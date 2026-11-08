"""Robot onboard software. Everything here only sees the world through `io`.

States: DEPLOYING, EXPLORING, LOST_LINK_EXPLORING, RETURNING_TO_SIGNAL,
RETURNING_HOME, REPLANNING, FAULT, DONE, plus WAITING_FOR_LINK in baseline mode.

Modes: "deadzone" (default, the real thing) and "baseline" ("without Deadzone": a robot that
stops and waits when its link drops and carries no relays, like a tethered or teleoperated
robot). Set at start with DZ_MODE=baseline or live with Robot.set_mode().
"""
import math
import os
import re

import numpy as np

from ..floorplan import FREE, UNKNOWN
from ..geometry import points_in_poly, wrap_angle
from ..network.dtn import PRIO, make_bundle
from . import planning
from .exploration import ProgressExplorer, line_clear
from .mapping import OccupancyMap
from .perception import close_crop, filter_hits, get_detector
from .power import Battery, RESERVE_PCT, wheel_current
from .scheduler import Scheduler

V_MAX = 0.8            # m/s cruise
LINK_LOST_AFTER = 2.0  # s without a path to CMD
CRUMB_SPACING = 1.5    # m between "had signal here" breadcrumbs
REPLAN_PERIOD = 1.5    # s
TELEMETRY_PERIOD = 1.0
BATTERY_TIME_SCALE = 6.0  # demo: drain faster so bars visibly move

# Multi-robot coordination through targets shared in telemetry bundles
PEER_TARGET_RADIUS = 4.0   # m, frontiers this close to a claimed target are penalized
PEER_TARGET_PENALTY = 12.0  # larger than the best possible size bonus (40 * 0.25)
PEER_FRESH_S = 15.0        # ignore claims older than this (peer out of contact)
DEPLOY_STAGGER_S = 1.5     # robot n waits n * this before exploring, so claims go out in order

# Relay drop rule (DARPA SubT style: drop before the link breaks, not after)
RELAYS_PER_ROBOT = 2
# dBm to the best upstream (non-robot) neighbor. The plan's -80 almost never fires in
# collapse_01 because links fall off in jumps at walls, -76 leaves a usable window.
RELAY_DROP_RSSI = -76.0
# A new link only comes up above -82 dBm (propagation.LINK_UP_DBM), while an existing one
# survives down to -88. Below this floor a fresh relay here could never link upstream, so
# dropping would waste it (happens when one step puts a wall on the line).
RELAY_DROP_FLOOR = -81.0
RELAY_MIN_SPACING = 4.0    # m from every relay this robot knows about

HOME_COST_PERIOD = 2.0     # s between A* "distance home" refreshes

# Lost link and replanning
LINK_HOLD_S = 10.0         # after reconnecting, wait at most this long for the dark backlog to upload
PATH_CHECK_M = 3.0         # look this far down the path for new obstacles
SURVIVOR_CLEAR_M = 0.5     # never drive over a person: motion plans keep this far from confirmed survivors
PATH_CHECK_SKIP_M = 0.4    # ignore the robot's own footprint (it may sit in a wall's inflation)
REPLAN_PAUSE_S = 0.6       # stop briefly in REPLANNING so the replan is visible and the map settles
REPLAN_COOLDOWN_S = 5.0    # repeat obstacles this soon after a replan are replanned silently
TRAPPED_AFTER_S = 10.0     # no route for this long raises a TRAPPED fault to the command post
ROUTE_CHECK_PERIOD = 2.0   # s between "is the rescue route I sent still open on my map?" checks
COLLAPSE_MARGINS_CELLS = (4, 2)  # rescue routes stay 1 m (else 0.5 m) clear of fresh collapse
ROUTE_MAX_POINTS = 60      # Command's RescueRoute cap (Aziz, PR #28)

# Wheel overcurrent (plan: above 6 A for 0.5 s -> stop, reverse 0.5 m, mark ahead, replan)
OVERCURRENT_A = 6.0
OVERCURRENT_HOLD_S = 0.5
INJECTED_SPIKE_A = 5.0     # director F key: extra amps on top of the normal wheel current
REVERSE_M = 0.5
REVERSE_V = 0.3
REVERSE_TIMEOUT_S = 4.0
SAFE_STOP_FAULTS = 3       # motion faults ...
SAFE_STOP_WINDOW_S = 60.0  # ... within this window -> SAFE_STOP

# Scheduler overload moment (director): perception inference suddenly costs this much
PERCEPTION_OVERLOAD_MS = 400
PERCEPTION_OVERLOAD_S = 3.0

# Dispatched plans
# "Unsure, moving closer": a hot spot the detector scores between these from a distance is not
# decided yet when a close-up crop exists; the robot drives to CLOSE_LOOK_M of it and judges the
# close-up (ml/crops/runtime/<crop>_close.png). The six demo crops score near 0 or 1, so the
# demo beats never take this path.
UNSURE_LO, UNSURE_HI = 0.35, 0.75
CLOSE_LOOK_M = 2.0         # judge the close-up from here
CLOSE_LOOK_STANDOFF_M = 1.4  # drive to this distance from the hot spot, never onto it
CLOSE_LOOK_TIMEOUT_S = 20.0  # could not get close: decide on the distant view

ZONE_PULL_PER_M = 0.7      # before the zone is on our map: score falls with distance to the zone
VOICE_ZONE_PULL_PER_M = 2.0  # a spoken "explore X" outweighs nearby frontiers (distance costs 1/m)
ZONE_DONE_KNOWN = 0.8      # stop pulling once this share of the zone's cells is mapped

# Rescue route: safest known route entrance -> survivor for responders. Clearance is the
# planner's 1-cell inflation (2 cells would close the 1.2 m doors) plus the wall cost, which
# keeps the route centered in corridors and doors.
HAZARD_MARGIN_CELLS = 4    # 1 m band around no-go areas ...
HAZARD_COST = 3.0          # ... costs this much extra per cell

# Final contract (telemetry): `state` is one of STATES, `fault` is None or one of FAULTS.
STATES = ("DEPLOYING", "EXPLORING", "LOST_LINK_EXPLORING", "RETURNING_TO_SIGNAL",
          "RETURNING_HOME", "REPLANNING", "FAULT", "DONE", "WAITING_FOR_LINK",
          "GOING_TO_POINT", "HOLDING")

# Direct commands (voice / phone) a robot accepts; see rayan.md voice-contract entry
COMMANDS = ("explore_zone", "go_to", "return_home", "hold", "resume")
CMD_ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
ETA_SPEED = 0.75 * 0.8      # m/s average incl. turns (V_MAX 0.8), for spoken ETAs
FAULTS = ("OVERCURRENT", "STUCK", "LOW_BATTERY", "TRAPPED", "SAFE_STOP")

# Robot modes. Deadzone is the demo default; baseline is the "without Deadzone" comparison.
MODES = ("deadzone", "baseline")


def default_mode():
    """DZ_MODE=baseline starts every robot in baseline mode; anything else means deadzone."""
    mode = os.environ.get("DZ_MODE", "deadzone").strip().lower()
    return mode if mode in MODES else "deadzone"


def _collinear_compact(pts):
    """Command's own compaction (PR #28): drop exactly-collinear middle points only."""
    out = []
    for q in pts:
        if out and q == out[-1]:
            continue
        while len(out) > 1:
            a, b = out[-2:]
            u = b[0] - a[0], b[1] - a[1]
            v = q[0] - b[0], q[1] - b[1]
            if u[0] * v[1] - u[1] * v[0] != 0 or u[0] * v[0] + u[1] * v[1] < 0:
                break
            out.pop()
        out.append(q)
    return out


def fit_route(pts, cap=ROUTE_MAX_POINTS, tol=0.15):
    """Rescue route points, rounded to cm, that Command will accept (at most `cap` after its
    compaction). Routes that already fit are returned unchanged, so nothing about normal routes
    (the demo's included) changes. Longer ones (big generated buildings) are simplified with
    Douglas-Peucker at `tol` m, then thinned evenly, always keeping both ends."""
    pts = [[round(px, 2), round(py, 2)] for px, py in pts]
    if len(pts) <= cap or len(_collinear_compact(pts)) <= cap:
        return pts

    def dp(seg):
        if len(seg) < 3:
            return seg
        (ax, ay), (bx, by) = seg[0], seg[-1]
        L = math.hypot(bx - ax, by - ay) or 1e-9
        d = [abs((bx - ax) * (ay - y) - (ax - x) * (by - ay)) / L for x, y in seg[1:-1]]
        k = max(range(len(d)), key=d.__getitem__)
        if d[k] <= tol:
            return [seg[0], seg[-1]]
        return dp(seg[:k + 2])[:-1] + dp(seg[k + 1:])
    out = dp(pts)
    if len(out) > cap:
        idx = sorted({round(i * (len(out) - 1) / (cap - 1)) for i in range(cap)})
        out = [out[i] for i in idx]
    return out


def resume_command(rid, now):
    """Bundle the command post sends to clear a robot's SAFE_STOP. CMD code enqueues it in the
    CMD network queue; it reaches the robot only if a route exists (custody like any bundle)."""
    return make_bundle("CMD", rid, "command", {"cmd": "resume"}, now, 64)


def is_robot_id(nid):
    """R1, R2 ... are robots. RL1 (relay), CMD and phones are infrastructure."""
    return len(nid) > 1 and nid[0] == "R" and nid[1:].isdigit()


def robot_rank(rid):
    """R1 -> 0, R2 -> 1 ... Lower rank has priority when two robots want the same frontier."""
    digits = "".join(ch for ch in rid if ch.isdigit())
    return int(digits) - 1 if digits else 0


class Robot:
    def __init__(self, rid, name, color, pose, fp_shape, cell, entry, nogo=None,
                 lost_link_budget_s=45.0):
        h, w = fp_shape
        self.id, self.name, self.color = rid, name, color
        self.pose = list(pose)
        self.cell = cell
        self.entry = entry
        self.map = OccupancyMap(w, h, cell)
        self.nogo = nogo if nogo is not None else np.zeros((h, w), dtype=bool)
        self.base_nogo = self.nogo.copy()   # hazards known at deploy; plan no-go areas add to it
        self.zones = []                     # this robot's dispatched zones, highest priority first
        self.battery = Battery()
        self.state = "DEPLOYING"
        self.t = 0.0
        self.state_since = 0.0

        self.path = []            # world waypoints
        self.target = None        # world goal
        self.goal_cell = None
        self.blacklist = []
        self.last_plan_t = -99.0
        self.cmd_v = 0.0
        self.v = 0.0

        self.linked = False
        self.last_link_t = 0.0
        self.lost_budget = lost_link_budget_s
        self.crumbs = [tuple(pose[:2])]
        self.found = {}           # survivor id -> record
        self.rejected = set()     # hot spot ids the detector turned down (reported once)
        self.unsure = {}          # hot spot id -> {pos, conf_far, since, crop, close}: waiting for a close look
        self.look_at = None       # the unsure hot spot the robot is driving toward, or None
        self.found_while_dark = False
        self.dark_declared = False   # link_lost raised for the current outage
        self.reconnect_t = None      # when the link last came back after an outage
        self.resume_state = None     # state to go back to after REPLANNING
        self.replan_fail_since = None
        self.last_replan_done_t = -99.0

        self.relays_left = RELAYS_PER_ROBOT
        self.my_relays = []       # [x, y] of relays this robot dropped
        self.upstream_rssi = None
        self.home_pct = Battery.pct_to_drive(0.0)
        self.home_m = 0.0
        self.home_t = -99.0

        self.outbox = []
        self.inbox = []           # bundles the network delivered to this robot
        self.peers = {}           # peer id -> {"target", "pose", "t"} from their telemetry
        self.rank = robot_rank(rid)
        self.last_telemetry_t = -99.0
        self.lidar_pts = []
        self.fault = None
        self.stuck_ref = (pose[0], pose[1], 0.0)
        self.events = []

        self.scheduler = Scheduler()
        self.tasks = []
        # Reality-side tallies for the "Under the hood" panel (Aziz sums them into tick.stats).
        # Never put in a bundle: Command learns about the robot only through delivered messages.
        self.counters = {"detector_calls": 0, "detector_persons": 0, "detector_rejections": 0,
                         "detector_unsure": 0, "deadlines_met": 0, "deadlines_missed": 0,
                         "rescue_routes": 0, "replans": 0, "dark_s": 0.0}
        self.wheel_a = 0.0
        self.spike_until = -1.0      # director-injected overcurrent ends at this time
        self.over_since = None       # wheel current above the limit since
        self.fault_resume = None     # state to resume after a fault recovery
        self.reverse_from = None     # pose where the reverse maneuver started
        self.reverse_t = 0.0
        self.fault_times = []        # motion faults in the SAFE_STOP window
        self.low_battery = False
        self.overload_until = None
        self.plan = None             # latest plan bundle payload from CMD (acted on in step A)
        self.mode = default_mode()
        self.routes = {}             # survivor id -> rescue route we sent (watched for new rubble)
        self.route_check_t = -99.0
        self.cmds = {}               # cmd_id -> last ack sent (dedupe, repeat answers)
        self.active_cmd = None       # accepted go_to / return_home / explore_zone in progress
        self.goto = None             # go_to target (x, y)
        self._cmd_zone_id = None
        self.explorer = (ProgressExplorer((h, w), cell)
                         if os.environ.get("DZ_EXPLORATION_V2") == "1" else None)
        self.sensor_view = os.environ.get("DZ_SENSOR_VIEW") == "1"
        self.camera_frame = None

    # ------------------------------------------------------------------ mode toggle
    def set_mode(self, mode):
        """Switch between "deadzone" and "baseline" live (Q&A toggle). A baseline robot that is
        waiting in the dark goes back to normal Deadzone behavior when switched back."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if mode == self.mode:
            return
        self.mode = mode
        self.events.append({"kind": "mode_changed", "robot": self.id, "mode": mode})
        if mode == "deadzone" and self.state == "WAITING_FOR_LINK":
            self.path = []
            self._set_state("LOST_LINK_EXPLORING" if self.dark_declared else "EXPLORING")

    # ------------------------------------------------------------------ main step
    def step(self, dt, io):
        self.t = io.time
        odo = io.odometry()
        self.pose = list(odo["pose"])
        x, y, th = self.pose

        angles, ranges, hits = io.lidar()
        self.map.integrate(self.pose, angles, ranges, hits)
        if self.explorer is not None:
            self.explorer.observe(self.map.grid, self.pose, self.t,
                                  self.state in ("EXPLORING", "LOST_LINK_EXPLORING"))
        self.lidar_pts = [[round(x + math.cos(a) * r, 2), round(y + math.sin(a) * r, 2)]
                          for a, r in zip(angles[::2], ranges[::2])]

        self._read_inbox()
        self._read_commands(io)
        self._perceive(io)
        self._check_routes()
        self._update_link(io)
        self._maybe_drop_relay(io)
        self._run_scheduler(dt)
        self._check_faults(odo)
        self._behave()
        self._check_command_done()
        v, w =self._reverse() if self.state == "FAULT" else self._follow()
        io.drive(v, w)
        self.cmd_v = v
        self.v = odo["v"]
        self.battery.drain(dt * BATTERY_TIME_SCALE, self.v)
        self._emit_bundles()

    # ------------------------------------------------------------------ comms in
    def _read_commands(self, io):
        """Plan and command bundles from the command post, delivered by the network. receive()
        can also hand over peer telemetry the inbox reader didn't take, so learn from it too."""
        for b in io.radio.receive():
            p = b.get("payload") or {}
            if b["kind"] == "telemetry":
                self._learn_peer(b)
            elif b["kind"] == "command" and p.get("cmd_id") is not None:
                self._on_command(p)                 # voice / phone command: acked
            elif b["kind"] == "command" and p.get("cmd") == "resume":
                self._resume_from_safe_stop()       # legacy SAFE_STOP resume: no ack
            elif b["kind"] == "plan":
                if self.plan is None or self.plan.get("_t", -1) <= b["created"]:
                    self.plan = dict(p, _t=b["created"])
                    self._apply_plan(self.plan)

    def _apply_plan(self, plan):
        """Follow a dispatched search plan: our zones (frontier preference), the plan's no-go
        areas (never planned through) and its lost-link budget. A newer plan replaces the old."""
        h, w = self.nogo.shape
        xs = (np.arange(w) + 0.5) * self.cell
        ys = (np.arange(h) + 0.5) * self.cell
        cx, cy = np.meshgrid(xs, ys)
        nogo = self.base_nogo.copy()
        for ng in plan.get("no_go", []):
            nogo |= points_in_poly(cx, cy, ng["poly"])
        self.nogo = nogo
        self.zones = []
        for z in sorted((z for z in plan.get("zones", []) if z.get("robot") == self.id),
                        key=lambda z: (z.get("priority", 1), z["id"])):
            mask = points_in_poly(cx, cy, z["poly"])
            if not mask.any():
                continue
            iy, ix = np.nonzero(mask)
            self.zones.append({"id": z["id"], "priority": z.get("priority", 1),
                               "comms": z.get("comms", "relay"), "mask": mask,
                               "near": planning.dilate(mask, 2),   # catches doorway frontiers
                               "center": (float(xs[ix].mean()), float(ys[iy].mean()))})
        if "lost_link_budget_s" in plan:
            self.lost_budget = float(plan["lost_link_budget_s"])
        self.path = []                       # replan under the new plan right away
        if self.explorer is not None:
            self.explorer.reset_goal()
        self.events.append({"kind": "plan_applied", "robot": self.id, "plan_id": plan.get("plan_id"),
                            "zones": [z["id"] for z in self.zones]})

    def _active_zone(self):
        """Highest-priority zone that is not mapped yet, or None."""
        for z in self.zones:
            if not self._zone_complete(z):
                return z
        return None

    def _zone_complete(self, zone):
        if (self.map.grid[zone["mask"]] != UNKNOWN).mean() < ZONE_DONE_KNOWN:
            return False
        if self.explorer is not None:
            free = zone["mask"] & (self.map.grid == FREE) & ~self.nogo
            surveyed = self.explorer.surveyed | self.explorer.team_surveyed
            if free.any() and surveyed[free].mean() < .9:
                return False
        return True

    def _in_lost_link_ok_zone(self):
        ix, iy = self._cell(*self.pose[:2])
        return any(z["comms"] == "lost_link_ok" and z["mask"][iy, ix] for z in self.zones)

    def _resume_from_safe_stop(self):
        """CMD `resume`: clear SAFE_STOP and the fault counter, then replan and carry on."""
        if self.fault != "SAFE_STOP":
            return
        self.fault_times = []
        self._clear_fault()
        self.events.append({"kind": "resumed", "robot": self.id})
        self.state = self.fault_resume or "EXPLORING"
        self._start_replan("resume")

    # ------------------------------------------------------------------ voice / phone commands
    def _on_command(self, p):
        """A direct command from CMD (voice or phone): decide, act, and answer with a priority-1
        command_ack. The same cmd_id twice gets the same answer again and is not run twice."""
        cid = p.get("cmd_id")
        if not isinstance(cid, str) or not CMD_ID_RE.fullmatch(cid):
            return                                   # can't answer without a valid id
        if cid in self.cmds:
            self._send_ack(dict(self.cmds[cid]))     # repeat the answer (e.g. a lost ack)
            return
        cmd = p.get("cmd")
        status, eta, reason, say = self._decide_command(cid, cmd, p)
        if status == "accepted" and self.explorer is not None:
            self.explorer.reset_goal()
        ack = {"cmd_id": cid, "robot": self.id, "cmd": cmd, "status": status,
               "eta_s": None if eta is None else int(round(eta)), "reason": reason, "say": say,
               "state": self.state, "t": round(self.t, 1), "issued_t": p.get("issued_t")}
        self.cmds[cid] = ack
        self._send_ack(ack)
        self.events.append({"kind": "command_received", "robot": self.id, "cmd_id": cid, "cmd": cmd,
                            "status": status, "eta_s": ack["eta_s"], "reason": reason, "say": say})
        if status == "accepted" and cmd in ("go_to", "return_home", "explore_zone"):
            self.active_cmd = {"cmd_id": cid, "cmd": cmd, "zone": (p.get("zone") or {}).get("name"),
                               "zone_id": self._cmd_zone_id}
            self._check_command_done()               # e.g. return_home while already home

    def _send_ack(self, ack):
        self.outbox.append(self._bundle("command_ack", ack, 220))

    def _refuse(self, reason, say):
        return "refused", None, reason, say

    def _decide_command(self, cid, cmd, p):
        """(status, eta_s, reason, say) for one command, and start doing it if accepted."""
        self._cmd_zone_id = None
        if cmd not in COMMANDS:
            return self._refuse("bad_command", "I don't know that command.")
        if cmd == "resume":
            if self.fault == "SAFE_STOP":
                self._resume_from_safe_stop()
                return "accepted", None, None, "Safe stop cleared. Resuming the search."
            if self.state in ("HOLDING", "GOING_TO_POINT", "DONE"):
                self.goto, self.path = None, []
                self._set_state("EXPLORING")
                return "accepted", None, None, "Resuming the search."
            return "accepted", None, None, "Already searching."
        if self.fault == "SAFE_STOP":
            return self._refuse("safe_stop", "I'm in safe stop. Send resume first.")
        if self.state == "FAULT":
            return self._refuse("fault", "I'm recovering from a fault. Try again in a few seconds.")
        if cmd == "hold":
            self.goto, self.path = None, []
            self._set_state("HOLDING")
            return "accepted", None, None, "Holding position."
        if cmd == "return_home":
            if math.dist(self.pose[:2], self.entry) < 0.6:
                self.path = []
                self._set_state("DONE")
                return "accepted", 0, None, "I'm already at the entrance."
            if not self._plan_to(self.entry):
                return self._refuse("no_route", "I can't find a known route home right now.")
            self.goto = None
            self._set_state("RETURNING_HOME")
            eta = self._path_m() / ETA_SPEED
            return "accepted", eta, None, f"Heading home, about {int(round(eta))} seconds."
        if self.low_battery:
            return self._refuse("low_battery", "My battery is low, I'm heading home.")
        if cmd == "go_to":
            target = p.get("target")
            ok = (isinstance(target, (list, tuple)) and len(target) == 2
                  and all(isinstance(v, (int, float)) and math.isfinite(v) for v in target))
            if not ok:
                return self._refuse("bad_command", "I didn't get a valid point.")
            x, y = float(target[0]), float(target[1])
            if not (0 <= x < self.map.w * self.cell and 0 <= y < self.map.h * self.cell):
                return self._refuse("outside_building", "That point is outside the building.")
            ix, iy = self._cell(x, y)
            if self.nogo[iy, ix]:
                return self._refuse("no_go", "That point is in a no-go area.")
            saved = list(self.path)
            if not self._plan_to((x, y)):
                self.path = saved
                return self._refuse("no_route", "I don't know a route there yet.")
            length = self._path_m()
            need = Battery.pct_to_drive(length + 1.6 * math.dist((x, y), self.entry))
            if self.battery.pct - need <= RESERVE_PCT:
                self.path = saved
                return self._refuse("battery_reserve", "Not enough battery to go there and come back.")
            self.goto = (x, y)
            self._set_state("GOING_TO_POINT")
            eta = length / ETA_SPEED
            return "accepted", eta, None, f"On my way, about {int(round(eta))} seconds."
        # explore_zone
        zone = p.get("zone") or {}
        poly = zone.get("poly")
        if not (isinstance(poly, list) and len(poly) >= 3 and all(
                isinstance(q, (list, tuple)) and len(q) == 2 and all(isinstance(v, (int, float)) for v in q)
                for q in poly)):
            return self._refuse("bad_command", "I didn't get a valid area.")
        h, w = self.nogo.shape
        xs = (np.arange(w) + 0.5) * self.cell
        ys = (np.arange(h) + 0.5) * self.cell
        cx, cy = np.meshgrid(xs, ys)
        mask = points_in_poly(cx, cy, poly)
        if not mask.any():
            return self._refuse("outside_building", "That area is outside the building.")
        if (mask & ~self.nogo).sum() == 0:
            return self._refuse("no_go", "That whole area is a no-go zone.")
        name = zone.get("name") or zone.get("id") or "that area"
        zid = f"voice:{zone.get('id') or cid}"
        iy, ix = np.nonzero(mask)
        center = (float(xs[ix].mean()), float(ys[iy].mean()))
        self.zones = [z for z in self.zones if not z["id"].startswith("voice:")]
        self.zones.insert(0, {"id": zid, "priority": 0, "comms": "relay", "mask": mask,
                              "near": planning.dilate(mask, 2), "center": center})
        self._cmd_zone_id = zid
        self.goto, self.path = None, []
        if self.state in ("HOLDING", "GOING_TO_POINT", "DONE", "RETURNING_HOME"):
            self._set_state("EXPLORING")
        if self._zone_complete(self.zones[0]):
            return "accepted", 0, None, f"{name} is already searched. I'll check it again."
        saved = list(self.path)
        eta = (self._path_m() if self._plan_to(center) else 1.6 * math.dist(self.pose[:2], center)) / ETA_SPEED
        self.path = saved
        return "accepted", eta, None, f"Heading to {name}, about {int(round(eta))} seconds."

    def _path_m(self):
        pts = [tuple(self.pose[:2])] + [tuple(q) for q in self.path]
        return planning.path_length(pts)

    def _check_command_done(self):
        """Send a `completed` ack when the active command is done."""
        c = self.active_cmd
        if c is None:
            return
        done, say = False, None
        if c["cmd"] == "go_to" and self.state == "HOLDING" and self.goto is None:
            done, say = True, "I'm there."
        elif c["cmd"] == "return_home" and self.state == "DONE":
            done, say = True, "I'm back at the entrance."
        elif c["cmd"] == "explore_zone":
            z = next((z for z in self.zones if z["id"] == c["zone_id"]), None)
            if z is None:
                self.active_cmd = None            # a newer plan replaced the zone
                return
            if self._zone_complete(z):
                done, say = True, f"Finished searching {c['zone'] or 'that area'}."
        if not done:
            return
        self.active_cmd = None
        ack = {"cmd_id": c["cmd_id"], "robot": self.id, "cmd": c["cmd"], "status": "completed",
               "eta_s": None, "reason": None, "say": say, "state": self.state,
               "t": round(self.t, 1), "issued_t": self.cmds[c["cmd_id"]].get("issued_t")}
        self.cmds[c["cmd_id"]] = ack
        self._send_ack(ack)
        self.events.append({"kind": "command_completed", "robot": self.id, "cmd_id": c["cmd_id"],
                            "cmd": c["cmd"], "say": say})

    def _read_inbox(self):
        """Learn peer targets from telemetry bundles the network delivered to us."""
        for b in self.inbox:
            self._learn_peer(b)
        self.inbox.clear()

    def _learn_peer(self, b):
        p = b["payload"]
        if b["kind"] != "telemetry" or p.get("id") in (None, self.id):
            return
        prev = self.peers.get(p["id"])
        if prev is None or prev["t"] <= b["created"]:
            self.peers[p["id"]] = {"target": p.get("target"), "pose": p.get("pose"),
                                   "relays": p.get("relays", []), "found": p.get("found", []),
                                   "t": b["created"]}
            if self.explorer is not None:
                self.explorer.observe_peer(self.map.grid, p.get("pose"))

    def _claimed_targets(self):
        """Fresh targets of higher-priority peers. Lower rank wins, so claims never oscillate."""
        out = []
        for pid, info in self.peers.items():
            if info["target"] is None or self.t - info["t"] > PEER_FRESH_S:
                continue
            if robot_rank(pid) < self.rank:
                out.append(info["target"])
        return out

    # ------------------------------------------------------------------ sensing
    def _perceive(self, io):
        # every hot spot goes through the trained detector (sim sensor fallback if no model)
        hits = io.thermal()
        hits, finals = self._triage_unsure(hits)
        kept = filter_hits(hits) + [h for h, conf in finals if conf >= get_detector().threshold]
        hits = hits + [h for h, _ in finals]
        kept_ids = {h["id"] for h in kept}
        if self.sensor_view:
            detector = get_detector()
            observations = []
            for hit in hits:
                score = detector.score(hit.get("crop"))
                observations.append({
                    "id": hit["id"], "pos": list(hit["pos"]), "crop": hit.get("crop"),
                    "verdict": "person" if hit["id"] in kept_ids else "rejected",
                    "conf": score, "source": "model" if score is not None else "sim"})
            self.camera_frame = {"t": self.t, "pose": list(self.pose), "hits": observations}
        for h in hits:
            if h["id"] in kept_ids or h["id"] in self.rejected or h["id"] in self.found:
                continue                  # (a person confirmed from close up still scores low from afar)
            self.rejected.add(h["id"])    # the robot only knows "hot, but not a person"
            self.counters["detector_calls"] += 1
            self.counters["detector_rejections"] += 1
            self.events.append({"kind": "hotspot_rejected", "robot": self.id, "id": h["id"],
                                "pos": [round(h["pos"][0], 2), round(h["pos"][1], 2)],
                                "crop": h.get("crop"), "conf": get_detector().score(h.get("crop")),
                                "heatmap": get_detector().heatmap(h.get("crop")),
                                **{k: h[k] for k in ("conf_far", "looked_closer") if k in h}})
        for s in kept:
            if s["id"] in self.found:
                continue
            rec = {"id": s["id"], "pos": [round(s["pos"][0], 2), round(s["pos"][1], 2)],
                   "by": self.id, "t": round(self.t, 1), "conf": s.get("conf", 0.99), "crop": s.get("crop"),
                   "heatmap": get_detector().heatmap(s.get("crop"))}
            self.found[s["id"]] = rec
            self.counters["detector_calls"] += 1
            self.counters["detector_persons"] += 1
            if not self.linked and not self._peer_found(s["id"]):
                self.found_while_dark = True    # new news: go back to signal and report it
            self.outbox.append(make_bundle(self.id, "CMD", "survivor", rec, self.t, 400))
            self.events.append({"kind": "survivor_found", "robot": self.id, "survivor": s["id"],
                                "pos": rec["pos"], "linked": self.linked,
                                "crop": rec["crop"], "conf": rec["conf"], "heatmap": rec["heatmap"],
                                **{k: s[k] for k in ("conf_far", "looked_closer") if k in s}})
            self._on_survivor_confirmed(io, rec)

    def _triage_unsure(self, hits):
        """Split thermal hits into the ones to judge now and the ones decided after a close look.
        A new hot spot whose distant score is unsure (and that has a close-up crop) is held while
        the robot drives toward it; within CLOSE_LOOK_M it is judged on the close-up, after
        CLOSE_LOOK_TIMEOUT_S on the distant view. Returns (hits to judge normally, [(hit, conf)])."""
        det = get_detector()
        normal, finals = [], []
        for h in hits:
            hid = h["id"]
            u = self.unsure.get(hid)
            if hid in self.found or hid in self.rejected:
                normal.append(h)
                continue
            if u is None:
                s = det.score(h.get("crop"))
                close = close_crop(h.get("crop"))
                if s is None or close is None or not (UNSURE_LO <= s < UNSURE_HI):
                    normal.append(h)
                    continue
                # held in every state (a robot still deploying or returning sees it too); only an
                # exploring robot drives over, the others decide on the distant view at the timeout
                u = self.unsure[hid] = {"pos": list(h["pos"]), "conf_far": s, "since": self.t,
                                        "crop": h.get("crop"), "close": close}
                self.counters["detector_calls"] += 1
                self.counters["detector_unsure"] += 1
                self.events.append({"kind": "hotspot_unsure", "robot": self.id, "id": hid,
                                    "pos": [round(h["pos"][0], 2), round(h["pos"][1], 2)], "crop": h.get("crop"),
                                    "conf": s, "heatmap": det.heatmap(h.get("crop")),
                                    "say": f"AI unsure {s * 100:.0f}%, moving closer"})
                if self.look_at is None:
                    self.look_at = hid
            near = math.dist(self.pose[:2], h["pos"]) <= CLOSE_LOOK_M
            if not near and self.t - u["since"] <= CLOSE_LOOK_TIMEOUT_S and u.get("approaching", True):
                continue                                  # still on the way: not decided yet
            s2 = det.score(u["close"]) if near else None
            conf = s2 if s2 is not None else u["conf_far"]
            finals.append(({**h, "crop": u["close"] if s2 is not None else h.get("crop"), "conf": conf,
                            "detector": "model", "conf_far": u["conf_far"], "looked_closer": s2 is not None}, conf))
            self.unsure.pop(hid, None)
            if self.look_at == hid:
                self.look_at = None
        return normal, finals

    def _look_closer(self):
        """While an unsure hot spot is pending, own the path: drive to CLOSE_LOOK_STANDOFF_M of it.
        Returns True while approaching (the caller skips frontier planning)."""
        if self.look_at is None:
            return False
        u = self.unsure.get(self.look_at)
        if u is None or self.t - u["since"] > CLOSE_LOOK_TIMEOUT_S:
            if u is not None:
                u["approaching"] = False              # decide on the distant view at the next sighting
            self.look_at = None
            return False
        ux, uy = u["pos"]
        d = math.dist(self.pose[:2], (ux, uy))
        if d <= CLOSE_LOOK_M:
            return False                                  # close enough: _perceive judges the close-up
        goal = (ux + (self.pose[0] - ux) / d * CLOSE_LOOK_STANDOFF_M,
                uy + (self.pose[1] - uy) / d * CLOSE_LOOK_STANDOFF_M)
        if not self.path or self.target != list(goal) or self.t - self.last_plan_t > REPLAN_PERIOD:
            if not self._plan_to(goal):
                return False              # no route on our map yet: explore this tick, try again next
        return True

    # ------------------------------------------------------------------ rescue route
    def _peer_found(self, sid):
        """A peer already confirmed this survivor (from the `found` list in its telemetry)."""
        return any(sid in (info.get("found") or []) for info in self.peers.values())

    def _on_survivor_confirmed(self, io, rec):
        """Send responders the safest route from the entrance to the survivor, computed on our
        own map, to CMD as a priority-1 bundle. If the survivor is in a dead zone (no link here)
        also drop a beacon relay next to them, so responders get radio at the survivor. Where
        there is coverage no beacon is needed (and spending relays there reshapes the network)."""
        if self._peer_found(rec["id"]):
            return                         # a peer already confirmed this survivor: no 2nd beacon/route
        beacon = None
        if self.mode == "deadzone" and self.relays_left > 0 and not self.linked:
            try:
                beacon = io.drop_relay(beacon_for=rec["id"])   # tagged beacon (None if refused)
            except ValueError:
                beacon = None              # the deployer refused this spot (wall / no-go)
            if beacon is not None:
                x, y, _ = self.pose
                self.relays_left -= 1
                self.my_relays.append([round(x, 2), round(y, 2)])
        route = self._rescue_route_cells(rec["pos"])
        if route is None:
            return
        self.routes[rec["id"]] = {"goal": rec["pos"], "beacon": beacon, "cells": None, "blocked": False}
        self._send_route(rec["id"], route, "found")

    def _send_route(self, sid, route, reason):
        """Send (or resend) the rescue route to CMD as a priority-1 bundle. A resend carries a newer
        `t`, so Command replaces the old route when it arrives."""
        cells, path, length_m, clearance_m = route
        r = self.routes[sid]
        r.update(cells=cells, blocked=False)
        payload = {"survivor": sid, "by": self.id, "path": path, "length_m": length_m,
                   "clearance_m": clearance_m, "beacon": r["beacon"], "t": round(self.t, 1)}
        self.outbox.append(self._bundle("rescue_route", payload, 64 + 12 * len(path)))
        self.counters["rescue_routes"] += 1
        self.events.append({"kind": "rescue_route", "robot": self.id, "survivor": sid, "path": path,
                            "length_m": length_m, "clearance_m": clearance_m, "beacon": r["beacon"],
                            "reason": reason})

    def _check_routes(self):
        """Every ROUTE_CHECK_PERIOD s: is each route we sent still open on our own map? New rubble
        (an aftershock, a collapse) that our lidar has seen on it -> recompute and resend. If no
        route exists any more, say so once and keep trying (the map may open up again)."""
        if not self.routes or self.t - self.route_check_t < ROUTE_CHECK_PERIOD:
            return
        self.route_check_t = self.t
        trav = self._trav()
        for sid, r in self.routes.items():
            if not r["blocked"] and all(trav[y, x] for x, y in r["cells"]):
                continue
            route = self._rescue_route_cells(r["goal"])
            if route is not None:
                self._send_route(sid, route, "blocked")
            elif not r["blocked"]:
                r["blocked"] = True
                self.events.append({"kind": "rescue_route_blocked", "robot": self.id, "survivor": sid})

    def _rescue_route(self, goal):
        """(points, length_m, clearance_m) of the rescue route to goal, or None."""
        route = self._rescue_route_cells(goal)
        return None if route is None else route[1:]

    def _rescue_route_cells(self, goal):
        """A* entrance -> survivor over known free cells only: never through rubble, walls, unknown
        space or no-go, centered by the wall cost, with a cost band around hazards.
        Returns (cells to watch, points, length_m, clearance_m) or None. The watched cells are the
        route's cells that were open when it was planned; if one closes, the route is blocked."""
        grid = self.map.grid
        cost = planning.wall_cost(grid) + HAZARD_COST * planning.dilate(self.nogo, HAZARD_MARGIN_CELLS)
        trav = planning.traversable(grid, self.nogo)
        start, end = self._cell(*self.entry), self._cell(*goal)
        cells = None
        if self.map.collapsed.any():
            # keep responders away from fresh collapse: the part we saw fall may be only the
            # edge of it, so stay as far clear as the corridors allow (1 m, then 0.5 m)
            for margin in COLLAPSE_MARGINS_CELLS:
                safe = trav & ~planning.dilate(self.map.collapsed, margin)
                cells = planning.astar(safe, start, end, cost)
                if cells:
                    break
        if not cells:
            cells = planning.astar(trav, start, end, cost)
        if not cells:
            return None
        watch = [(cx, cy) for cx, cy in cells if trav[cy, cx]]
        centers = [((cx + 0.5) * self.cell, (cy + 0.5) * self.cell) for cx, cy in cells]
        pts = [list(self.entry)] + [list(p) for p in planning.simplify(cells, self.cell)] + [list(goal)]
        pts = fit_route(pts)
        length = math.dist(self.entry, centers[0]) + planning.path_length(centers) + math.dist(centers[-1], goal)
        return watch, pts, round(length, 1), planning.INFLATE_CELLS * self.cell

    def _bundle(self, kind, payload, size):
        """Bundle to CMD. `rescue_route` is priority 1; until network/dtn.py lists the kind in
        PRIO we build it from a known kind and set kind/prio ourselves (DTN orders by b["prio"])."""
        b = make_bundle(self.id, "CMD", kind if kind in PRIO else "plan", payload, self.t, size)
        b["kind"], b["prio"] = kind, PRIO.get(kind, 1)
        return b

    def _update_link(self, io):
        """Track the link and raise link_lost / link_restored exactly once per outage, in any state.
        An outage starts after LINK_LOST_AFTER s without a path to CMD (short blips are ignored)."""
        reachable = io.radio.cmd_reachable()
        x, y, _ = self.pose
        if reachable:
            if self.dark_declared:
                self.dark_declared = False
                self.reconnect_t = self.t
                self.found_while_dark = False
                self.events.append({"kind": "link_restored", "robot": self.id,
                                    "dark_s": round(self.t - self.last_link_t, 1)})
            self.last_link_t = self.t
            if math.dist(self.crumbs[-1], (x, y)) > CRUMB_SPACING:
                self.crumbs.append((x, y))
                self.crumbs = self.crumbs[-200:]
        elif not self.dark_declared and self.t - self.last_link_t > LINK_LOST_AFTER:
            self.dark_declared = True
            self.events.append({"kind": "link_lost", "robot": self.id})
        self.linked = reachable

    # ------------------------------------------------------------------ relays
    def _known_relays(self):
        out = list(self.my_relays)
        for info in self.peers.values():
            out.extend(info.get("relays") or [])
        return out

    def _maybe_drop_relay(self, io):
        """Drop a relay when all hold: still linked to CMD, best upstream link below
        -80 dBm, a relay left to drop, at least 4 m from every known relay, not in no-go.
        Upstream means infrastructure (CMD, relays, phones): robots never forward for others."""
        infra = [r for nid, r in io.radio.neighbors() if not is_robot_id(nid)]
        self.upstream_rssi = max(infra) if infra else None
        if self.mode == "baseline":
            return                      # baseline robots carry no relays
        if self.state not in ("EXPLORING", "RETURNING_TO_SIGNAL") or self.relays_left <= 0:
            return
        if not self.linked or self.upstream_rssi is None:
            return
        if not (RELAY_DROP_FLOOR < self.upstream_rssi < RELAY_DROP_RSSI):
            return
        x, y, _ = self.pose
        if any(math.dist((x, y), p) < RELAY_MIN_SPACING for p in self._known_relays()):
            return
        ix, iy = self._cell(x, y)
        if self.nogo[iy, ix] or self._in_lost_link_ok_zone():   # planner allowed this zone to be dark
            return
        try:
            io.drop_relay()
        except ValueError:
            return   # the deployer refused this spot, try again further along
        self.relays_left -= 1
        self.my_relays.append([round(x, 2), round(y, 2)])
        self.last_telemetry_t = -99.0   # tell peers right away so they keep their spacing

    # ------------------------------------------------------------------ onboard scheduler
    def _run_scheduler(self, dt):
        if self.overload_until is not None and self.t >= self.overload_until:
            self.scheduler.reset_wcet("perception")
            self.overload_until = None
        self.tasks = self.scheduler.run_frame(int(round(self.t / dt)))
        for name in dict.fromkeys(self.scheduler.new_misses):
            self.events.append({"kind": "deadline_miss", "robot": self.id, "task": name})
        self.counters["deadlines_met"] = self.scheduler.met
        self.counters["deadlines_missed"] = self.scheduler.missed
        if not self.linked:
            self.counters["dark_s"] = round(self.counters["dark_s"] + dt, 1)

    # ------------------------------------------------------------------ fault protection FSM
    #   NOMINAL --(wheel > 6 A for 0.5 s)--> OVERCURRENT -+
    #   NOMINAL --(v > 0.2 but < 5 cm in 3 s)--> STUCK ---+--> FAULT: stop, back up 0.5 m,
    #                                                       mark ahead occupied -> REPLANNING
    #   3 motion faults within 60 s --> SAFE_STOP (state FAULT, wheels off, stays stopped)
    #   battery - trip home <= reserve --> LOW_BATTERY (label) + RETURNING_HOME
    #   no route for 10 s --> TRAPPED (label, keeps retrying in REPLANNING)
    # Every fault raises a `fault` event and a priority-1 fault bundle to the command post.
    def _check_faults(self, odo):
        """Runs every frame, conceptually inside the 50 ms safety task."""
        x, y, _ = self.pose
        if self.fault == "SAFE_STOP":
            self.wheel_a = wheel_current(0.0, False)
            return
        spike = INJECTED_SPIKE_A if self.t < self.spike_until else 0.0
        self.wheel_a = wheel_current(self.cmd_v, bool(odo.get("blocked"))) + spike
        if self.wheel_a > OVERCURRENT_A and self.state not in ("DEPLOYING", "DONE", "FAULT"):
            if self.over_since is None:
                self.over_since = self.t
            elif self.t - self.over_since >= OVERCURRENT_HOLD_S:
                self._enter_fault("OVERCURRENT")
                return
        else:
            self.over_since = None
        if self.explorer is not None and self.cmd_v <= 0.2:
            # Camera sweeps and alignment intentionally stop translation. Only
            # sustained commanded travel belongs in the no-progress window.
            self.stuck_ref = (x, y, self.t)
        rx, ry, rt = self.stuck_ref
        if self.t - rt > 3.0:
            moved = math.dist((x, y), (rx, ry))
            self.stuck_ref = (x, y, self.t)
            if self.cmd_v > 0.2 and moved < 0.05 and self.state not in ("DEPLOYING", "DONE", "FAULT"):
                self._enter_fault("STUCK")
                return
        if odo.get("blocked"):
            self._block_ahead()

    def inject_overcurrent(self, seconds=1.0):
        """Director hook (F key): the wheel motors draw an extra INJECTED_SPIKE_A for `seconds`,
        as if a wheel jammed on debris. Detection and recovery then run as for a real spike."""
        self.spike_until = self.t + seconds

    def inject_perception_overload(self, seconds=PERCEPTION_OVERLOAD_S, wcet_ms=PERCEPTION_OVERLOAD_MS):
        """Director hook (scheduler overload moment): model inference suddenly costs `wcet_ms`
        per 500 ms frame for `seconds`. Perception and battery miss deadlines, safety never does."""
        self.scheduler.set_wcet("perception", wcet_ms)
        self.overload_until = self.t + seconds

    def _raise_fault(self, fault):
        self.fault = fault
        x, y, _ = self.pose
        rec = {"robot": self.id, "fault": fault, "pos": [round(x, 2), round(y, 2)],
               "t": round(self.t, 1), "state": self.state}
        self.events.append({"kind": "fault", "robot": self.id, "fault": fault})
        self.outbox.append(make_bundle(self.id, "CMD", "fault", rec, self.t, 120))

    def _clear_fault(self):
        """Back to nominal, but a robot heading home on low battery keeps that label."""
        self.fault = "LOW_BATTERY" if self.low_battery else None

    def _enter_fault(self, fault):
        """Motion fault: stop, back up REVERSE_M, mark what stopped us as occupied, then replan.
        The third motion fault within SAFE_STOP_WINDOW_S stops the robot for good."""
        self.fault_resume = self.resume_state if self.state == "REPLANNING" else self.state
        self.fault_times = [t for t in self.fault_times if self.t - t < SAFE_STOP_WINDOW_S] + [self.t]
        self.over_since = None
        self.path = []
        self._set_state("FAULT")
        if len(self.fault_times) >= SAFE_STOP_FAULTS:
            self._raise_fault("SAFE_STOP")
            return
        self._raise_fault(fault)
        self.reverse_from = list(self.pose)
        self.reverse_t = self.t

    def _reverse(self):
        return (0.0, 0.0) if self.fault == "SAFE_STOP" else (-REVERSE_V, 0.0)

    def _fault_recovery(self):
        if self.fault == "SAFE_STOP":
            return                       # needs a human (or a command bundle, later)
        backed = math.dist(self.pose[:2], self.reverse_from[:2])
        if backed < REVERSE_M and self.t - self.reverse_t < REVERSE_TIMEOUT_S:
            return
        self._block_ahead(self.reverse_from)
        self.state = self.fault_resume or "EXPLORING"   # resume target for the replan
        self._start_replan(self.fault.lower())

    def _block_ahead(self, pose=None):
        x, y, th = pose if pose is not None else self.pose
        for d in (0.35, 0.6):
            ix = int((x + math.cos(th) * d) // self.cell)
            iy = int((y + math.sin(th) * d) // self.cell)
            if 0 <= ix < self.map.w and 0 <= iy < self.map.h:
                self.map.mark_occupied(ix, iy)

    # ------------------------------------------------------------------ behavior FSM
    def _set_state(self, s):
        if s != self.state:
            self.state = s
            self.state_since = self.t

    def _behave(self):
        dark_for = self.t - self.last_link_t
        s = self.state

        if s == "DEPLOYING":
            if self.t - self.state_since > 1.0 + DEPLOY_STAGGER_S * self.rank:
                self._set_state("EXPLORING")
            return

        if s == "FAULT":
            self._fault_recovery()
            return

        if s == "REPLANNING":
            self._replanning()
            return

        if s == "WAITING_FOR_LINK":
            self.path = []
            if self.linked or self.mode != "baseline":
                self._set_state("EXPLORING")
            return
        if self.mode == "baseline" and self.dark_declared and s != "DONE":
            # without Deadzone: no link, no autonomy. Stop where the signal died and wait.
            self.path = []
            self._set_state("WAITING_FOR_LINK")
            self.events.append({"kind": "waiting_for_link", "robot": self.id})
            return

        if s in ("EXPLORING", "LOST_LINK_EXPLORING"):
            if self.dark_declared and s == "EXPLORING":
                self._set_state("LOST_LINK_EXPLORING")
            elif self.linked and s == "LOST_LINK_EXPLORING":
                self._set_state("EXPLORING")
            if self.state == "LOST_LINK_EXPLORING" and (dark_for > self.lost_budget or self.found_while_dark):
                self._set_state("RETURNING_TO_SIGNAL")
                if not self._plan_to_signal():
                    self._start_replan("no_route")
                return
            if self.battery.pct - self._pct_home() <= RESERVE_PCT:
                self.low_battery = True
                self._raise_fault("LOW_BATTERY")
                self._set_state("RETURNING_HOME")
                if not self._plan_to(self.entry):
                    self._start_replan("no_route")
                return
            if self._path_blocked():
                self._start_replan("obstacle")
                return
            if self._look_closer():                     # approaching an unsure hot spot
                return
            if not self.path or self.t - self.last_plan_t > REPLAN_PERIOD:
                if not self._plan_frontier():
                    self._set_state("RETURNING_HOME")   # nothing left to explore
                    if not self._plan_to(self.entry):
                        self._start_replan("no_route")
            return

        if s == "RETURNING_TO_SIGNAL":
            if self.linked:
                # hold until everything gathered in the dark has left the outbox (custody to the
                # next hop), at most LINK_HOLD_S after the link came back, then go back to work
                self.path = []
                since = self.reconnect_t if self.reconnect_t is not None else self.t
                backlog = any(b["created"] < since for b in self.outbox)
                if not backlog or self.t - since >= LINK_HOLD_S:
                    self._set_state("EXPLORING")
                return
            if self._path_blocked():
                self._start_replan("obstacle")
            elif not self.path:
                if len(self.crumbs) > 1:
                    self.crumbs.pop()
                if not self._plan_to(self.crumbs[-1]):
                    self._start_replan("no_route")
            return

        if s == "RETURNING_HOME":
            if math.dist(self.pose[:2], self.entry) < 0.6:
                self.path = []
                self._set_state("DONE")
            elif self._path_blocked():
                self._start_replan("obstacle")
            elif not self.path and not self._plan_to(self.entry):
                self._start_replan("no_route")
            return

        if s == "HOLDING":
            self.path = []                   # stays put; still maps, perceives and reports
            return

        if s == "GOING_TO_POINT":
            if self.battery.pct - self._pct_home() <= RESERVE_PCT:
                self.low_battery = True
                self._raise_fault("LOW_BATTERY")
                self.goto = None
                self._set_state("RETURNING_HOME")
                if not self._plan_to(self.entry):
                    self._start_replan("no_route")
            elif math.dist(self.pose[:2], self.goto) < 0.6:
                self.path, self.goto = [], None
                self._set_state("HOLDING")
            elif self._path_blocked():
                self._start_replan("obstacle")
            elif not self.path and not self._plan_to(self.goto):
                self._start_replan("no_route")
            return

    # ------------------------------------------------------------------ replanning
    def _start_replan(self, reason):
        """Stop, mark REPLANNING, and replan for whatever we were doing.

        Anti flip-flop: an obstacle seen again within REPLAN_COOLDOWN_S of the last replan (the
        map is still settling, e.g. a rubble corner coming into view) is handled by an immediate
        silent replan with no stop and no state change. Only if that fails do we stop and show
        REPLANNING."""
        if self.state in ("DEPLOYING", "DONE"):
            return
        if (reason == "obstacle" and self.state != "REPLANNING"
                and self.t - self.last_replan_done_t < REPLAN_COOLDOWN_S):
            ok, resume = self._plan_for(self.state)
            if ok and resume == self.state:
                return
        if self.state != "REPLANNING":
            self.resume_state = self.state
            self.counters["replans"] += 1
            self.events.append({"kind": "replan", "robot": self.id, "reason": reason})
        self.path = []
        self._set_state("REPLANNING")

    def _plan_for(self, state):
        """Plan for what `state` is doing. Returns (ok, state to resume)."""
        if state in ("EXPLORING", "LOST_LINK_EXPLORING"):
            if self._plan_frontier():
                return True, state
            if self._plan_to(self.entry):
                return True, "RETURNING_HOME"      # nothing reachable left to explore
            return False, state
        if state == "RETURNING_TO_SIGNAL":
            return self._plan_to_signal(), state
        if state == "GOING_TO_POINT" and self.goto is not None:
            return self._plan_to(self.goto), state
        return self._plan_to(self.entry), state

    def _replanning(self):
        if self.t - self.state_since < REPLAN_PAUSE_S:
            return
        if self.replan_fail_since is not None and self.t - self.last_plan_t < REPLAN_PERIOD:
            return   # throttle retries while no route exists
        ok, resume = self._plan_for(self.resume_state or "EXPLORING")
        if ok:
            self.last_replan_done_t = self.t
            self.replan_fail_since = None
            if self.fault in ("TRAPPED", "OVERCURRENT", "STUCK"):
                self._clear_fault()   # recovered
            self._set_state(resume)
            return
        if self.replan_fail_since is None:
            self.replan_fail_since = self.t
        elif self.t - self.replan_fail_since >= TRAPPED_AFTER_S and self.fault != "TRAPPED":
            self._raise_fault("TRAPPED")

    def _plan_to_signal(self):
        """A* back to the newest breadcrumb we can still reach (older ones if rubble cut us off).
        Crumbs are only dropped once an older one works, so being trapped never erases them."""
        for k in range(1, min(5, len(self.crumbs)) + 1):
            if self._plan_to(self.crumbs[-k]):
                del self.crumbs[len(self.crumbs) - k + 1:]
                return True
        return False

    # ------------------------------------------------------------------ planning
    def _cell(self, x, y):
        return int(x // self.cell), int(y // self.cell)

    def _trav(self):
        return planning.traversable(self.map.grid, self.nogo)

    def _drive_trav(self):
        """Where this robot may drive: traversable, minus a disk around every survivor it has
        confirmed, so it never runs a person over. Rescue routes still use _trav (they have
        to reach the survivor). The robot's own cell stays open so it can always leave."""
        trav = self._trav()
        if not self.found:
            return trav
        trav = trav.copy()
        r = int(math.ceil(SURVIVOR_CLEAR_M / self.cell))
        ys, xs = np.ogrid[-r:r + 1, -r:r + 1]
        disk = xs * xs + ys * ys <= r * r
        h, w = trav.shape
        mx, my = self._cell(*self.pose[:2])
        keep = trav[my, mx] if 0 <= mx < w and 0 <= my < h else None
        for rec in self.found.values():
            cx, cy = self._cell(*rec["pos"])
            x0, x1, y0, y1 = max(0, cx - r), min(w, cx + r + 1), max(0, cy - r), min(h, cy + r + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            sub = disk[y0 - (cy - r):y1 - (cy - r), x0 - (cx - r):x1 - (cx - r)]
            trav[y0:y1, x0:x1] &= ~sub
        if keep is not None:
            trav[my, mx] = keep
        return trav

    def _plan_frontier(self):
        if self.explorer is not None:
            result = self.explorer.plan(self.map.grid, self._drive_trav(), self.pose, self.t, self.path,
                                        self._active_zone(), self._claimed_targets())
            self.last_plan_t = self.t
            if result is None:
                return False
            old = self.target
            self.path, self.goal_cell = result
            self.target = [(v + .5) * self.cell for v in self.goal_cell]
            if old is None or math.dist(old, self.target) > PEER_TARGET_RADIUS:
                self.last_telemetry_t = -99.0
            return True
        trav = self._drive_trav()
        start = self._cell(*self.pose[:2])
        clusters, _, start = planning.frontier_clusters(self.map.grid, trav, start, self.blacklist)
        self.last_plan_t = self.t
        if not clusters:
            return False
        claimed = self._claimed_targets()

        # dispatched zone: while frontiers touch our zone, pick only among them; before the
        # zone shows up on our map, pull toward it; once it is mapped, help anywhere
        zone = self._active_zone()
        pull = None
        if zone is not None:
            inside = [c for c in clusters if any(zone["near"][y, x] for x, y in c["cells"])]
            if inside:
                clusters = inside
            else:
                pull = zone["center"]

        # score: prefer big frontiers that are close, keep going the same way,
        # stay away from frontiers a higher-priority peer already claimed
        def score(c):
            s = min(c["size"], 40) * 0.25 - c["dist"] * self.cell * 1.0
            if self.goal_cell and abs(c["goal"][0] - self.goal_cell[0]) + abs(c["goal"][1] - self.goal_cell[1]) < 8:
                s += 2.0
            gx, gy = (c["goal"][0] + 0.5) * self.cell, (c["goal"][1] + 0.5) * self.cell
            if any(math.dist((gx, gy), t) < PEER_TARGET_RADIUS for t in claimed):
                s -= PEER_TARGET_PENALTY
            if pull is not None:
                per_m = VOICE_ZONE_PULL_PER_M if zone["id"].startswith("voice:") else ZONE_PULL_PER_M
                s -= per_m * math.dist((gx, gy), pull)
            return s
        clusters.sort(key=score, reverse=True)
        for c in clusters[:4]:
            cells = planning.astar(trav, start, c["goal"], planning.wall_cost(self.map.grid))
            if cells:
                old = self.target
                self.goal_cell = c["goal"]
                self.path = planning.simplify(cells, self.cell)
                self.target = list(self.path[-1])
                if old is None or math.dist(old, self.target) > PEER_TARGET_RADIUS:
                    self.last_telemetry_t = -99.0   # announce the new claim on this tick
                return True
            self.blacklist.append(c["goal"])
        return False

    def _plan_to(self, xy):
        trav = self._drive_trav()
        cells = planning.astar(trav, self._cell(*self.pose[:2]), self._cell(*xy), planning.wall_cost(self.map.grid))
        self.last_plan_t = self.t
        if cells:
            self.path = planning.simplify(cells, self.cell)
            self.target = list(xy)
            return True
        self.path = []
        return False

    def _path_blocked(self):
        """True when the next PATH_CHECK_M of path, sampled every half cell, leaves the
        inflated traversable area of our own map (a new wall, rubble or no-go seen on it)."""
        if not self.path:
            return False
        trav = self._drive_trav()
        pts = [tuple(self.pose[:2])] + [tuple(p) for p in self.path]
        along = 0.0
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            seg = math.dist((ax, ay), (bx, by))
            n = max(1, int(seg / (self.cell / 2)))
            for k in range(1, n + 1):
                d = along + seg * k / n
                if d < PATH_CHECK_SKIP_M:
                    continue
                if d > PATH_CHECK_M:
                    return False
                ix, iy = self._cell(ax + (bx - ax) * k / n, ay + (by - ay) * k / n)
                if 0 <= ix < self.map.w and 0 <= iy < self.map.h and not trav[iy, ix]:
                    return True
            along += seg
        return False

    def _pct_home(self):
        """Battery % needed to drive home along the A* path on our own map (x 1.25 margin
        inside pct_to_drive). Refreshed every HOME_COST_PERIOD s because A* is not free.
        Falls back to straight line x 1.6 when our map has no known route yet."""
        if self.t - self.home_t >= HOME_COST_PERIOD:
            self.home_t = self.t
            cells = planning.astar(self._trav(), self._cell(*self.pose[:2]), self._cell(*self.entry))
            if cells:
                pts = [((cx + 0.5) * self.cell, (cy + 0.5) * self.cell) for cx, cy in cells]
                self.home_m = planning.path_length(pts) + math.dist(pts[-1], self.entry)
            else:
                self.home_m = 1.6 * math.dist(self.pose[:2], self.entry)
            self.home_pct = Battery.pct_to_drive(self.home_m)
        return self.home_pct

    # ------------------------------------------------------------------ motion
    def _follow(self):
        x, y, th = self.pose
        if self.explorer is not None and self.state in ("EXPLORING", "LOST_LINK_EXPLORING"):
            if self.explorer.scan_left > .05 and self.t < self.explorer.scan_deadline:
                return 0.0, 1.8
            trav = self._drive_trav()     # same mask the path was planned on: never shortcut across a person
            while self.path and math.dist(self.path[0], (x, y)) < .35:
                if (len(self.path) > 1 and math.dist(self.path[0], (x, y)) > .1
                        and not line_clear(trav, (x, y), self.path[1], self.cell)):
                    break
                self.path.pop(0)
            # A visible shortcut advances the path permanently. Merely aiming at
            # path[1] near a distance threshold makes the target flip back and
            # forth around a bend as the robot crosses that threshold.
            while (len(self.path) > 1 and math.dist(self.path[0], (x, y)) < 1.0
                   and line_clear(trav, (x, y), self.path[1], self.cell)):
                self.path.pop(0)
            if not self.path:
                return 0.0, 0.0
            tx, ty = self.path[0]
            err = wrap_angle(math.atan2(ty - y, tx - x) - th)
            v = 0.0 if abs(err) > 1 else V_MAX * math.cos(err)**2
            return v, max(-2.0, min(2.0, 2.5 * err))
        while self.path and math.dist(self.path[0], (x, y)) < 0.35:
            self.path.pop(0)
        if not self.path:
            return 0.0, 0.0
        tx, ty = self.path[0]
        if len(self.path) > 1 and math.dist((tx, ty), (x, y)) < 0.6:
            tx, ty = self.path[1]
        err = wrap_angle(math.atan2(ty - y, tx - x) - th)
        w = max(-2.0, min(2.0, 2.5 * err))
        v = 0.0 if abs(err) > 1.0 else V_MAX * math.cos(err) ** 2
        return v, w

    # ------------------------------------------------------------------ comms
    def _emit_bundles(self):
        if self.t - self.last_telemetry_t < TELEMETRY_PERIOD:
            return
        self.last_telemetry_t = self.t
        self.outbox.append(make_bundle(self.id, "CMD", "telemetry", {
            "id": self.id,
            "pose": [round(v, 2) for v in self.pose],
            "state": self.state,
            "battery_pct": round(self.battery.pct, 1),
            "found": list(self.found),
            "target": [round(v, 2) for v in self.target] if self.target else None,
            "relays": [list(p) for p in self.my_relays],
        }, self.t, 120))
        ix, iy, vals = self.map.take_patch()
        if len(vals):
            self.outbox.append(make_bundle(self.id, "CMD", "map_patch",
                                           {"robot": self.id, "ix": ix, "iy": iy, "v": vals},
                                           self.t, 64 + 5 * len(vals)))

    # ------------------------------------------------------------------ telemetry for the Reality view
    def telemetry(self, link):
        x, y, th = self.pose
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "pose": [round(x, 3), round(y, 3), round(th, 3)],
            "v": round(self.v, 2),
            "state": self.state,
            "mode": self.mode,
            "battery": {"pct": round(self.battery.pct, 1), "wh": round(self.battery.wh, 1),
                        "reserve_needed_pct": round(RESERVE_PCT + self._pct_home(), 1)},
            "link": link,
            "relays_left": self.relays_left,
            "plan_id": self.plan.get("plan_id") if self.plan else None,
            "zone": (self._active_zone() or {}).get("id"),
            "target": self.target,
            "path": [[round(px, 2), round(py, 2)] for px, py in self.path[:60]],
            "lidar": self.lidar_pts,
            "fault": self.fault,
            "wheel_a": round(self.wheel_a, 2),
            "tasks": self.tasks,
            "outbox": len(self.outbox),
            "last_link_t": round(self.last_link_t, 1),
        }
