"""Robot onboard software. Everything here only sees the world through `io`.

States: DEPLOYING, EXPLORING, LOST_LINK_EXPLORING, RETURNING_TO_SIGNAL,
RETURNING_HOME, REPLANNING, FAULT, DONE
"""
import math

import numpy as np

from ..geometry import wrap_angle
from ..network.dtn import make_bundle
from . import planning
from .mapping import OccupancyMap
from .power import Battery, RESERVE_PCT

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
PATH_CHECK_SKIP_M = 0.4    # ignore the robot's own footprint (it may sit in a wall's inflation)
REPLAN_PAUSE_S = 0.6       # stop briefly in REPLANNING so the replan is visible and the map settles
TRAPPED_AFTER_S = 10.0     # no route for this long raises a TRAPPED fault to the command post


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
        self.found_while_dark = False
        self.dark_declared = False   # link_lost raised for the current outage
        self.reconnect_t = None      # when the link last came back after an outage
        self.resume_state = None     # state to go back to after REPLANNING
        self.replan_fail_since = None

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

    # ------------------------------------------------------------------ main step
    def step(self, dt, io):
        self.t = io.time
        odo = io.odometry()
        self.pose = list(odo["pose"])
        x, y, th = self.pose

        angles, ranges, hits = io.lidar()
        self.map.integrate(self.pose, angles, ranges, hits)
        self.lidar_pts = [[round(x + math.cos(a) * r, 2), round(y + math.sin(a) * r, 2)]
                          for a, r in zip(angles[::2], ranges[::2])]

        self._read_inbox()
        self._perceive(io)
        self._update_link(io)
        self._maybe_drop_relay(io)
        self._check_faults(odo)
        self._behave()
        v, w = self._follow()
        io.drive(v, w)
        self.cmd_v = v
        self.v = odo["v"]
        self.battery.drain(dt * BATTERY_TIME_SCALE, self.v)
        self._emit_bundles()

    # ------------------------------------------------------------------ comms in
    def _read_inbox(self):
        """Learn peer targets from telemetry bundles the network delivered to us."""
        for b in self.inbox:
            p = b["payload"]
            if b["kind"] != "telemetry" or p.get("id") == self.id:
                continue
            prev = self.peers.get(p["id"])
            if prev is None or prev["t"] <= b["created"]:
                self.peers[p["id"]] = {"target": p.get("target"), "pose": p.get("pose"),
                                       "relays": p.get("relays", []), "t": b["created"]}
        self.inbox.clear()

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
        for s in io.thermal():
            if s["id"] in self.found:
                continue
            rec = {"id": s["id"], "pos": [round(s["pos"][0], 2), round(s["pos"][1], 2)],
                   "by": self.id, "t": round(self.t, 1), "conf": s.get("conf", 0.99)}
            self.found[s["id"]] = rec
            if not self.linked:
                self.found_while_dark = True
            self.outbox.append(make_bundle(self.id, "CMD", "survivor", rec, self.t, 400))
            self.events.append({"kind": "survivor_found", "robot": self.id, "survivor": s["id"],
                                "pos": rec["pos"], "linked": self.linked})

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
        if self.nogo[iy, ix]:
            return
        try:
            io.drop_relay()
        except ValueError:
            return   # the deployer refused this spot, try again further along
        self.relays_left -= 1
        self.my_relays.append([round(x, 2), round(y, 2)])
        self.last_telemetry_t = -99.0   # tell peers right away so they keep their spacing

    def _check_faults(self, odo):
        """First pass. The full fault FSM (overcurrent, stuck, low battery) lands at 10 PM."""
        x, y, _ = self.pose
        rx, ry, rt = self.stuck_ref
        if self.t - rt > 3.0:
            moved = math.dist((x, y), (rx, ry))
            if self.cmd_v > 0.2 and moved < 0.05 and self.state not in ("DONE",):
                self.fault = "STUCK"
                self.events.append({"kind": "fault", "robot": self.id, "fault": "STUCK"})
                self._block_ahead()
                self._start_replan("stuck")
            elif self.fault == "STUCK":
                self.fault = None
            self.stuck_ref = (x, y, self.t)
        if odo.get("blocked"):
            self._block_ahead()

    def _block_ahead(self):
        x, y, th = self.pose
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

        if s == "REPLANNING":
            self._replanning()
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
                self._set_state("RETURNING_HOME")
                if not self._plan_to(self.entry):
                    self._start_replan("no_route")
                return
            if self._path_blocked():
                self._start_replan("obstacle")
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

    # ------------------------------------------------------------------ replanning
    def _start_replan(self, reason):
        """Stop, mark REPLANNING, and replan for whatever we were doing."""
        if self.state in ("DEPLOYING", "DONE"):
            return
        if self.state != "REPLANNING":
            self.resume_state = self.state
            self.events.append({"kind": "replan", "robot": self.id, "reason": reason})
        self.path = []
        self._set_state("REPLANNING")

    def _replanning(self):
        if self.t - self.state_since < REPLAN_PAUSE_S:
            return
        if self.replan_fail_since is not None and self.t - self.last_plan_t < REPLAN_PERIOD:
            return   # throttle retries while no route exists
        resume = self.resume_state or "EXPLORING"
        if resume in ("EXPLORING", "LOST_LINK_EXPLORING"):
            ok = self._plan_frontier()
            if not ok and self._plan_to(self.entry):
                ok, resume = True, "RETURNING_HOME"   # nothing reachable left to explore
        elif resume == "RETURNING_TO_SIGNAL":
            ok = self._plan_to_signal()
        else:
            ok = self._plan_to(self.entry)
        if ok:
            self.replan_fail_since = None
            if self.fault == "TRAPPED":
                self.fault = None
            self._set_state(resume)
            return
        if self.replan_fail_since is None:
            self.replan_fail_since = self.t
        elif self.t - self.replan_fail_since >= TRAPPED_AFTER_S and self.fault != "TRAPPED":
            self.fault = "TRAPPED"
            x, y, _ = self.pose
            rec = {"robot": self.id, "fault": "TRAPPED", "pos": [round(x, 2), round(y, 2)], "t": round(self.t, 1)}
            self.events.append({"kind": "fault", "robot": self.id, "fault": "TRAPPED"})
            self.outbox.append(make_bundle(self.id, "CMD", "fault", rec, self.t, 120))

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

    def _plan_frontier(self):
        trav = self._trav()
        start = self._cell(*self.pose[:2])
        clusters, _, start = planning.frontier_clusters(self.map.grid, trav, start, self.blacklist)
        self.last_plan_t = self.t
        if not clusters:
            return False
        claimed = self._claimed_targets()

        # score: prefer big frontiers that are close, keep going the same way,
        # stay away from frontiers a higher-priority peer already claimed
        def score(c):
            s = min(c["size"], 40) * 0.25 - c["dist"] * self.cell * 1.0
            if self.goal_cell and abs(c["goal"][0] - self.goal_cell[0]) + abs(c["goal"][1] - self.goal_cell[1]) < 8:
                s += 2.0
            gx, gy = (c["goal"][0] + 0.5) * self.cell, (c["goal"][1] + 0.5) * self.cell
            if any(math.dist((gx, gy), t) < PEER_TARGET_RADIUS for t in claimed):
                s -= PEER_TARGET_PENALTY
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
        trav = self._trav()
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
        trav = self._trav()
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
            "battery": {"pct": round(self.battery.pct, 1), "wh": round(self.battery.wh, 1),
                        "reserve_needed_pct": round(RESERVE_PCT + self._pct_home(), 1)},
            "link": link,
            "relays_left": self.relays_left,
            "target": self.target,
            "path": [[round(px, 2), round(py, 2)] for px, py in self.path[:60]],
            "lidar": self.lidar_pts,
            "fault": self.fault,
            "tasks": [],
            "outbox": len(self.outbox),
            "last_link_t": round(self.last_link_t, 1),
        }
