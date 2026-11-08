"""Tester's trace (2026-11-09): with DZ_ROBOT_COLLISIONS, R1 bumped R3 in Office A's doorway at
9.4 s, marked R3's body as a wall on its own map for good, and later reported TRAPPED at 37.4 s
(required flags, seed 7, no plan). Cells marked because a peer blocked us are given back as soon
as a route or a frontier is missing, so another robot never walls a robot in."""
import pytest

from deadzone.sim import Sim

FLAGS = {"DZ_OBSTACLES": "1", "DZ_ROBOT_COLLISIONS": "1", "DZ_SMART_RUBBLE": "1", "DZ_COVERAGE_GRID": "1"}


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    for k, v in FLAGS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DETECTOR", "sim")


def test_no_plan_seed_7_no_robot_is_trapped_by_a_peer():
    sim = Sim(n_robots=3, seed=7)
    sim.tick()
    contacts, faults = [], []
    while sim.time < 60:
        sim.tick()
        for e in sim.drain_events():
            if e["kind"] == "robot_contact":
                contacts.append((round(sim.time, 1), e["a"], e["b"]))
            if e["kind"] == "fault":
                faults.append((round(sim.time, 1), e["robot"], e["fault"]))
    assert contacts, "the doorway contact still happens"
    assert not any(f == "TRAPPED" for _, _, f in faults), faults
    assert sim.robots["R1"].state not in ("DONE", "SHUTDOWN"), "Office A is not hidden from R1's search"


def test_peer_marks_are_given_back_and_real_obstacles_are_kept():
    sim = Sim(n_robots=1, seed=7)
    r = sim.robots["R1"]
    r.pose = (5.0, 15.0, 0.0)
    ix, iy = r._cell(5.0 + 0.35, 15.0)
    before = int(r.map.grid[iy, ix])
    r._block_ahead(peer=True)
    assert (ix, iy) in r.peer_marks and r.map.grid[iy, ix] != before or before == 1
    assert r._forget_peer_marks() or before == 1
    assert int(r.map.grid[iy, ix]) == before and not r.peer_marks
    r._block_ahead()                               # a real obstacle (no peer): stays
    assert not r.peer_marks and not r._forget_peer_marks()
