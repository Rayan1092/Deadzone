"""What the command post knows. Updated ONLY by bundles delivered through the network."""
import numpy as np


class CommandPost:
    def __init__(self, fp):
        self.map = np.zeros((fp.h, fp.w), dtype=np.uint8)
        self.map_sent_t = np.full((fp.h, fp.w), -np.inf)
        self.robots = {}      # id -> last telemetry + last_seen
        self.relays = {}
        self.survivors = {}   # id -> record + reported_t
        self.faults = {}
        self.delivered = 0
        self.events = []
        self._seen = {}

    def receive(self, b, now):
        if b["dst"] != "CMD" or b["custodian"] != "CMD" or now > b["created"] + b["ttl"]:
            return False
        self._seen = {bid: expiry for bid, expiry in self._seen.items() if now <= expiry}
        if b["bid"] in self._seen:
            return False
        self._seen[b["bid"]] = b["created"] + b["ttl"]
        self.delivered += 1
        p = b["payload"]
        k = b["kind"]
        if k == "telemetry" and p.get("node_type") == "relay":
            prev = self.relays.get(p["id"])
            version = b["created"], p.get("revision", 0)
            if prev is None or (prev["sent_t"], prev.get("revision", 0)) <= version:
                self.relays[p["id"]] = {"id": p["id"], "pos": list(p["pos"]), "sent_t": b["created"],
                                         "revision": version[1]}
        elif k == "telemetry":
            prev = self.robots.get(p["id"])
            if prev is None or prev["sent_t"] <= b["created"]:
                self.robots[p["id"]] = {"id": p["id"], "pose": p["pose"], "state": p["state"],
                                        "battery_pct": p["battery_pct"], "last_seen": round(b["created"], 1),
                                        "sent_t": b["created"]}
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
        elif k == "survivor":
            if p["id"] not in self.survivors:
                rec = dict(p)
                rec["reported_t"] = round(now, 1)
                rec["delay_s"] = round(now - p["t"], 1)
                self.survivors[p["id"]] = rec
                self.events.append({"kind": "survivor_reported", "survivor": p["id"], "by": p["by"],
                                    "pos": p["pos"], "delay_s": rec["delay_s"]})
        return True

    def view(self, now):
        robots = []
        for r in self.robots.values():
            robots.append({k: r[k] for k in ("id", "pose", "state", "battery_pct", "last_seen")}
                          | {"stale_s": round(now - r["sent_t"], 1)})
        relays = [{"id": r["id"], "pos": list(r["pos"])} for r in self.relays.values()]
        faults = [{k: v for k, v in f.items() if k != "sent_t"} for f in self.faults.values()]
        return {"robots": robots, "survivors": list(self.survivors.values()), "relays": relays, "faults": faults}
