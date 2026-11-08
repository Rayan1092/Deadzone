"""DZ_SMART_RUBBLE=1 (Rayan, 2026-11-08): the R key drops its rubble on the followed robot's planned
path 3-4 m ahead, at the nearest spot that walls nobody in (flood fill on the truth grid); when no
such spot exists it falls back to the plain spot. Separately, a scripted secondary collapse drops
rubble 1.5 m ahead of R1 at DZ_COLLAPSE_AT sim seconds (162.5 on collapse_01) whatever anyone
pressed (rubble_fall, cause "collapse"). Flag unset: exactly the old behaviour."""
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
    assert sim.collapse_at is None
    for _ in range(50):
        sim.tick()
    at = ahead(sim.robots["R1"])
    placed = sim.press_rubble(at)
    assert placed["smart"] is False and placed["robot"] == "R1"
    assert rubble_centers(sim) == [(round(at[0], 2), round(at[1], 2))]
    for _ in range(100):
        sim.tick()
    assert len(rubble_centers(sim)) == 1, "no scripted collapse with the flag unset"


def test_smart_press_lands_on_the_path_ahead_and_walls_nobody_in(monkeypatch):
    monkeypatch.setenv("DZ_SMART_RUBBLE", "1")
    monkeypatch.setenv("DZ_COLLAPSE_AT", "0")
    sim = Sim(n_robots=3, seed=7)
    assert sim.collapse_at is None
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
    monkeypatch.setenv("DZ_COLLAPSE_AT", "0")
    sim = Sim(n_robots=1, seed=7)
    sim.tick()
    sim.robots["R1"].path = []                      # nothing planned: no candidate on the path
    at = ahead(sim.robots["R1"])
    placed = sim.press_rubble(at)
    assert placed["smart"] is False and rubble_centers(sim) == [(round(at[0], 2), round(at[1], 2))]


def test_scripted_collapse_drops_ahead_of_r1_once_even_after_a_key_press(monkeypatch):
    monkeypatch.setenv("DZ_SMART_RUBBLE", "1")
    monkeypatch.setenv("DZ_COLLAPSE_AT", "6.0")
    sim = Sim(n_robots=3, seed=7)
    assert sim.collapse_at == 6.0
    log = []
    while sim.time < 4.0:
        sim.tick()
        log += [(round(sim.time, 1), e) for e in sim.drain_events()]
    sim.press_rubble(ahead(sim.robots["R3"]), robot="R3")    # a Q&A press first changes nothing
    while sim.time < 5.95:
        sim.tick()
        log += [(round(sim.time, 1), e) for e in sim.drain_events()]
    expected = ahead(sim.robots["R1"])                       # pose at the tick the collapse fires
    while sim.time < 10.0:
        sim.tick()
        log += [(round(sim.time, 1), e) for e in sim.drain_events()]
    falls = [(t, e.get("cause"), e.get("robot")) for t, e in log if e["kind"] == "rubble_fall"]
    assert [f[1] for f in falls] == ["key", "collapse"], falls
    t, cause, robot = falls[1]
    assert abs(t - 6.1) < 0.15 and robot == "R1"
    assert not any(e["kind"] == "rubble_pressed" and t2 > 5 for t2, e in log), "the collapse is not a key press"
    cx, cy = rubble_centers(sim)[1]
    assert math.dist((cx, cy), expected) < 0.05, ((cx, cy), expected)


def test_default_collapse_time_is_the_demo_beat_on_collapse_01_only(monkeypatch):
    monkeypatch.setenv("DZ_SMART_RUBBLE", "1")
    monkeypatch.delenv("DZ_COLLAPSE_AT", raising=False)
    assert Sim(n_robots=1, seed=7).collapse_at == 162.5
    monkeypatch.setenv("DZ_COLLAPSE_AT", "0")
    assert Sim(n_robots=1, seed=7).collapse_at is None
