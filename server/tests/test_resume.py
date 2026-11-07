import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot.robot import resume_command  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def safe_stopped_sim():
    sim = Sim(n_robots=1, seed=7)
    r = sim.robots["R1"]
    while sim.time < 20:
        sim.tick()
    for _ in range(3):
        r.inject_overcurrent()
        for _ in range(80):
            sim.tick()
    assert r.fault == "SAFE_STOP"
    sim.drain_events()
    return sim, r


def test_resume_command_from_cmd_clears_safe_stop():
    sim, r = safe_stopped_sim()
    assert sim.ios["R1"].radio.cmd_reachable(), "test spot must be linked so the command arrives"
    pose = list(r.pose)
    sim.network.queues["CMD"].append(resume_command("R1", sim.time))   # through the network only
    events = []
    for _ in range(40):
        sim.tick()
        events += [e["kind"] for e in sim.drain_events()]
    assert "resumed" in events
    assert r.fault is None and r.fault_times == [] and r.state != "FAULT"
    assert r.pose[:2] != pose[:2], "robot drives again after resume"


def test_resume_is_ignored_when_not_safe_stopped():
    sim = Sim(n_robots=1, seed=7)
    r = sim.robots["R1"]
    while sim.time < 10:
        sim.tick()
    sim.network.queues["CMD"].append(resume_command("R1", sim.time))
    for _ in range(20):
        sim.tick()
    assert not any(e["kind"] == "resumed" for e in sim.drain_events())
    assert r.state != "FAULT"
