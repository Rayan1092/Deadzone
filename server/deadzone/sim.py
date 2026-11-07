"""Fixed-tick simulation. Owns the truth and wires robots, network and command post."""
import base64
import math
import random
from pathlib import Path

import numpy as np

from .command.post import CommandPost
from .floorplan import FloorPlan, OCC, NOGO
from .geometry import wrap_angle
from .network.dtn import drain_outbox
from .network.propagation import LinkGraph, throughput_bps
from .robot.lidar import raycast
from .robot.robot import Robot

DT = 0.1
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = ROOT / "data" / "floorplans" / "collapse_01.json"

ROBOT_DEFS = [
    ("R1", "Scout 1", "#2dd4bf"),
    ("R2", "Scout 2", "#38bdf8"),
    ("R3", "Scout 3", "#a78bfa"),
]
THERMAL_RANGE = 5.0
THERMAL_FOV = math.radians(120)


class RadioIO:
    def __init__(self, sim, rid):
        self.sim, self.rid = sim, rid

    def cmd_reachable(self):
        return self.sim.links.path(self.rid, "CMD") is not None

    def neighbors(self):
        return self.sim.links.neighbors(self.rid)


class RobotIO:
    """The only door between robot software and the world."""

    def __init__(self, sim, rid):
        self.sim, self.rid = sim, rid
        self.radio = RadioIO(sim, rid)

    @property
    def time(self):
        return self.sim.time

    def lidar(self):
        b = self.sim.bodies[self.rid]
        return raycast(self.sim.fp.occ, self.sim.fp.cell, (b["x"], b["y"], b["th"]))

    def odometry(self):
        b = self.sim.bodies[self.rid]
        return {"pose": (b["x"], b["y"], b["th"]), "v": b["v"], "blocked": b["blocked"]}

    def drive(self, v, w):
        b = self.sim.bodies[self.rid]
        b["cmd_v"], b["cmd_w"] = v, w

    def thermal(self):
        """Survivors in the forward camera cone with line of sight (sim sensor fallback)."""
        b = self.sim.bodies[self.rid]
        out = []
        for s in self.sim.fp.data.get("survivors", []):
            sx, sy = s["pos"]
            d = math.dist((b["x"], b["y"]), (sx, sy))
            if d > THERMAL_RANGE:
                continue
            bearing = wrap_angle(math.atan2(sy - b["y"], sx - b["x"]) - b["th"])
            if abs(bearing) > THERMAL_FOV / 2:
                continue
            if self.sim.line_of_sight((b["x"], b["y"]), (sx, sy)):
                out.append({"id": s["id"], "pos": (sx, sy), "crop": s.get("thermal"), "conf": 0.99})
        return out


class Sim:
    def __init__(self, plan_path=DEFAULT_PLAN, n_robots=1, seed=7):
        self.plan_path = plan_path
        self.n_robots = n_robots
        self.seed = seed
        self.reset()

    def reset(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        self.fp = FloorPlan.load(self.plan_path)
        self.time = 0.0
        self.tick_n = 0
        self.links = LinkGraph()
        self.post = CommandPost(self.fp)
        self.events = []
        self.robots, self.bodies, self.ios = {}, {}, {}
        ex, ey = self.fp.entry
        for i, (rid, name, color) in enumerate(ROBOT_DEFS[: self.n_robots]):
            pose = (ex + 0.2, ey - 0.8 + 0.8 * i, 0.0)
            self.bodies[rid] = {"x": pose[0], "y": pose[1], "th": pose[2], "v": 0.0,
                                "cmd_v": 0.0, "cmd_w": 0.0, "blocked": False}
            self.robots[rid] = Robot(rid, name, color, pose, (self.fp.h, self.fp.w), self.fp.cell,
                                     self.fp.entry, nogo=self.fp.nogo.copy())
            self.ios[rid] = RobotIO(self, rid)
        self._update_links()

    # ------------------------------------------------------------------ physics + world
    def line_of_sight(self, p, q):
        n = int(math.dist(p, q) / (self.fp.cell / 2)) + 1
        for k in range(1, n):
            x = p[0] + (q[0] - p[0]) * k / n
            y = p[1] + (q[1] - p[1]) * k / n
            ix, iy = self.fp.to_cell(x, y)
            if not self.fp.in_bounds(ix, iy) or self.fp.occ[iy, ix]:
                return False
        return True

    def _integrate(self, b, dt):
        th = wrap_angle(b["th"] + b["cmd_w"] * dt)
        nx = b["x"] + b["cmd_v"] * math.cos(th) * dt
        ny = b["y"] + b["cmd_v"] * math.sin(th) * dt
        ix, iy = self.fp.to_cell(nx, ny)
        blocked = (not self.fp.in_bounds(ix, iy)) or bool(self.fp.occ[iy, ix])
        b["th"] = th
        b["blocked"] = blocked and b["cmd_v"] > 0
        if not blocked:
            b["v"] = math.dist((nx, ny), (b["x"], b["y"])) / dt
            b["x"], b["y"] = nx, ny
        else:
            b["v"] = 0.0

    def _nodes(self):
        nodes = {"CMD": (*self.fp.cmd_pos, self.fp.cmd_tx, True)}
        for rid, b in self.bodies.items():
            nodes[rid] = (b["x"], b["y"], 20.0, True)
        return nodes

    def _update_links(self):
        for a, b, change in self.links.update(self.fp, self._nodes()):
            self.events.append({"kind": "link_up" if change == "up" else "link_down", "a": a, "b": b})

    # ------------------------------------------------------------------ tick
    def tick(self):
        dt = DT
        self.time = round(self.time + dt, 3)
        self.tick_n += 1
        fresh = {}
        for rid, robot in self.robots.items():
            n0 = len(robot.outbox)
            robot.step(dt, self.ios[rid])
            fresh[rid] = robot.outbox[n0:]   # step only appends, so these are this tick's bundles
            self.events.extend(robot.events)
            robot.events.clear()
        for b in self.bodies.values():
            self._integrate(b, dt)
        self._update_links()
        self._share_telemetry(fresh)
        self._move_bundles(dt)
        self.events.extend(self.post.events)
        self.post.events.clear()

    def _share_telemetry(self, fresh):
        """TEMPORARY shim (Rayan, task 1, approved): robot-to-robot telemetry so robots can
        share frontier targets. Every robot with a link path to the sender gets a copy in its
        inbox. Robots never forward for other robots (team decision), so a path only counts if
        every intermediate hop is a non-robot node (relay, phone, CMD).
        Person 2 replaces this with dst = robot id / broadcast bundles in network/dtn.py."""
        for src, bundles in fresh.items():
            for b in bundles:
                if b["kind"] != "telemetry":
                    continue
                for rid, other in self.robots.items():
                    path = self.links.path(src, rid) if rid != src else None
                    if path and not any(n in self.robots for n in path[1:-1]):
                        other.inbox.append(dict(b, dst=rid, hops=path, custodian=rid))

    def _move_bundles(self, dt):
        """Single-hop store and forward for the first milestone (multi-hop at 5 PM)."""
        for rid, robot in self.robots.items():
            path = self.links.path(rid, "CMD")
            if not path or not robot.outbox:
                continue
            worst = min(self.links.link_rssi(path[i], path[i + 1]) for i in range(len(path) - 1))
            for bundle in drain_outbox(robot.outbox, throughput_bps(worst) * dt, self.time):
                bundle["hops"] = path
                bundle["custodian"] = "CMD"
                self.post.receive(bundle, self.time)

    # ------------------------------------------------------------------ views
    def reality_map(self):
        m = np.zeros((self.fp.h, self.fp.w), dtype=np.uint8)
        for r in self.robots.values():
            g = r.map.grid
            m = np.where(g > m, g, m)   # OCC (2) beats FREE (1) beats UNKNOWN (0)
        return m

    def snapshot(self):
        robots = []
        for rid, r in self.robots.items():
            path = self.links.path(rid, "CMD")
            via = path[1] if path and len(path) > 1 else None
            rssi = self.links.link_rssi(rid, via) if via else max(
                [x[1] for x in self.links.neighbors(rid)] + [self.links.link_rssi(rid, "CMD")])
            link = {"up": path is not None, "via": via, "rssi": round(rssi, 1),
                    "to_cmd_hops": len(path) - 1 if path else None}
            robots.append(r.telemetry(link))
        found = [rec for r in self.robots.values() for rec in r.found.values()]
        links = self.links.as_list()
        reality = {"robots": robots, "relays": [], "links": links, "survivors_found": found}
        stats = {"robots": len(self.robots), "relays": 0, "links_up": sum(1 for l in links if l["up"]),
                 "delivered": self.post.delivered, "in_flight": sum(len(r.outbox) for r in self.robots.values())}
        return {"reality": reality, "command": self.post.view(self.time), "stats": stats}

    def maps(self):
        cmd = self.post.map.copy()
        return {
            "w": self.fp.w, "h": self.fp.h, "cell": self.fp.cell,
            "reality": base64.b64encode(self.reality_map().tobytes()).decode(),
            "command": base64.b64encode(cmd.tobytes()).decode(),
        }

    def hello(self):
        return {
            "floorplan": self.fp.data,
            "grid": {"w": self.fp.w, "h": self.fp.h, "cell": self.fp.cell},
            "robots": [{"id": r.id, "name": r.name, "color": r.color} for r in self.robots.values()],
        }

    def drain_events(self):
        ev, self.events = self.events, []
        return ev

    # ------------------------------------------------------------------ director
    def drop_rubble(self, at, size=1.4):
        x, y = at
        s = size / 2
        poly = [[x - s, y - s], [x + s, y - s], [x + s, y + s], [x - s, y + s]]
        self.fp.add_rubble(poly)
        self.fp.data.setdefault("rubble", []).append({"id": f"RBX{len(self.fp.data['rubble'])}",
                                                       "poly": poly, "height": 1.0, "dynamic": True})
        self.events.append({"kind": "rubble_fall", "poly": poly})
