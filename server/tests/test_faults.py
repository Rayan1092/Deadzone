import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FREE  # noqa: E402
from deadzone.robot.power import RESERVE_PCT  # noqa: E402
from deadzone.robot.robot import PERCEPTION_OVERLOAD_MS, SAFE_STOP_WINDOW_S, Robot  # noqa: E402
from deadzone.robot.scheduler import Scheduler  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def bare_robot():
    r = Robot("R1", "Scout 1", "#fff", (2.0, 2.0, 0.0), (20, 20), 0.25, (1.0, 1.0))
    r.map.grid = np.full((20, 20), FREE, dtype=np.uint8)
    return r


def test_overload_misses_perception_but_never_safety():
    s = Scheduler()
    s.set_wcet("perception", PERCEPTION_OVERLOAD_MS)
    frames = [s.run_frame(f) for f in range(30)]
    assert s.misses["perception"] > 0 and s.misses["safety"] == 0
    for slices in frames:
        assert [x["start"] for x in slices if x["name"] == "safety"] == [0, 50]
        assert not any(x["missed"] for x in slices if x["name"] == "safety")
    assert any(x["missed"] for sl in frames for x in sl if x["name"] == "perception")
    s.reset_wcet("perception")
    for f in range(30, 50):
        s.run_frame(f)
    assert not s.jobs and s.nominal()          # recovers to the cached nominal schedule


def test_robot_overload_hook_raises_deadline_events_then_recovers():
    r = bare_robot()
    r.t = 0.0
    r.inject_perception_overload(seconds=2.0)
    misses = []
    for k in range(1, 40):
        r.t = k * 0.1
        r._run_scheduler(0.1)
        misses += [e["task"] for e in r.events if e["kind"] == "deadline_miss"]
        r.events.clear()
    assert "perception" in misses and "safety" not in misses
    assert r.overload_until is None and r.scheduler.nominal()


def test_stuck_goes_through_the_fault_fsm():
    r = bare_robot()
    r.state, r.cmd_v = "EXPLORING", 0.5
    odo = {"pose": (2.0, 2.0, 0.0), "v": 0.0, "blocked": False}
    for k in range(1, 33):
        r.t = k * 0.1
        r.cmd_v = 0.5                       # keeps commanding speed but does not move
        r._check_faults(odo)
        if r.state == "FAULT":
            break
    assert r.state == "FAULT" and r.fault == "STUCK"
    assert any(b["kind"] == "fault" and b["prio"] == 1 for b in r.outbox)


def test_three_motion_faults_in_a_minute_safe_stop():
    sim = Sim(n_robots=1, seed=7)
    r = sim.robots["R1"]
    while sim.time < 20:
        sim.tick()
    faults = []
    for _ in range(3):
        r.inject_overcurrent()
        for _ in range(80):
            sim.tick()
            faults += [e["fault"] for e in sim.drain_events() if e["kind"] == "fault"]
    assert faults == ["OVERCURRENT", "OVERCURRENT", "SAFE_STOP"]
    pose = list(r.pose)
    for _ in range(30):
        sim.tick()
    assert r.state == "FAULT" and r.fault == "SAFE_STOP" and r.pose[:2] == pose[:2]


def test_faults_spread_over_more_than_a_minute_do_not_safe_stop():
    r = bare_robot()
    r.state = "EXPLORING"
    r.fault_times = [0.0, 10.0]
    r.t = SAFE_STOP_WINDOW_S + 1.0          # the first fault has aged out
    r._enter_fault("OVERCURRENT")
    assert r.fault == "OVERCURRENT"


def test_low_battery_is_reported_as_a_fault():
    sim = Sim(n_robots=1, seed=7)
    r = sim.robots["R1"]
    while sim.time < 40:
        sim.tick()
    sim.drain_events()
    r.battery.wh = (RESERVE_PCT + r._pct_home() - 0.5) / 100.0 * 90.0
    sim.tick()
    kinds = [(e["kind"], e.get("fault")) for e in sim.drain_events()]
    assert ("fault", "LOW_BATTERY") in kinds
    assert r.state == "RETURNING_HOME" and r.fault == "LOW_BATTERY"
