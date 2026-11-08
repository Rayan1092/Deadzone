"""Belief map Phase 2 (opt-in DZ_SEARCH_BAYES=1): frontiers are ranked by the expected missing
mass of the robot's own belief within sensor reach, divided by travel time. Flag off: the legacy
frontier score, unchanged (the demo guard covers that)."""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FREE, OCC, UNKNOWN  # noqa: E402
from deadzone.robot import perception  # noqa: E402
from deadzone.robot.robot import Robot  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def hall_with_two_unknown_rooms(monkeypatch, flag):
    """A known corridor (y 14..18 m) with two unknown rooms opening off it, west (x 2..10) and east
    (x 22..30); the robot stands in the middle facing east. Both rooms are the same size and the
    same distance away."""
    monkeypatch.setenv("DZ_SEARCH_BAYES", "1" if flag else "0")
    r = Robot("R1", "test", "#fff", (16.0, 16.0, 0.0), (128, 128), 0.25, (16.0, 16.0))
    r.state, r.linked, r.t = "EXPLORING", True, 5.0
    g = r.map.grid
    g[:] = OCC
    g[56:72, 8:120] = FREE                      # corridor, y 14..18
    g[20:56, 8:40] = UNKNOWN                    # west room, y 5..14, x 2..10
    g[20:56, 88:120] = UNKNOWN                  # east room, y 5..14, x 22..30
    g[72:76, :] = OCC
    return r


def test_flagged_scorer_prefers_the_room_nobody_has_looked_at(monkeypatch):
    r = hall_with_two_unknown_rooms(monkeypatch, True)
    assert r.search_bayes
    # the west room was looked at from its doorway: its missing mass is low now
    for _ in range(6):
        r.belief.observe((6.0, 13.5, -math.pi / 2), r.map.grid == OCC)
    assert r._plan_frontier()
    assert r.target[0] > 16, r.target                    # heads east, toward the unexamined room
    # flip the evidence: now the east room has been seen, the west one is the better bet
    r2 = hall_with_two_unknown_rooms(monkeypatch, True)
    for _ in range(6):
        r2.belief.observe((26.0, 13.5, -math.pi / 2), r2.map.grid == OCC)
    assert r2._plan_frontier()
    assert r2.target[0] < 16, r2.target


def test_flag_off_keeps_the_legacy_choice_and_ignores_belief(monkeypatch):
    a = hall_with_two_unknown_rooms(monkeypatch, False)
    b = hall_with_two_unknown_rooms(monkeypatch, False)
    for _ in range(6):
        b.belief.observe((6.0, 13.5, -math.pi / 2), b.map.grid == OCC)
    assert not a.search_bayes and a._plan_frontier() and b._plan_frontier()
    assert a.target == b.target                           # the belief changes nothing with the flag off


def test_seed_7_runs_with_the_flag_on(monkeypatch):
    monkeypatch.setenv("DZ_SEARCH_BAYES", "1")
    perception.reset_detector()
    sim = Sim(n_robots=3, seed=7)
    found = set()
    while sim.time < 150:
        sim.tick()
        found |= {e["survivor"] for e in sim.drain_events() if e["kind"] == "survivor_found"}
    assert all(r.search_bayes for r in sim.robots.values())
    assert found, "robots steered by belief still find people"
    assert all(r.fault is None or r.fault != "TRAPPED" for r in sim.robots.values())
    assert all(np.isfinite(r.belief.missing_grid()).all() for r in sim.robots.values())
