"""DZ_SMART_RUBBLE=1 (Rayan, 2026-11-08): the R key drops its rubble on the followed robot's planned
path 3-4 m ahead, at the nearest spot that walls nobody in (flood fill on the truth grid); when no
such spot exists it falls back to the plain spot. Flag unset: exactly the old behaviour. (The
demo's 162.5 s collapse is a scenario event in collapse_01.json, tests/test_scenario_events.py.)"""
import math

import pytest

from deadzone.robot.planning import dilate
from deadzone.sim import Sim


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("DETECTOR", "sim")
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "0")


def ahead(robot, m=1.5):
    x, y, th = robot.pose
    return (x + math.cos(th) * m, y + math.sin(th) * m)


def rubble_centers(sim):
    return [(round(sum(p[0] for p in rb["poly"]) / 4, 2), round(sum(p[1] for p in rb["poly"]) / 4, 2))
            for rb in sim.fp.data["rubble"] if rb.get("dynamic")]


def test_flag_unset_drops_exactly_where_the_screen_says(monkeypatch):
    monkeypatch.delenv("DZ_SMART_RUBBLE", raising=False)
    sim = Sim(n_robots=1, seed=7)
    for _ in range(50):
        sim.tick()
    at = ahead(sim.robots["R1"])
    placed = sim.press_rubble(at)
    assert placed["smart"] is False and placed["robot"] == "R1"
    assert rubble_centers(sim) == [(round(at[0], 2), round(at[1], 2))]
    for _ in range(100):
        sim.tick()
    assert len(rubble_centers(sim)) == 1, "one press, one rubble"


def test_smart_press_lands_on_the_path_ahead_and_walls_nobody_in(monkeypatch):
    monkeypatch.setenv("DZ_SMART_RUBBLE", "1")
    monkeypatch.setenv("DZ_SCENARIO_EVENTS", "0")
    sim = Sim(n_robots=3, seed=7)
    while sim.time < 20.0:                          # R1 in Storage with a 7 m planned path
        sim.tick()
    r1 = sim.robots["R1"]
    assert r1.path, "R1 is driving a planned path"
    pts = [tuple(r1.pose[:2])] + [tuple(p) for p in r1.path]
    placed = sim.press_rubble(ahead(r1))
    assert placed["smart"] is True and placed["robot"] == "R1"
    (cx, cy), = rubble_centers(sim)
    # on the path (within half a cell of a segment) and 2-6 m along it, preferring 3-4 m
    best, along = None, 0.0
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        n = max(1, int(seg / 0.25))
        for k in range(1, n + 1):
            q = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
            d = math.dist(q, (cx, cy))
            if best is None or d < best[0]:
                best = (d, along + seg * k / n)
        along += seg
    assert best[0] <= 0.2, f"rubble {cx, cy} is {best[0]:.2f} m off the path"
    assert 2.0 <= best[1] <= 6.0, f"rubble is {best[1]:.1f} m along the path"
    # safety: every robot still has a route to the entrance on the truth grid, nobody is under it
    for rid, b in sim.bodies.items():
        assert abs(b["x"] - cx) > 0.7 or abs(b["y"] - cy) > 0.7, f"{rid} under the rubble"
    sim.tick()
    free = ~dilate(sim.fp.occ, 1)
    ex, ey = sim.fp.to_cell(*sim.fp.entry)
    home = Sim._flood(free, (ex + 2, ey))
    for rid, b in sim.bodies.items():
        sx, sy = sim.fp.to_cell(b["x"], b["y"])
        assert home[sy, sx] or any(home[sy + dy, sx + dx] for dx in (-1, 0, 1) for dy in (-1, 0, 1)), \
            f"{rid} cut off from the entrance"


def test_doorway_spot_is_refused_and_corridor_spot_accepted(monkeypatch):
    monkeypatch.setenv("DZ_SMART_RUBBLE", "1")
    sim = Sim(n_robots=3, seed=7)
    sim.tick()
    assert sim._rubble_is_safe((10.0, 15.0), 1.4), "the 4 m corridor stays passable beside a 1.4 m square"
    assert not sim._rubble_is_safe((4.6, 17.0), 1.4), "Office A's only door: sealing it disconnects the room"
    assert not sim._rubble_is_safe((1.0, 15.0), 1.4), "never on a robot"


def test_no_safe_spot_falls_back_to_the_plain_spot(monkeypatch):
    monkeypatch.setenv("DZ_SMART_RUBBLE", "1")
    monkeypatch.setenv("DZ_SCENARIO_EVENTS", "0")
    sim = Sim(n_robots=1, seed=7)
    sim.tick()
    sim.robots["R1"].path = []                      # nothing planned: no candidate on the path
    at = ahead(sim.robots["R1"])
    placed = sim.press_rubble(at)
    assert placed["smart"] is False and rubble_centers(sim) == [(round(at[0], 2), round(at[1], 2))]
