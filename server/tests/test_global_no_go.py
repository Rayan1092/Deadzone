"""Testing-laptop trace: global exclusions reach unassigned robots through DTN."""
from copy import deepcopy
import json

import pytest

from deadzone.command.plan import PlanManager, SearchPlan
from deadzone.command.post import CommandPost
from deadzone.command.safety import RobotSpec, SafetyChecker
from deadzone.floorplan import FloorPlan
from deadzone.geometry import points_in_poly
from deadzone.network.dtn import make_bundle
from deadzone.sim import Sim


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("DZ_GLOBAL_NO_GO", "1")
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "0")
    monkeypatch.setenv("DETECTOR", "sim")


def draft(plan_id="P-global", no_go=True):
    return SearchPlan.model_validate({"plan_id": plan_id, "author": "phone-a", "zones": [
        {"id": "Z1", "robot": "R1", "poly": [[3, 14], [6, 14], [6, 16], [3, 16]]}],
        "no_go": [{"id": "NG1", "poly": [[.5, .5], [11.5, .5], [11.5, 12.5], [.5, 12.5]]}] if no_go else []})


def manager(sim):
    return PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))


def test_one_zone_global_exclusion_reaches_every_robot_and_can_be_cleared():
    sim = Sim(n_robots=3)
    sim.tick()
    plans = manager(sim)
    plans.save(draft())
    assert plans.dispatch("P-global")["ok"]
    queued = list(sim.network.queues["CMD"])
    assert {b["dst"] for b in queued} == {"R1", "R2", "R3"}
    for bundle in queued:
        assert bundle["kind"] == "plan" and bundle["prio"] == 1
        assert bundle["payload"]["no_go"]
        assert bool(bundle["payload"]["zones"]) == (bundle["dst"] == "R1")
    # Idempotence still means exactly one plan per robot, not repeated dispatches.
    assert plans.dispatch("P-global")["ok"]
    assert len(sim.network.queues["CMD"]) == 3
    applied = set()
    for _ in range(25):
        sim.tick()
        applied.update(e["robot"] for e in sim.drain_events() if e["kind"] == "plan_applied")
    assert applied == {"R1", "R2", "R3"}
    ix, iy = sim.fp.to_cell(5, 5)
    assert all(r.nogo[iy, ix] for r in sim.robots.values())
    assert not sim.robots["R2"].zones and not sim.robots["R3"].zones
    # Full shared plans also clear old exclusions on robots with no assigned zone.
    plans.save(draft("P-clear", no_go=False))
    assert plans.dispatch("P-clear")["ok"]
    for _ in range(25):
        sim.tick()
    assert all(not r.nogo[iy, ix] for r in sim.robots.values())


def test_flag_off_keeps_legacy_recipient_behavior(monkeypatch):
    monkeypatch.delenv("DZ_GLOBAL_NO_GO", raising=False)
    sim = Sim(n_robots=3)
    sim.tick()
    plans = manager(sim)
    plans.save(draft())
    assert plans.dispatch("P-global")["ok"]
    assert [b["dst"] for b in sim.network.queues["CMD"]] == ["R1"]


def test_trace_room_is_avoided_by_unassigned_robots_through_the_80_second_window():
    sim = Sim(n_robots=3)
    sim.tick()
    plans = manager(sim)
    plan = draft()
    plans.save(plan)
    assert plans.dispatch(plan.plan_id)["ok"]
    while sim.time < 80:
        sim.tick()
        for body in sim.bodies.values():
            assert not points_in_poly(body["x"], body["y"], plan.no_go[0].poly)


def test_trace_inside_start_passes_on_actual_building_prior():
    sim = Sim(n_robots=3)
    sim.tick()
    bundle = make_bundle("R3", "CMD", "telemetry", {
        "id": "R3", "pose": [3.8, 10, 0], "state": "EXPLORING", "battery_pct": 100}, sim.time, 120)
    bundle.update(custodian="CMD", hops=["R3", "CMD"])
    assert sim.post.receive(bundle, sim.time)
    data = draft().model_dump(mode="json")
    data["zones"][0]["robot"] = "R3"
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(data))
    assert plans.check("P-global")["ok"]


def open_prior(**changes):
    data = {"id": "escape", "name": "Escape", "size": [20, 12], "cell": .25,
            "materials": {"concrete": 16}, "walls": [], "hazards": [], "entry": [1, 6],
            "command_post": {"pos": [0, 6]}}
    data.update(changes)
    return FloorPlan(data)


def escape_plan():
    return SearchPlan.model_validate({"plan_id": "P-escape", "author": "phone-a", "zones": [
        {"id": "Z1", "robot": "R1", "poly": [[10, 5], [12, 5], [12, 7], [10, 7]], "comms": "lost_link_ok"}],
        "no_go": [{"id": "NG1", "poly": [[3, 3], [7, 3], [7, 8], [3, 8]]}]})


def report(post, pose=(5, 6, 0)):
    bundle = make_bundle("R1", "CMD", "telemetry", {
        "id": "R1", "pose": list(pose), "state": "EXPLORING", "battery_pct": 100}, 0, 120)
    bundle.update(custodian="CMD", hops=["R1", "CMD"])
    assert post.receive(bundle, 0)


def test_delivered_start_inside_new_exclusion_uses_escape_but_legacy_rejects(monkeypatch):
    fp = open_prior()
    post = CommandPost(fp)
    report(post)
    plan = escape_plan()
    checker = SafetyChecker(fp, {"R1": RobotSpec()})
    assert checker.check(plan, post, 0)["ok"]
    monkeypatch.setenv("DZ_GLOBAL_NO_GO", "0")
    legacy = SafetyChecker(fp, {"R1": RobotSpec()})
    result = legacy.check(plan, post, 0)
    assert not result["ok"] and result["violations"][0]["rule"] == "zone_unreachable"


@pytest.mark.parametrize("block", ["wall", "static_hazard", "home"])
def test_escape_never_crosses_walls_or_static_hazards_or_relaxes_the_home_goal(block):
    data = {}
    plan = escape_plan()
    if block == "wall":
        corners = [[3, 3], [7, 3], [7, 8], [3, 8]]
        data["walls"] = [{"a": a, "b": b, "material": "concrete"}
                         for a, b in zip(corners, corners[1:] + corners[:1])]
    elif block == "static_hazard":
        data["hazards"] = [{"id": "gas", "poly": [[4, 5], [6, 5], [6, 7], [4, 7]]}]
    else:
        payload = plan.model_dump(mode="json")
        payload["no_go"].append({"id": "HOME", "poly": [[0, 5], [2, 5], [2, 7], [0, 7]]})
        plan = SearchPlan.model_validate(payload)
    fp = open_prior(**data)
    post = CommandPost(fp)
    report(post)
    result = SafetyChecker(fp, {"R1": RobotSpec()}).check(plan, post, 0)
    assert not result["ok"]
    assert "zone_unreachable" in {v["rule"] for v in result["violations"]}


def test_escape_distance_is_charged_to_battery_reserve():
    fp = open_prior()
    post = CommandPost(fp)
    report(post)
    # Tiny test capacity makes both estimates report a reserve, so the extra
    # walking cost can be compared without assuming a passing approval is cached.
    checker = SafetyChecker(fp, {"R1": RobotSpec(capacity_wh=.1)})
    plan = escape_plan()
    inner = checker.check(plan, post, 0)
    report(post, (7.125, 6.125, 0))  # nearest allowed start, without the escape walk
    outer = checker.check(plan, post, 0)
    reserve = lambda result: next(v["value"] for v in result["violations"] if v["rule"] == "battery_reserve")
    assert reserve(inner) < reserve(outer)


def test_escape_keeps_command_only_boundary_and_does_not_read_live_robots():
    sim = Sim(n_robots=3)
    sim.tick()
    plans = manager(sim)
    plans.save(draft())
    before = deepcopy(plans.check("P-global"))
    sim.bodies["R1"].update(x=35, y=26)
    sim.robots["R1"].battery.wh = 0
    assert plans.check("P-global") == before
    assert "reality" not in json.dumps(before)
