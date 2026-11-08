"""What the command post knows. Updated ONLY by bundles delivered through the network."""
from copy import deepcopy
from collections import OrderedDict, deque
import logging
import os

import numpy as np
from pydantic import ValidationError

from .rescue import RescueRoute
from .ack import CommandAck, STATUS_ORDER
from .camera import delivered_frame
from .coverage import CoverageGrid

log = logging.getLogger(__name__)


class CommandPost:
    def __init__(self, fp):
        self.size = fp.W, fp.H
        self.map = np.zeros((fp.h, fp.w), dtype=np.uint8)
        self.map_sent_t = np.full((fp.h, fp.w), -np.inf)
        self.robots = {}      # id -> last telemetry + last_seen
        self.heat_sources = os.environ.get("DZ_HEAT_SOURCES") == "1"
        self.camera_telemetry = os.environ.get("DZ_CAMERA_TELEMETRY") == "1" or self.heat_sources
        self.coverage_grid = CoverageGrid(fp) if os.environ.get("DZ_COVERAGE_GRID") == "1" else None
        self.relays = {}
        self.survivors = {}   # id -> record + reported_t
        self.faults = {}
        self.routes = {}      # survivor id -> latest delivered route
        self.command_acks = OrderedDict()  # bounded latest delivered decision per cmd_id
        self.delivered = 0
        self.delivery_hops_total = 0
        self.events = []
        # Bounded, delivered-only evidence for read-only briefings. Sim.events
        # contains Reality events and must never be passed to an AI tool.
        self.receipt_history = deque(maxlen=200)
        self.event_history = deque(maxlen=200)
        self._seen = {}

    def receive(self, b, now):
        if b["dst"] != "CMD" or b["custodian"] != "CMD" or now > b["created"] + b["ttl"]:
            return False
        self._seen = {bid: expiry for bid, expiry in self._seen.items() if now <= expiry}
        if b["bid"] in self._seen:
            return False
        route = None
        ack = None
        if b["kind"] == "command_ack":
            try:
                ack = CommandAck.model_validate(b["payload"])
            except ValidationError:
                log.warning("Rejected command_ack bundle %s: invalid payload", b["bid"])
                return False
            if (ack.robot != b["src"] or ack.t > now + .11
                    or (ack.issued_t is not None and ack.issued_t > ack.t + .11)):
                log.warning("Rejected command_ack bundle %s: source or timestamps invalid", b["bid"])
                return False
        if b["kind"] == "rescue_route":
            try:
                route = RescueRoute.model_validate(b["payload"])
            except ValidationError:
                log.warning("Rejected rescue_route bundle %s: invalid payload", b["bid"])
                return False
            if route.by != b["src"] or any(
                    not (0 <= x <= self.size[0] and 0 <= y <= self.size[1]) for x, y in route.path):
                log.warning("Rejected rescue_route bundle %s: source or coordinates invalid", b["bid"])
                return False
        self._seen[b["bid"]] = b["created"] + b["ttl"]
        self.delivered += 1
        self.delivery_hops_total += max(0, len(b["hops"]) - 1)
        event_start = len(self.events)
        p = b["payload"]
        k = b["kind"]
        if k == "telemetry" and p.get("node_type") == "relay":
            prev = self.relays.get(p["id"])
            version = b["created"], p.get("revision", 0)
            if prev is None or (prev["sent_t"], prev.get("revision", 0)) <= version:
                self.relays[p["id"]] = {"id": p["id"], "pos": list(p["pos"]), "sent_t": b["created"],
                                         "revision": version[1], "beacon_for": p.get("beacon_for")}
                if self.coverage_grid is not None:
                    self.coverage_grid.report_relay(p)
        elif k == "telemetry":
            prev = self.robots.get(p["id"])
            camera = prev.get("camera") if self.camera_telemetry and prev else None
            if prev is None or prev["sent_t"] <= b["created"]:
                self.robots[p["id"]] = {"id": p["id"], "pose": p["pose"], "state": p["state"],
                                        "battery_pct": p["battery_pct"], "last_seen": round(b["created"], 1),
                                        "sent_t": b["created"],
                                        "plan_id": p.get("plan_id"), "zone": p.get("zone")}
                if camera is not None:
                    self.robots[p["id"]]["camera"] = camera
            if self.camera_telemetry and p["id"] == b["src"] and "camera" in p:
                frame = delivered_frame(p["camera"], b["created"], now, self.size,
                                        heat_sources=self.heat_sources)
                if frame is not None and (camera is None or
                        (frame["t"], frame["delivered_t"]) >= (camera["t"], camera["delivered_t"])):
                    self.robots[p["id"]]["camera"] = frame
        elif k == "map_patch":
            fresh = self.map_sent_t[p["iy"], p["ix"]] <= b["created"]
            ix, iy = p["ix"][fresh], p["iy"][fresh]
            self.map[iy, ix] = p["v"][fresh]
            self.map_sent_t[iy, ix] = b["created"]
        elif k == "fault":
            robot = p["robot"]
            prev = self.faults.get(robot)
            if prev is None or prev["sent_t"] <= b["created"]:
                self.faults[robot] = dict(p, sent_t=b["created"], reported_t=round(now, 1))
        elif k == "rescue_route":
            prev = self.routes.get(route.survivor_id)
            if prev is None or prev["t"] < route.t:
                record = route.model_dump(mode="json", exclude={"survivor_id"})
                record.update(survivor=route.survivor_id, reported_t=round(now, 1),
                              beacon=route.beacon_id, clearance_m=route.clearance_m)
                self.routes[route.survivor_id] = record
                self.events.append({"kind": "rescue_route_reported", **deepcopy(record),
                                    "delay_s": round(now - route.t, 1)})
        elif k == "command_ack":
            prev = self.command_acks.get(ack.cmd_id)
            fresh = (prev is None or (
                prev["robot"] == ack.robot and prev["cmd"] == ack.cmd
                and prev["issued_t"] == ack.issued_t
                and STATUS_ORDER[ack.status] >= STATUS_ORDER[prev["status"]]
                and (ack.t, STATUS_ORDER[ack.status]) > (prev["t"], STATUS_ORDER[prev["status"]])))
            if fresh:
                record = ack.model_dump(mode="json") | {"reported_t": round(now, 1),
                                                       "delay_s": round(max(0, now - ack.t), 1)}
                self.command_acks[ack.cmd_id] = record
                self.command_acks.move_to_end(ack.cmd_id)
                while len(self.command_acks) > 256:
                    self.command_acks.popitem(last=False)
                self.events.append({"kind": "command_ack_reported", **deepcopy(record)})
        elif k == "survivor":
            if p["id"] not in self.survivors:
                rec = dict(p)
                rec["reported_t"] = round(now, 1)
                rec["delay_s"] = round(now - p["t"], 1)
                self.survivors[p["id"]] = rec
                self.events.append({"kind": "survivor_reported", "survivor": p["id"], "by": p["by"],
                                    "pos": p["pos"], "delay_s": rec["delay_s"]})
        self.receipt_history.append({"src": b["src"], "kind": k, "hops": list(b["hops"]),
                                     "reported_t": round(now, 1), "delay_s": round(now - b["created"], 3)})
        for event in self.events[event_start:]:
            self.event_history.append(deepcopy(event) | {"received_at": round(now, 1)})
        if k == "fault":
            self.event_history.append({"kind": "fault_reported", "robot": p["robot"],
                                       "fault": p["fault"], "received_at": round(now, 1)})
        elif k == "telemetry" and p.get("node_type") == "relay":
            self.event_history.append({"kind": "relay_reported", "id": p["id"],
                                       "received_at": round(now, 1)})
        return True

    def coverage(self):
        return {} if self.coverage_grid is None else {"coverage": self.coverage_grid.view()}

    def view(self, now):
        robots = []
        for r in self.robots.values():
            record = {k: r[k] for k in ("id", "pose", "state", "battery_pct", "last_seen", "plan_id", "zone")}
            record["stale_s"] = round(now - r["sent_t"], 1)
            if self.camera_telemetry and "camera" in r:
                record["camera"] = deepcopy(r["camera"]) | {
                    "last_seen_s": round(max(0, now - r["camera"]["t"]), 1)}
            robots.append(record)
        relays = [{"id": r["id"], "pos": list(r["pos"]), "beacon_for": r["beacon_for"]}
                  for r in self.relays.values()]
        faults = [{k: v for k, v in f.items() if k != "sent_t"} for f in self.faults.values()]
        routes = [deepcopy(self.routes[sid]) for sid in sorted(self.routes)]
        result = {"robots": robots, "survivors": list(self.survivors.values()), "relays": relays,
                  "faults": faults, "routes": routes}
        if self.command_acks:
            result["command_acks"] = deepcopy(list(self.command_acks.values()))
        return result
