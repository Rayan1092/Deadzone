"""Shutdown on DONE: back at the command post with nothing left to send, the robot powers down
(SHUTDOWN): scheduler stopped, lidar / camera / headlights off, battery drain stopped, one final
telemetry bundle with the new state, then radio silence (it still listens)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot import perception  # noqa: E402
from deadzone.robot.robot import SHUTDOWN_AFTER_S, STATES  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def small_building(tmp_path):
    data = {"id": "shutdown-test", "name": "Shutdown", "size": [10, 8], "cell": 0.25,
            "materials": {"brick": 4, "rubble": 8, "concrete": 16},
            "walls": [{"a": a, "b": b, "material": "concrete"} for a, b in
                      [([0, 0], [10, 0]), ([10, 0], [10, 8]), ([10, 8], [0, 8]), ([0, 8], [0, 5]), ([0, 3], [0, 0])]],
            "doors": [{"at": [0, 4], "width": 2.0, "axis": "y", "state": "open"}],
            "rooms": [{"id": "A", "name": "Hall", "poly": [[0, 0], [10, 0], [10, 8], [0, 8]]}],
            "rubble": [], "hazards": [], "survivors": [{"id": "S1", "pos": [8.0, 6.0], "thermal": "pos_0001.png"}],
            "decoys": [], "entry": [1.0, 4.0], "command_post": {"pos": [-2.0, 4.0], "tx_dbm": 30}}
    path = tmp_path / "b.json"
    path.write_text(json.dumps(data))
    return path


def test_robot_powers_down_after_done_and_sends_one_final_status(tmp_path):
    assert "SHUTDOWN" in STATES
    perception.reset_detector()
    sim = Sim(plan_path=small_building(tmp_path), n_robots=1, seed=7)
    r = sim.robots["R1"]
    log, done_t, shutdown_t = [], None, None
    while sim.time < 240 and shutdown_t is None:
        sim.tick()
        for e in sim.drain_events():
            log.append((round(sim.time, 1), e))
            if e["kind"] == "robot_shutdown":
                shutdown_t = sim.time
        if r.state == "DONE" and done_t is None:
            done_t = sim.time
    assert done_t is not None and shutdown_t is not None, (r.state, sim.time)
    assert shutdown_t - done_t >= SHUTDOWN_AFTER_S - 1e-6
    assert r.state == "SHUTDOWN" and r.tasks == [] and r.lights is False and r.lidar_pts == []
    tele = r.telemetry({})
    assert tele["state"] == "SHUTDOWN" and tele["lights"] is False and tele["tasks"] == []
    # the final status reaches Command, then the radio goes quiet while the robot still listens
    for _ in range(30):
        sim.tick()
        sim.drain_events()
    assert sim.post.robots["R1"]["state"] == "SHUTDOWN"
    wh, met = r.battery.wh, r.counters["scheduler_deadlines_met"]
    sent_before = sim.post.delivered
    for _ in range(50):
        sim.tick()
        sim.drain_events()
    assert r.battery.wh == wh, "no drain once shut down"
    assert r.counters["scheduler_deadlines_met"] == met, "scheduler stopped"
    assert sim.post.delivered == sent_before, "no more bundles after the final status"
    assert r.state == "SHUTDOWN" and r.outbox == []
    assert any(e["kind"] == "robot_shutdown" and e["robot"] == "R1" for _, e in log)


def test_lights_are_on_while_working(tmp_path):
    perception.reset_detector()
    sim = Sim(n_robots=1, seed=7)
    for _ in range(20):
        sim.tick()
    tele = sim.robots["R1"].telemetry({})
    assert tele["lights"] is True and tele["state"] != "SHUTDOWN"
