"""Fixed-tick simulation. Owns the truth and wires robots, network and command post."""
import base64
import json
import math
import os
import random
import re
from copy import deepcopy
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
from .robot.perception import get_detector
from .robot.robot import BATTERY_TIME_SCALE, PEER_FRESH_S, Robot
from .sensors import THERMAL_FOV, THERMAL_RANGE, camera_config

DT = 0.1
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = ROOT / "data" / "floorplans" / "collapse_01.json"

ROBOT_DEFS = [
    ("R1", "Scout 1", "#2dd4bf"),
    ("R2", "Scout 2", "#38bdf8"),
    ("R3", "Scout 3", "#a78bfa"),
]


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
        result = raycast(self.sim.fp.occ, self.sim.fp.cell, (b["x"], b["y"], b["th"]))
        self.sim.counters["lidar_scans"] += 1
        self.sim.counters["lidar_rays"] += len(result[0])
        return result

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
        self.sim.counters["drive_calls"] += 1
        b = self.sim.bodies[self.rid]
        b["cmd_v"], b["cmd_w"] = v, w

    def drop_relay(self, beacon_for=None):
        """Place a relay here; robot policy owns inventory and when to drop."""
        if beacon_for is not None and self.radio.cmd_reachable():
            return None  # survivor beacons are only dropped while dark
        return self.sim.add_relay(self.odometry()["pose"][:2], owner=self.rid, beacon_for=beacon_for)

    def thermal(self):
        """Thermal hot spots in the forward camera cone; classification belongs to the robot."""
        self.sim.counters["thermal_scans"] += 1
        b = self.sim.bodies[self.rid]
        out = []
        spots = list(self.sim.fp.data.get("survivors", []))
        if get_detector().mode == "model":
            spots.extend(self.sim.fp.data.get("decoys", []))
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
        self.sim.counters["thermal_hits"] += len(out)
        return out


class Sim:
    def __init__(self, plan_path=DEFAULT_PLAN, n_robots=1, seed=7):
        self.plan_path = plan_path
        self.n_robots = n_robots
        self.seed = seed
        self.reset()

    def reset(self):
        self.sensor_view = os.environ.get("DZ_SENSOR_VIEW") == "1"
        random.seed(self.seed)
        np.random.seed(self.seed)
        self.fp = FloorPlan.load(self.plan_path)
        self.prior = FloorPlan(self.fp.planning_data())
        self.robot_specs = {rid: RobotSpec() for rid, _, _ in ROBOT_DEFS[:self.n_robots]}
        self.energy_time_scale = BATTERY_TIME_SCALE
        self.time = 0.0
        self.tick_n = 0
        self.geometry_revision = 0
        self.timeline = None
        self.pending_aftershocks = []
        self.counters = {"aftershock_areas": 0, "survivor_detections": 0, "hotspots_rejected": 0,
                         "rescue_routes_computed": 0, "replans": 0, "faults_raised": 0,
                         "lidar_scans": 0, "lidar_rays": 0, "thermal_scans": 0, "thermal_hits": 0,
                         "drive_calls": 0}
        self.links = LinkGraph()
        self.network = DTNNetwork(fec_enabled=os.environ.get("DZ_FEC") == "1", seed=self.seed)
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

    def add_relay(self, pos, owner=None, phone=False, beacon_for=None):
        """Backend hook for the robot drop rule and future phone relay controls."""
        if beacon_for is not None and (not isinstance(beacon_for, str) or
                                       re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", beacon_for) is None):
            raise ValueError("beacon_for must be a survivor identifier or None")
        x, y = self._relay_position(pos)
        rid = f"RL{len(self.relays) + 1}"
        self.relays[rid] = {"id": rid, "pos": [x, y], "owner": owner, "on": True,
                            "phone": bool(phone), "beacon_for": beacon_for}
        self.network.register(rid, capacity_bytes=RELAY_QUEUE_BYTES)
        self._relay_telemetry(rid)
        self.events.append({"kind": "relay_dropped", "id": rid, "pos": [x, y], "owner": owner,
                            "beacon_for": beacon_for})
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
        if self.relays[rid].get("destroyed"):
            raise ValueError("Destroyed relay cannot be moved")
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
        if on and relay.get("destroyed"):
            raise ValueError("Destroyed relay cannot be powered on")
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
        size = max(160, len(json.dumps(payload, separators=(",", ":")).encode()) + 64)
        if sum(b["size"] for b in queue) + size <= RELAY_QUEUE_BYTES:
            queue.append(make_bundle(rid, "CMD", "telemetry", payload, self.time, size))

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
        if self.timeline is not None:
            self.timeline.apply_due(self)
        due = [item for item in self.pending_aftershocks if item["t"] <= self.time + 1e-6]
        self.pending_aftershocks = [item for item in self.pending_aftershocks if item not in due]
        for item in due:
            self.aftershock(item["at"], destroy_relay=False)
        fresh = {}
        for rid, robot in self.robots.items():
            n0 = len(robot.outbox)
            robot.step(dt, self.ios[rid])
            fresh[rid] = robot.outbox[n0:]   # step only appends, so these are this tick's bundles
            for event in robot.events:
                key = {"survivor_found": "survivor_detections", "hotspot_rejected": "hotspots_rejected",
                       "rescue_route": "rescue_routes_computed", "replan": "replans", "fault": "faults_raised"}.get(event["kind"])
                if key:
                    self.counters[key] += 1
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
            robot = r.telemetry(link)
            if self.sensor_view and r.camera_frame is not None:
                # Local instrument view only. Never put this in a radio bundle,
                # CommandPost, phone state or the Gemini tool surface.
                robot["camera"] = deepcopy(r.camera_frame)
            robots.append(robot)
        found = [rec for r in self.robots.values() for rec in r.found.values()]
        links = self.links.as_list()
        for link in links:
            edge = tuple(sorted((link["a"], link["b"])))
            link.update(self.network.link_stats.get(edge, {"corrupted_bytes": 0, "corrected_bytes": 0,
                                                         "fec_failed_blocks": 0}))
            link["fec"] = bool(self.network.fec_enabled and link["up"] and -88 <= self.links.link_rssi(*edge) <= -80)
        relays = [dict(relay, queue=len(self.network.queues[rid])) for rid, relay in self.relays.items()]
        reality = {"robots": robots, "relays": relays, "links": links, "survivors_found": found}
        stats = {"robots": len(self.robots), "relays": len(relays),
                 "links_up": sum(1 for l in links if l["up"]),
                 "delivered": self.post.delivered, "in_flight": sum(map(len, self.network.queues.values()))}
        stats.update(self.counters)
        stats.update(self.network.counters)
        stats.update(ticks=self.tick_n, sim_s=self.time,
                     command_delivery_hops=self.post.delivery_hops_total,
                     hops_per_delivery=round(self.post.delivery_hops_total / self.post.delivered, 3) if self.post.delivered else 0,
                     relays_destroyed=sum(bool(r.get("destroyed")) for r in self.relays.values()),
                     survivors_reported=len(self.post.survivors), rescue_routes_delivered=len(self.post.routes),
                     deadline_misses=sum(sum(r.scheduler.misses.values()) for r in self.robots.values()),
                     safety_deadline_misses=sum(r.scheduler.misses["safety"] for r in self.robots.values()),
                     exploration_searches=sum(r.explorer.searches for r in self.robots.values() if r.explorer is not None),
                     queued_bytes=sum(b["size"] for queue in self.network.queues.values() for b in queue),
                     timeline_events_played=self.timeline.played if self.timeline else 0,
                     timeline_events_failed=self.timeline.failed if self.timeline else 0,
                     timeline_events_total=len(self.timeline.events) if self.timeline else 0)
        # Rayan owns these instrumentation hooks. Omit incomplete totals rather than invent zeroes.
        for key in ("detector_calls", "detector_rejections", "scheduler_deadlines_met"):
            values = [robot.get("counters", {}).get(key) for robot in robots]
            if values and all(type(value) is int and value >= 0 for value in values):
                stats[key] = sum(values)
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
            **({"sensor_view": camera_config()} if self.sensor_view else {}),
            "floorplan": self.fp.data,
            "grid": {"w": self.fp.w, "h": self.fp.h, "cell": self.fp.cell},
            "robots": [{"id": r.id, "name": r.name, "color": r.color} for r in self.robots.values()],
        }

    def drain_events(self):
        ev, self.events = self.events, []
        return ev

    # ------------------------------------------------------------------ director
    def earthquake(self, strength="normal", at=None, relay=None):
        """Normal stays identical; strong adds two areas now and one at +10 sim s."""
        if strength not in ("normal", "strong"):
            raise ValueError("Unknown earthquake strength")
        if strength == "normal":
            return self.aftershock(at, relay)
        if self.pending_aftershocks:
            raise ValueError("Wait for the pending secondary collapse")
        if relay is not None and (relay not in self.relays or self.relays[relay].get("destroyed")):
            raise ValueError("Unknown or already destroyed relay")
        active = [rid for rid, r in self.relays.items() if r["on"] and not r["phone"] and not r.get("destroyed")]
        first = relay or next(iter(active), None)
        anchor = at if at is not None else self.relays[first]["pos"] if first else (min(22, self.fp.W-self.fp.cell), self.fp.H/2)
        x, y = map(float, anchor)
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < self.fp.W and 0 <= y < self.fp.H):
            raise ValueError("Aftershock must be inside the building")
        # Positions depend only on this world; no random draws alter robot/demo behavior.
        areas = [[x, y]]
        for fx, fy in ((.7, .3), (.3, .7), (.7, .7), (.3, .3), (.5, .5)):
            point = [self.fp.W*fx, self.fp.H*fy]
            if math.dist(point, self.fp.entry) > 3 and all(math.dist(point, p) > 3 for p in areas):
                areas.append(point)
            if len(areas) == 3:
                break
        if len(areas) < 3:
            raise ValueError("Building is too small for a strong earthquake")
        second = next((rid for rid in active if rid != first), None)
        events = [self.aftershock(areas[0], first),
                  self.aftershock(areas[1], second, destroy_relay=second is not None)]
        self.pending_aftershocks.append({"t": round(self.time+10, 3), "at": areas[2]})
        return {"strength": "strong", "areas": events, "secondary_at": round(self.time+10, 3)}

    def aftershock(self, at=None, relay=None, *, destroy_relay=True):
        """Apply one validated truth-only collapse; robots react through normal IO."""
        if relay is not None and (relay not in self.relays or self.relays[relay].get("destroyed")):
            raise ValueError("Unknown or already destroyed relay")
        if relay is None and destroy_relay:
            relay = next((rid for rid, r in self.relays.items() if r["on"] and not r["phone"]), None)
        if at is None:
            at = self.relays[relay]["pos"] if relay else (min(22, self.fp.W - self.fp.cell), self.fp.H / 2)
        x, y = map(float, at)
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < self.fp.W and 0 <= y < self.fp.H):
            raise ValueError("Aftershock must be inside the building")
        # Validate first, then mutate geometry/custody together without awaiting.
        x0, x1 = max(0, x - 1), min(self.fp.W, x + 1)
        y0, y1 = max(0, y - 1), min(self.fp.H, y + 1)
        poly = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        rubble = {"id": f"ASR{len(self.fp.data.get('rubble', [])) + 1}", "poly": poly,
                  "height": 1.5, "dynamic": True}
        wall = {"id": f"ASW{len(self.fp.data.get('dynamic_walls', [])) + 1}",
                "a": [max(0, x - 1.5), y1], "b": [min(self.fp.W, x + 1.5), y1],
                "material": "concrete", "dynamic": True}
        self.fp.add_rubble(poly)
        self.fp.data.setdefault("rubble", []).append(rubble)
        self.fp.add_wall(wall)
        self.geometry_revision += 1
        self.counters["aftershock_areas"] += 1
        self._invalidate_camera_frames()
        lost = 0
        if relay:
            node = self.relays[relay]
            node.update(on=False, destroyed=True)
            lost = self.network.destroy(relay)
            self.events.append({"kind": "relay_destroyed", "id": relay, "pos": list(node["pos"]),
                                "lost_bundles": lost})
        self.events.append({"kind": "rubble_fall", "poly": poly})
        event = {"kind": "aftershock", "at": [x, y], "rubble": [rubble], "walls": [wall],
                 "destroyed_relay": relay, "lost_bundles": lost}
        self.events.append(event)
        self._update_links()
        return event

    def drop_rubble(self, at, size=1.4):
        x, y = at
        s = size / 2
        poly = [[x - s, y - s], [x + s, y - s], [x + s, y + s], [x - s, y + s]]
        self.fp.add_rubble(poly)
        self.geometry_revision += 1
        self.fp.data.setdefault("rubble", []).append({"id": f"RBX{len(self.fp.data['rubble'])}",
                                                       "poly": poly, "height": 1.0, "dynamic": True})
        self._invalidate_camera_frames()
        self.events.append({"kind": "rubble_fall", "poly": poly})

    def _invalidate_camera_frames(self):
        """Changed world geometry needs a fresh IO sample, even while paused.

        Never manufacture a perception decision during a director action. The
        next normal robot step restores the frame from actual sensor input.
        """
        if self.sensor_view:
            for robot in self.robots.values():
                robot.camera_frame = None
