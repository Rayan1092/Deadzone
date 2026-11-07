"""Fixed-tick simulation. Owns the truth and wires robots, network and command post."""
import base64
import math
import random
from pathlib import Path

import numpy as np

from .command.post import CommandPost
from .command.safety import RobotSpec
from .floorplan import FloorPlan, OCC, NOGO
from .geometry import wrap_angle
from .network.dtn import DTNNetwork, RELAY_QUEUE_BYTES, make_bundle
from .network.propagation import LinkGraph
from .robot.lidar import raycast
from .robot.power import wheel_current
from .robot.robot import BATTERY_TIME_SCALE, PEER_FRESH_S, Robot

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
        return self.sim.radio_path(self.rid, "CMD") is not None

    def neighbors(self):
        return self.sim.links.neighbors(self.rid)

    def receive(self):
        """Consume all delivered robot messages, including legacy peer telemetry."""
        inbox = self.sim.inboxes[self.rid]
        peer_inbox = getattr(self.sim.robots[self.rid], "inbox", [])
        delivered = sorted([*inbox, *peer_inbox], key=lambda b: (b["prio"], b["created"], b["bid"]))
        inbox.clear()
        peer_inbox.clear()
        return delivered


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
        return {"pose": (b["x"], b["y"], b["th"]), "v": b["v"], "blocked": b["blocked"],
                "wheel_current": self.motor_current()}

    def motor_current(self):
        if self.sim.time < self.sim.overcurrent_until.get(self.rid, -1):
            return 8.0
        b = self.sim.bodies[self.rid]
        return wheel_current(b["cmd_v"], b["blocked"])

    def drive(self, v, w):
        b = self.sim.bodies[self.rid]
        b["cmd_v"], b["cmd_w"] = v, w

    def drop_relay(self):
        """Place a relay here; robot policy owns inventory and when to drop."""
        return self.sim.add_relay(self.odometry()["pose"][:2], owner=self.rid)

    def thermal(self):
        """Thermal hot spots in the forward camera cone; classification belongs to the robot."""
        b = self.sim.bodies[self.rid]
        out = []
        spots = [*self.sim.fp.data.get("survivors", []), *self.sim.fp.data.get("decoys", [])]
        for s in spots:
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
        self.prior = FloorPlan(self.fp.planning_data())
        self.robot_specs = {rid: RobotSpec() for rid, _, _ in ROBOT_DEFS[:self.n_robots]}
        self.energy_time_scale = BATTERY_TIME_SCALE
        self.time = 0.0
        self.tick_n = 0
        self.links = LinkGraph()
        self.network = DTNNetwork()
        self.network.register("CMD")
        self.relays = {}
        self.relay_revisions = {}
        self.overcurrent_until = {}
        self.inboxes = {}  # delivered robot commands, consumed by future robot IO
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
            self.network.register(rid, self.robots[rid].outbox, can_forward=False)
            self.inboxes[rid] = []
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
        for rid, relay in self.relays.items():
            nodes[rid] = (*relay["pos"], 20.0, relay["on"])
        return nodes

    def add_relay(self, pos, owner=None, phone=False):
        """Backend hook for the robot drop rule and future phone relay controls."""
        x, y = self._relay_position(pos)
        rid = f"RL{len(self.relays) + 1}"
        self.relays[rid] = {"id": rid, "pos": [x, y], "owner": owner, "on": True, "phone": bool(phone)}
        self.network.register(rid, capacity_bytes=RELAY_QUEUE_BYTES)
        self._relay_telemetry(rid)
        self.events.append({"kind": "relay_dropped", "id": rid, "pos": [x, y], "owner": owner})
        self._update_links()
        return rid

    def _relay_position(self, pos):
        x, y = map(float, pos)
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < self.fp.W and 0 <= y < self.fp.H):
            raise ValueError("Relay must be inside the floor plan")
        ix, iy = self.fp.to_cell(x, y)
        if self.fp.occ[iy, ix] or self.fp.nogo[iy, ix]:
            raise ValueError("Relay cannot be placed in an obstacle or no-go zone")
        return x, y

    def move_relay(self, rid, pos):
        x, y = self._relay_position(pos)
        self.relays[rid]["pos"] = [x, y]
        self._relay_telemetry(rid)
        self._update_links()

    def inject_overcurrent(self, rid, duration_s=1.0):
        if rid not in self.robots:
            raise ValueError(f"Unknown robot: {rid}")
        if not math.isfinite(duration_s) or not 0.6 <= duration_s <= 10:
            raise ValueError("Overcurrent duration must be 0.6 to 10 sim seconds")
        self.overcurrent_until[rid] = max(self.overcurrent_until.get(rid, 0), self.time + duration_s)
        # Rayan's timeline/fault contract provides this robot-owned recovery hook.
        # Legacy robot code still gets the injected IO sensor reading above.
        injector = getattr(self.robots[rid], "inject_overcurrent", None)
        if callable(injector):
            injector(seconds=self.overcurrent_until[rid] - self.time)
        self.events.append({"kind": "fault_injected", "type": "overcurrent", "robot": rid,
                            "until": self.overcurrent_until[rid]})
        return self.overcurrent_until[rid]

    def set_relay_power(self, rid, on):
        """Power changes break links without deleting the relay's stored bundles."""
        relay = self.relays[rid]
        if relay["on"] == bool(on):
            return
        relay["on"] = bool(on)
        if relay["on"]:
            self._relay_telemetry(rid)
        self._update_links()

    def _relay_telemetry(self, rid):
        self.relay_revisions[rid] = self.relay_revisions.get(rid, 0) + 1
        payload = dict(self.relays[rid], node_type="relay", revision=self.relay_revisions[rid])
        queue = self.network.queues[rid]
        # Dragging a relay while paused should not fill its queue with obsolete
        # positions. Never discard bundles carried for somebody else.
        queue[:] = [b for b in queue if not (b["src"] == rid and b["kind"] == "telemetry"
                                             and b["payload"].get("node_type") == "relay")]
        if sum(b["size"] for b in queue) + 160 <= RELAY_QUEUE_BYTES:
            queue.append(make_bundle(rid, "CMD", "telemetry", payload, self.time, 160))

    def _update_links(self):
        for a, b, change in self.links.update(self.fp, self._nodes()):
            self.events.append({"kind": "link_up" if change == "up" else "link_down", "a": a, "b": b})

    def radio_path(self, src, dst):
        """Robots are radio endpoints; only relays and CMD forward for peers."""
        return self.links.path(src, dst, avoid=set(self.robots) - {src, dst})

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
        self._queue_peer_telemetry(fresh)
        self._move_bundles(dt)
        self.events.extend(self.post.events)
        self.post.events.clear()

    def _queue_peer_telemetry(self, fresh):
        """Fan out reports before transport; disconnected peers wait in custody."""
        for rid, bundles in fresh.items():
            for b in bundles:
                if b["kind"] != "telemetry":
                    continue
                # Sample source-owned status once, before transport. Never fill
                # delayed Command reports from the robot's current live state.
                status = self.robots[rid].telemetry(None)
                for key in ("plan_id", "zone"):
                    b["payload"].setdefault(key, status.get(key))
                self.network.fanout_telemetry(b, self.robots, ttl=PEER_FRESH_S)

    def _move_bundles(self, dt):
        """Only destination deliveries may update a consumer's knowledge."""
        for bundle in self.network.step(self.links, dt, self.time):
            if bundle["dst"] == "CMD":
                if self.post.receive(bundle, self.time):
                    self.events.append({"kind": "bundle_delivered",
                        "src": bundle["src"], "dst": "CMD", "bundle_kind": bundle["kind"],
                        "hops": list(bundle["hops"]), "delay_s": round(self.time - bundle["created"], 3)})
            elif (bundle["kind"] == "telemetry" and bundle["dst"] in self.robots
                  and hasattr(self.robots[bundle["dst"]], "inbox")):
                # Compatibility for the current robot reader. IO.receive() can
                # consume this buffer too; if Rayan removes it, all messages use
                # the IO inbox below. No packet is copied into both buffers.
                self.robots[bundle["dst"]].inbox.append(bundle)
            else:
                self.inboxes.setdefault(bundle["dst"], []).append(bundle)

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
            path = self.radio_path(rid, "CMD")
            via = path[1] if path and len(path) > 1 else None
            rssi = self.links.link_rssi(rid, via) if via else max(
                [x[1] for x in self.links.neighbors(rid)] + [self.links.link_rssi(rid, "CMD")])
            link = {"up": path is not None, "via": via, "rssi": round(rssi, 1),
                    "to_cmd_hops": len(path) - 1 if path else None}
            robots.append(r.telemetry(link))
        found = [rec for r in self.robots.values() for rec in r.found.values()]
        links = self.links.as_list()
        relays = [dict(relay, queue=len(self.network.queues[rid])) for rid, relay in self.relays.items()]
        reality = {"robots": robots, "relays": relays, "links": links, "survivors_found": found}
        stats = {"robots": len(self.robots), "relays": len(relays),
                 "links_up": sum(1 for l in links if l["up"]),
                 "delivered": self.post.delivered, "in_flight": sum(map(len, self.network.queues.values()))}
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
