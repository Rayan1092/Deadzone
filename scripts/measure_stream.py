"""Compare actual screen serialization over one shared seed-7 demo replay.

Run from the repo root: .venv/Scripts/python scripts/measure_stream.py
Counts UTF-8 application bytes, before WebSocket framing/TLS, with a deterministic
30 Hz input clock (3x simulation speed). This measures payload, never browser FPS.
"""
import argparse
import asyncio
import base64
from collections import Counter
import json
import math
import os
from pathlib import Path
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))


class Screen:
    def __init__(self, sim, compact):
        self.sim, self.compact = sim, compact
        self.bytes, self.frames = Counter(), Counter()
        self.max_lidar = 0
        self.grid_round_trips = 0

    async def send_text(self, wire):
        frame = json.loads(wire)
        kind, data = frame["t"], frame["data"]
        self.bytes[kind] += len(wire.encode("utf-8"))
        self.frames[kind] += 1
        if kind == "tick":
            self.max_lidar = max(self.max_lidar, *(len(r["lidar"]) for r in data["reality"]["robots"]))
        if kind == "maps" and self.compact:
            expected = self.sim.maps()
            for key in ("reality", "command"):
                assert zlib.decompress(base64.b64decode(data[key])) == base64.b64decode(expected[key])
                self.grid_round_trips += 1

    def result(self):
        return {"bytes": dict(self.bytes), "total_bytes": sum(self.bytes.values()),
                "frames": dict(self.frames), "max_lidar_points_per_robot": self.max_lidar,
                "lossless_grid_checks": self.grid_round_trips}


async def measure(seconds, input_hz):
    # Explicit overrides keep local server/.env and live services out of this run.
    for key in ("DZ_ROBOT_COLLISIONS", "DZ_OBSTACLES", "DZ_CAMERA_TELEMETRY", "DZ_NETWORK_TRAFFIC",
                "DZ_STREAM_OPTIMIZE", "DZ_SEARCH_BAYES", "DZ_GLOBAL_NO_GO", "DZ_FEC",
                "DZ_EXPLORATION_V2", "DZ_SENSOR_VIEW", "DZ_AFTERSHOCK", "DZ_SCENARIO_TIMELINE",
                "DZ_CRDT", "DZ_VOICE", "DZ_CONTROL_LEASES", "DZ_GEMINI", "DZ_AI_LAB",
                "DZ_MIC_CHECK", "DZ_AUTOSTART"):
        os.environ[key] = "0"
    os.environ.update(DZ_ROBOTS="3", DZ_SEED="7", DZ_FLOORPLAN="", DZ_MODE="deadzone", DETECTOR="model")

    from deadzone.app import Hub
    from deadzone.command.plan import SearchPlan
    from deadzone.network.stream import StreamState
    from deadzone.robot.perception import get_detector

    hubs = [Hub() for _ in range(3)]
    sim = hubs[0].sim
    zones = [
        {"id": "ZW", "robot": "R1", "priority": 1, "comms": "relay",
         "poly": [[0, 17], [20, 17], [20, 30], [0, 30]]},
        {"id": "ZNE", "robot": "R2", "priority": 1, "comms": "relay",
         "poly": [[32, 17], [40, 17], [40, 30], [32, 30]]},
        {"id": "ZB", "robot": "R3", "priority": 1, "comms": "relay",
         "poly": [[20, 17], [32, 17], [32, 30], [20, 30]]}]
    plan = {"plan_id": "P-1", "author": "judge-phone", "lost_link_budget_s": 60,
            "no_go": [], "zones": zones}
    plans = hubs[0].plans
    plans.save(SearchPlan.model_validate(plan))
    assert not plans.check("P-1")["ok"]
    zones[1]["comms"] = "lost_link_ok"
    plans.save(SearchPlan.model_validate(plan))
    assert plans.check("P-1")["ok"] and plans.dispatch("P-1")["ok"]

    clock = [0.0]
    sinks = []
    for i, hub in enumerate(hubs):
        hub.sim = sim
        hub.stream = StreamState(enabled=i > 0, clock=lambda: clock[0])
        sink = Screen(sim, compact=i == 2)
        hub.screens.add(sink)
        if i == 2:
            hub.compact_clients.add(sink)
        sinks.append(sink)

    async def broadcast(force=False):
        events = list(sim.events)
        for hub in hubs:
            sim.events = list(events)
            await hub.broadcast_tick(force_maps=force)
        sim.events.clear()

    await broadcast(force=True)
    director = {150.0: ("rubble", "R1"), 165.0: ("overcurrent", "R3"), 175.0: ("overload", "R1")}
    while sim.time < seconds:
        action = director.get(round(sim.time, 1))
        if action:
            name, rid = action
            robot = sim.robots[rid]
            if name == "rubble":
                x, y, th = robot.pose
                sim.drop_rubble((x + math.cos(th) * 1.5, y + math.sin(th) * 1.5))
            elif name == "overcurrent":
                robot.inject_overcurrent()
            else:
                robot.inject_perception_overload()
        sim.tick()
        clock[0] = (sim.tick_n - 1) / input_hz
        await broadcast()

    profiles = dict(zip(("legacy", "optimized_base64", "optimized_compact"), (s.result() for s in sinks)))
    for name in ("optimized_base64", "optimized_compact"):
        profiles[name]["reduction_pct"] = round(100 * (1 - profiles[name]["total_bytes"] /
                                                       profiles["legacy"]["total_bytes"]), 2)
    return {"setup": {"seed": 7, "robots": 3, "sim_seconds": sim.time,
                       "input_hz": input_hz, "modeled_wall_seconds": round(clock[0], 3),
                       "detector": get_detector().mode, "plan": "P-1 rejected, allow ZNE dark, dispatch",
                       "director": "R/F/O at 150/165/175 s", "initial_forced_frame": True,
                       "counts": "screen UTF-8 JSON bytes; no WS/TLS overhead, hello or plan_state"},
            "profiles": profiles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=250)
    parser.add_argument("--input-hz", type=float, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if (not math.isfinite(args.seconds) or not math.isfinite(args.input_hz)
            or args.seconds <= .1 or args.input_hz <= 0):
        parser.error("seconds must exceed 0.1 and input-hz must be positive")
    report = json.dumps(asyncio.run(measure(args.seconds, args.input_hz)), indent=2)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
