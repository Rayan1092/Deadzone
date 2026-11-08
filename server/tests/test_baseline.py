"""Baseline robot mode ("without Deadzone"): stops and waits when its link drops, no relays.
Deadzone stays the default; the live toggle switches a waiting robot back to normal behavior."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot import robot as robot_mod  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def test_deadzone_is_the_default(monkeypatch):
    monkeypatch.delenv("DZ_MODE", raising=False)
    sim = Sim(n_robots=3, seed=7)
    assert {r.mode for r in sim.robots.values()} == {"deadzone"}
    assert sim.snapshot()["reality"]["robots"][0]["mode"] == "deadzone"


def test_env_selects_baseline_and_bad_values_fall_back(monkeypatch):
    monkeypatch.setenv("DZ_MODE", "Baseline")
    assert robot_mod.default_mode() == "baseline"
    monkeypatch.setenv("DZ_MODE", "nonsense")
    assert robot_mod.default_mode() == "deadzone"


def test_set_mode_validates_and_reports(monkeypatch):
    monkeypatch.delenv("DZ_MODE", raising=False)
    r = Sim(n_robots=1, seed=7).robots["R1"]
    with pytest.raises(ValueError):
        r.set_mode("teleop")
    r.set_mode("baseline")
    r.set_mode("baseline")                     # no-op, no second event
    assert [e for e in r.events if e["kind"] == "mode_changed"] == [
        {"kind": "mode_changed", "robot": "R1", "mode": "baseline"}]


@pytest.fixture(scope="module")
def baseline_run():
    """Seed 7, 3 robots, all baseline for 200 s, then the waiting robot is toggled back."""
    sim = Sim(n_robots=3, seed=7)
    for r in sim.robots.values():
        r.set_mode("baseline")
    log, poses = [], {}
    while sim.time < 200.0:
        sim.tick()
        t = round(sim.time, 1)
        log += [(t, e) for e in sim.drain_events()]
        for rid, r in sim.robots.items():
            if r.state == "WAITING_FOR_LINK":
                poses.setdefault(rid, []).append(tuple(r.pose[:2]))
    waiting = sorted(rid for rid, r in sim.robots.items() if r.state == "WAITING_FOR_LINK")
    after = {}
    if waiting:
        rid = waiting[0]
        start = tuple(sim.robots[rid].pose[:2])
        sim.robots[rid].set_mode("deadzone")
        for _ in range(100):
            sim.tick()
            log += [(round(sim.time, 1), e) for e in sim.drain_events()]
        after = {"rid": rid, "state": sim.robots[rid].state,
                 "moved": math.dist(start, sim.robots[rid].pose[:2])}
    return {"sim": sim, "log": log, "poses": poses, "waiting": waiting, "after": after}


def test_baseline_drops_no_relays(baseline_run):
    assert not any(e["kind"] == "relay_dropped" for _, e in baseline_run["log"])
    assert all(r.relays_left == robot_mod.RELAYS_PER_ROBOT for r in baseline_run["sim"].robots.values())


def test_baseline_stops_and_waits_in_the_dark(baseline_run):
    log = baseline_run["log"]
    lost = [(t, e["robot"]) for t, e in log if e["kind"] == "link_lost"]
    waits = [(t, e["robot"]) for t, e in log if e["kind"] == "waiting_for_link"]
    assert lost, "some robot should lose its link in collapse_01 within 200 s"
    assert waits
    for t, rid in waits:
        assert any(lt <= t <= lt + 0.2 and lr == rid for lt, lr in lost), (t, rid)
    for rid, pts in baseline_run["poses"].items():
        # stays where the signal died (no driving while waiting)
        assert max(math.dist(pts[0], p) for p in pts) < 0.3, rid


def test_toggle_back_to_deadzone_resumes(baseline_run):
    after = baseline_run["after"]
    assert after, "expected a waiting robot at 200 s"
    assert after["state"] != "WAITING_FOR_LINK"
    assert after["moved"] > 1.0
    assert any(e["kind"] == "mode_changed" and e["mode"] == "deadzone" for _, e in baseline_run["log"])
