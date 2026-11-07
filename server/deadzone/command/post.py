"""What the command post knows. Updated ONLY by bundles delivered through the network."""
import numpy as np


class CommandPost:
    def __init__(self, fp):
        self.map = np.zeros((fp.h, fp.w), dtype=np.uint8)
        self.robots = {}      # id -> last telemetry + last_seen
        self.survivors = {}   # id -> record + reported_t
        self.delivered = 0
        self.events = []

    def receive(self, b, now):
        self.delivered += 1
        p = b["payload"]
        k = b["kind"]
        if k == "telemetry":
            prev = self.robots.get(p["id"])
            if prev is None or prev["sent_t"] <= b["created"]:
                self.robots[p["id"]] = {"id": p["id"], "pose": p["pose"], "state": p["state"],
                                        "battery_pct": p["battery_pct"], "last_seen": round(b["created"], 1),
                                        "sent_t": b["created"]}
        elif k == "map_patch":
            self.map[p["iy"], p["ix"]] = p["v"]
        elif k == "survivor":
            if p["id"] not in self.survivors:
                rec = dict(p)
                rec["reported_t"] = round(now, 1)
                rec["delay_s"] = round(now - p["t"], 1)
                self.survivors[p["id"]] = rec
                self.events.append({"kind": "survivor_reported", "survivor": p["id"], "by": p["by"],
                                    "pos": p["pos"], "delay_s": rec["delay_s"]})

    def view(self, now):
        robots = []
        for r in self.robots.values():
            robots.append({k: r[k] for k in ("id", "pose", "state", "battery_pct", "last_seen")}
                          | {"stale_s": round(now - r["sent_t"], 1)})
        return {"robots": robots, "survivors": list(self.survivors.values()), "relays": []}
