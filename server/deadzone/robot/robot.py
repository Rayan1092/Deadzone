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
                self.peers[p["id"]] = {"target": p.get("target"), "pose": p.get("pose"), "t": b["created"]}
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
        reachable = io.radio.cmd_reachable()
        x, y, _ = self.pose
        if reachable:
            self.last_link_t = self.t
            if math.dist(self.crumbs[-1], (x, y)) > CRUMB_SPACING:
                self.crumbs.append((x, y))
                self.crumbs = self.crumbs[-200:]
        self.linked = reachable

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
                self._replan_now()
            else:
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

        if s in ("EXPLORING", "LOST_LINK_EXPLORING"):
            if dark_for > LINK_LOST_AFTER and s == "EXPLORING":
                self._set_state("LOST_LINK_EXPLORING")
                self.found_while_dark = False
                self.events.append({"kind": "link_lost", "robot": self.id})
            elif self.linked and s == "LOST_LINK_EXPLORING":
                self._set_state("EXPLORING")
                self.events.append({"kind": "link_restored", "robot": self.id})
            if self.state == "LOST_LINK_EXPLORING" and (dark_for > self.lost_budget or self.found_while_dark):
                self._set_state("RETURNING_TO_SIGNAL")
                self._plan_to(self.crumbs[-1])
                return
            if self.battery.pct - self._pct_home() <= RESERVE_PCT:
                self._set_state("RETURNING_HOME")
                self._plan_to(self.entry)
                return
            need = (not self.path or self.t - self.last_plan_t > REPLAN_PERIOD or self._path_blocked())
            if need:
                if not self._plan_frontier():
                    self._set_state("RETURNING_HOME")
                    self._plan_to(self.entry)
            return

        if s == "RETURNING_TO_SIGNAL":
            if self.linked:
                # hold position until the backlog is uploaded, then go back to work
                self.path = []
                if not self.outbox or self.t - self.state_since > 20.0:
                    self._set_state("EXPLORING")
                    self.events.append({"kind": "link_restored", "robot": self.id})
                return
            if not self.path:
                if len(self.crumbs) > 1:
                    self.crumbs.pop()
                self._plan_to(self.crumbs[-1])
            return

        if s == "RETURNING_HOME":
            if math.dist(self.pose[:2], self.entry) < 0.6:
                self.path = []
                self._set_state("DONE")
            elif not self.path or self._path_blocked():
                self._plan_to(self.entry)
            return

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

    def _replan_now(self):
        self.path = []
        self.events.append({"kind": "replan", "robot": self.id})

    def _path_blocked(self):
        from ..floorplan import OCC
        for px, py in self.path[:8]:
            ix, iy = self._cell(px, py)
            if self.map.grid[iy, ix] == OCC:
                self.events.append({"kind": "replan", "robot": self.id})
                return True
        return False

    def _pct_home(self):
        # cheap estimate for now: straight line x 1.6. A* length lands with the battery work at 6 PM.
        return Battery.pct_to_drive(1.6 * math.dist(self.pose[:2], self.entry))

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
            "relays_left": 0,
            "target": self.target,
            "path": [[round(px, 2), round(py, 2)] for px, py in self.path[:60]],
            "lidar": self.lidar_pts,
            "fault": self.fault,
            "tasks": [],
            "outbox": len(self.outbox),
            "last_link_t": round(self.last_link_t, 1),
        }
