"""Scenario events in the floor plan JSON (Rayan, 2026-11-08; schema in docs/PLAN.md "Scenario
events"): `events: [{"t", "type": collapse|aftershock|radio_fail, ...}]`, run by the sim every run,
deterministically, before the robots step at that tick. DZ_SCENARIO_EVENTS=0 switches them off."""
import json
import math
from pathlib import Path

import pytest

from deadzone.sim import DEFAULT_PLAN, Sim, parse_scenario_events


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("DETECTOR", "sim")
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "0")
    monkeypatch.delenv("DZ_SCENARIO_EVENTS", raising=False)
    monkeypatch.delenv("DZ_SMART_RUBBLE", raising=False)


def plan_with(tmp_path, events):
    data = json.loads(Path(DEFAULT_PLAN).read_text(encoding="utf-8"))
    data["events"] = events
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(sim, until):
    log = []
    while sim.time < until:
        sim.tick()
        log += [(round(sim.time, 1), e) for e in sim.drain_events()]
    return log


def test_collapse_01_carries_the_demo_collapse():
    data = json.loads(Path(DEFAULT_PLAN).read_text(encoding="utf-8"))
    assert [(e["t"], e["type"], e["near"]) for e in data["events"]] == [(162.5, "collapse", "R1")]


def test_collapse_near_a_robot_drops_ahead_of_it_without_any_flag(tmp_path):
    sim = Sim(plan_path=plan_with(tmp_path, [{"t": 30.0, "type": "collapse", "near": "R1"}]), n_robots=3, seed=7)
    log = run(sim, 29.95)
    x, y, th = sim.robots["R1"].pose
    expected = (x + math.cos(th) * 1.5, y + math.sin(th) * 1.5)
    assert sim._rubble_is_safe(expected, 1.4)
    log += run(sim, 32.0)
    falls = [(t, e) for t, e in log if e["kind"] == "rubble_fall"]
    assert len(falls) == 1
    t, e = falls[0]
    assert abs(t - 30.1) < 0.15 and e["cause"] == "collapse" and e["robot"] == "R1"
    cx = sum(p[0] for p in e["poly"]) / 4
    cy = sum(p[1] for p in e["poly"]) / 4
    assert math.dist((cx, cy), expected) < 0.05
    assert not any(e["kind"] == "rubble_pressed" for _, e in log), "a scenario event is not a key press"


def test_collapse_spot_is_never_moved(tmp_path):
    """The author owns the spot: even where the smart R key would refuse it, the collapse lands
    exactly 1.5 m ahead of `near`."""
    sim = Sim(plan_path=plan_with(tmp_path, [{"t": 20.0, "type": "collapse", "near": "R1"}]), n_robots=3, seed=7)
    run(sim, 19.95)
    x, y, th = sim.robots["R1"].pose
    plain = (x + math.cos(th) * 1.5, y + math.sin(th) * 1.5)
    assert not sim._rubble_is_safe(plain, 1.4)
    log = run(sim, 21.0)
    (e,) = [e for _, e in log if e["kind"] == "rubble_fall"]
    center = (sum(p[0] for p in e["poly"]) / 4, sum(p[1] for p in e["poly"]) / 4)
    assert math.dist(center, plain) < 0.05 and e["cause"] == "collapse"


def test_aftershock_and_radio_fail_events(tmp_path):
    events = [{"t": 2.0, "type": "radio_fail"},          # no relay yet: reported, run carries on
              {"t": 3.0, "type": "aftershock", "at": [10.0, 15.0], "destroy_relay": False}]
    sim = Sim(plan_path=plan_with(tmp_path, events), n_robots=1, seed=7)
    log = run(sim, 4.0)
    failed = [e for _, e in log if e["kind"] == "scenario_event_failed"]
    assert [(e["type"], e["scheduled_t"]) for e in failed] == [("radio_fail", 2.0)]
    shocks = [e for _, e in log if e["kind"] == "aftershock"]
    assert len(shocks) == 1 and shocks[0]["at"] == [10.0, 15.0] and shocks[0]["destroyed_relay"] is None

    events = [{"t": 2.0, "type": "radio_fail", "relay": "RL1"}]
    sim = Sim(plan_path=plan_with(tmp_path, events), n_robots=1, seed=7)
    sim.add_relay((3.0, 15.0), owner="R1")
    log = run(sim, 3.0)
    assert [e["relay"] for _, e in log if e["kind"] == "radio_fail"] == ["RL1"]
    assert sim.relays["RL1"]["destroyed"] and not sim.relays["RL1"]["on"]
    assert not any(e["kind"] == "rubble_fall" for _, e in log), "a radio failure drops no rubble"


def test_events_run_in_time_order_and_are_deterministic(tmp_path):
    events = [{"t": 4.0, "type": "collapse", "near": "R1"}, {"t": 2.0, "type": "collapse", "near": "R1"}]
    path = plan_with(tmp_path, events)
    runs = []
    for _ in range(2):
        sim = Sim(plan_path=path, n_robots=3, seed=7)
        log = run(sim, 6.0)
        runs.append([(t, e["poly"]) for t, e in log if e["kind"] == "rubble_fall"])
    assert runs[0] == runs[1] and [t for t, _ in runs[0]] == [2.1, 4.1]


def test_switch_off_and_schema_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("DZ_SCENARIO_EVENTS", "0")
    sim = Sim(plan_path=plan_with(tmp_path, [{"t": 1.0, "type": "collapse", "near": "R1"}]), n_robots=1, seed=7)
    assert not any(e["kind"] == "rubble_fall" for _, e in run(sim, 2.0))
    size = {"size": [40, 30]}
    for bad in ([{"t": 1, "type": "fire"}], [{"type": "collapse"}], [{"t": -1, "type": "collapse"}],
                [{"t": 1, "type": "collapse", "at": [50, 1]}], [{"t": 1, "type": "collapse", "size": 9}], {"t": 1}):
        with pytest.raises(ValueError):
            parse_scenario_events({**size, "events": bad})
    assert parse_scenario_events(size) == []
