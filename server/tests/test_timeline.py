import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot.robot import FAULTS, REVERSE_M, STATES  # noqa: E402
from deadzone.robot.scheduler import NAMES, Scheduler, liu_layland_bound, utilization  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def test_utilization_matches_the_plan_table():
    assert round(utilization(), 3) == 0.377
    assert utilization() <= liu_layland_bound() and round(liu_layland_bound(), 3) == 0.735


def test_task_frames_follow_the_contract():
    sched = Scheduler()
    for frame in range(20):
        slices = sched.run_frame(frame)
        end = 0
        for s in slices:
            assert set(s) == {"name", "start", "dur", "missed"}
            assert s["name"] in NAMES and 0 <= s["start"] < 100 and s["dur"] > 0
            assert s["start"] >= end and s["start"] + s["dur"] <= 100   # one CPU, no overlap
            end = s["start"] + s["dur"]
            assert not s["missed"]
        safety = [s for s in slices if s["name"] == "safety"]
        assert [s["start"] for s in safety] == [0, 50]   # top priority runs the moment it is released


def test_telemetry_carries_tasks_and_contract_values():
    sim = Sim(n_robots=1, seed=7)
    for _ in range(300):
        sim.tick()
        r = sim.snapshot()["reality"]["robots"][0]
        assert r["state"] in STATES and (r["fault"] is None or r["fault"] in FAULTS)
    assert r["tasks"] and r["tasks"][0]["name"] == "safety"


def test_director_overcurrent_stops_backs_up_and_replans():
    sim = Sim(n_robots=1, seed=7)
    r = sim.robots["R1"]
    while sim.time < 90:
        sim.tick()
    sim.drain_events()
    r.inject_overcurrent()
    seen, kinds, back_from, backed = [], [], None, 0.0
    for _ in range(60):
        sim.tick()
        kinds += [(e["kind"], e.get("fault"), e.get("reason")) for e in sim.drain_events()]
        if not seen or seen[-1] != r.state:
            seen.append(r.state)
        if r.state == "FAULT":
            back_from = back_from or list(r.reverse_from)
            backed = max(backed, math.dist(back_from[:2], r.pose[:2]))
    assert ("fault", "OVERCURRENT", None) in kinds and ("replan", None, "overcurrent") in kinds
    assert seen[:4] == ["EXPLORING", "FAULT", "REPLANNING", "EXPLORING"]
    assert backed >= REVERSE_M - 0.05
    assert r.fault is None
