"""DZ_ZONE_PRIORITY=1 (Rayan, 2026-11-09): on plan receipt the zone owner abandons its current
frontier and heads to the zone at once; telemetry plan_state says "heading to <zone>" until it is
there. Flag unset: unchanged."""
import math

import pytest

from deadzone.command.plan import PlanManager, SearchPlan
from deadzone.command.safety import SafetyChecker
from deadzone.sim import Sim

EAST = [[32, 17], [40, 17], [40, 30], [32, 30]]   # warehouse / steel cage corner, far from the start


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("DETECTOR", "sim")
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "0")
    monkeypatch.setenv("DZ_SCENARIO_EVENTS", "0")


def dispatch(sim, plan_id, robot="R1", zone_id="Z3", poly=EAST):
    plans = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
    plans.save(SearchPlan.model_validate({"plan_id": plan_id, "author": "phone-a", "lost_link_budget_s": 60,
                                          "zones": [{"id": zone_id, "robot": robot, "comms": "lost_link_ok", "poly": poly}]}))
    assert plans.dispatch(plan_id)["ok"]


def run(sim, until):
    log = []
    while sim.time < until:
        sim.tick()
        log += [(round(sim.time, 1), e) for e in sim.drain_events()]
    return log


def centre(poly):
    return sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)


def test_mid_run_plan_turns_the_owner_toward_its_zone_and_says_so(monkeypatch):
    monkeypatch.setenv("DZ_ZONE_PRIORITY", "1")
    sim = Sim(n_robots=1, seed=7)
    run(sim, 20.0)                                   # exploring Storage, west side
    r1 = sim.robots["R1"]
    before = r1.target
    assert before is not None and math.dist(before, centre(EAST)) > 20
    dispatch(sim, "P-z3")
    log = run(sim, 22.0)
    heading = [e for _, e in log if e["kind"] == "heading_to_zone"]
    assert [(e["robot"], e["zone"]) for e in heading] == [("R1", "Z3")]
    assert r1.telemetry(None)["plan_state"] == "heading to Z3"
    assert r1.target is not None and math.dist(r1.target, centre(EAST)) < math.dist(before, centre(EAST)) - 5, \
        f"abandoned {before} for a frontier toward the zone, got {r1.target}"
    run(sim, 90.0)
    assert r1.telemetry(None)["plan_state"] is None, "arrived: the zone is on its map"
    assert r1.pose[0] > 20, f"R1 crossed toward the east zone, is at {r1.pose[:2]}"


def test_flag_unset_keeps_the_old_behaviour(monkeypatch):
    monkeypatch.delenv("DZ_ZONE_PRIORITY", raising=False)
    sim = Sim(n_robots=1, seed=7)
    run(sim, 20.0)
    dispatch(sim, "P-z3")
    log = run(sim, 22.0)
    assert not any(e["kind"] == "heading_to_zone" for _, e in log)
    assert sim.robots["R1"].telemetry(None)["plan_state"] is None


def test_owner_already_in_its_zone_does_not_head_anywhere(monkeypatch):
    monkeypatch.setenv("DZ_ZONE_PRIORITY", "1")
    sim = Sim(n_robots=1, seed=7)
    run(sim, 1.0)
    dispatch(sim, "P-here", zone_id="ZE", poly=[[0, 12], [6, 12], [6, 18], [0, 18]])   # the entrance
    log = run(sim, 3.0)
    assert not any(e["kind"] == "heading_to_zone" for _, e in log)
    assert sim.robots["R1"].telemetry(None)["plan_state"] is None
