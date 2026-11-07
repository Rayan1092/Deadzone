"""Safety and dispatch operate on delivered knowledge, never simulation truth."""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.command.plan import PlanError, PlanManager, SearchPlan  # noqa: E402
from deadzone.command.post import CommandPost  # noqa: E402
from deadzone.command.safety import RobotSpec, SafetyChecker  # noqa: E402
from deadzone.floorplan import FloorPlan  # noqa: E402
from deadzone.network.dtn import make_bundle  # noqa: E402
from deadzone.sim import DT, Sim  # noqa: E402


def plan_data(**updates):
    data = {"plan_id": "P-1", "author": "phone-a", "zones": [
        {"id": "Z1", "robot": "R1", "priority": 1, "comms": "relay",
         "poly": [[3, 14], [6, 14], [6, 16], [3, 16]]}], "no_go": [], "lost_link_budget_s": 60}
    data.update(updates)
    return data


def report(post, *, pct=100.0, pose=(1.2, 14.2, 0.0), created=0.0, rid="R1"):
    payload = {"id": rid, "pose": list(pose), "state": "EXPLORING", "battery_pct": pct}
    b = make_bundle(rid, "CMD", "telemetry", payload, created, 120)
    b["custodian"] = "CMD"
    assert post.receive(b, created)


def manager(sim):
    return PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))


def rules(result):
    return {v["rule"] for v in result["violations"]}


def test_good_plan_passes_and_low_battery_plan_fails_with_reason():
    sim = Sim()
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(plan_data()))
    report(sim.post)
    assert plans.check("P-1") == {"ok": True, "plan_id": "P-1", "violations": []}
    report(sim.post, pct=20.1, created=0.1)
    result = plans.check("P-1")
    assert not result["ok"]
    assert "battery_reserve" in rules(result)
    violation = next(v for v in result["violations"] if v["rule"] == "battery_reserve")
    assert violation["value"] < violation["limit"] == 20
    assert violation["robot"] == "R1" and violation["zone"] == "Z1"


def test_missing_telemetry_does_not_fall_back_to_live_battery():
    sim = Sim()
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(plan_data()))
    assert "battery_reserve" in rules(plans.check("P-1"))
    assert sim.robots["R1"].battery.pct == 100


@pytest.mark.parametrize("requirement", [{"stairs": True}, {"rubble_height": 1.0}])
def test_capability_mismatch_is_rejected(requirement):
    sim = Sim()
    report(sim.post)
    data = plan_data()
    data["zones"][0]["requires"] = requirement
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(data))
    assert "capability" in rules(plans.check("P-1"))


def test_unknown_robot_is_rejected():
    sim = Sim()
    data = plan_data()
    data["zones"][0]["robot"] = "R99"
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(data))
    assert rules(plans.check("P-1")) == {"capability"}


def test_exact_polygon_overlap_detects_a_thin_no_go_area():
    sim = Sim()
    report(sim.post)
    data = plan_data(no_go=[{"id": "NG1", "poly": [[4.01, 13.9], [4.02, 13.9], [4.02, 16.1], [4.01, 16.1]]}])
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(data))
    assert "no_go_overlap" in rules(plans.check("P-1"))


def test_known_hazard_overlap_is_rejected():
    sim = Sim()
    report(sim.post)
    data = plan_data()
    data["zones"][0]["poly"] = [[15, 3], [20, 3], [20, 6], [15, 6]]
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(data))
    assert "no_go_overlap" in rules(plans.check("P-1"))


def open_prior(walls=None):
    return FloorPlan({"id": "test", "name": "Test", "size": [20, 10], "cell": 0.25,
                      "materials": {"concrete": 16}, "walls": walls or [], "hazards": [],
                      "entry": [1, 5], "command_post": {"pos": [0, 5]}})


def test_sealed_room_is_unreachable_without_snapping_across_its_wall():
    prior = open_prior([{"a": [6, 0], "b": [6, 10], "material": "concrete"}])
    post = CommandPost(prior)
    report(post, pose=(1, 5, 0))
    data = plan_data()
    data["zones"][0]["poly"] = [[8, 4], [12, 4], [12, 6], [8, 6]]
    result = SafetyChecker(prior, {"R1": RobotSpec()}).check(SearchPlan.model_validate(data), post, 0)
    assert "zone_unreachable" in rules(result)


def test_battery_budget_covers_all_zones_assigned_to_one_robot():
    prior = open_prior()
    post = CommandPost(prior)
    report(post, pct=21.75, pose=(1, 5, 0))
    data = plan_data()
    data["zones"][0]["poly"] = [[8, 4], [12, 4], [12, 6], [8, 6]]
    checker = SafetyChecker(prior, {"R1": RobotSpec()}, energy_time_scale=6)
    assert checker.check(SearchPlan.model_validate(data), post, 0)["ok"]
    data["zones"].append({**data["zones"][0], "id": "Z2"})
    assert "battery_reserve" in rules(checker.check(SearchPlan.model_validate(data), post, 0))


def test_stale_battery_reports_are_discounted_for_possible_offline_driving():
    sim = Sim()
    report(sim.post, pct=30)
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(plan_data()))
    assert plans.check("P-1")["ok"]
    sim.time = 1000
    assert "battery_reserve" in rules(plans.check("P-1"))


def test_dead_zone_requires_explicit_permission_or_a_delivered_relay():
    sim = Sim()
    report(sim.post)
    data = plan_data()
    data["zones"][0]["poly"] = [[35, 24], [39, 24], [39, 28], [35, 28]]
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(data))
    assert "comms_plan" in rules(plans.check("P-1"))
    relay = sim.add_relay((33, 15))
    assert "comms_plan" in rules(plans.check("P-1"))  # placement truth is not delivered knowledge
    announcement = sim.network.queues[relay][0]
    sim.post.receive(dict(announcement, custodian="CMD"), 0)
    assert "comms_plan" not in rules(plans.check("P-1"))
    sim.post.relays.clear()
    data["zones"][0]["comms"] = "lost_link_ok"
    plans.save(SearchPlan.model_validate(data))
    assert plans.check("P-1")["ok"]
    data["lost_link_budget_s"] = 0
    plans.save(SearchPlan.model_validate(data))
    assert "comms_plan" in rules(plans.check("P-1"))


def test_safety_does_not_read_live_pose_battery_rubble_or_link_state():
    sim = Sim()
    report(sim.post)
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(plan_data()))
    before = plans.check("P-1")
    sim.robots["R1"].battery.wh = 0
    sim.bodies["R1"].update(x=37.5, y=26)
    sim.drop_rubble((4, 15))
    sim._update_links()
    assert plans.check("P-1") == before


def test_dispatch_revalidates_and_does_not_queue_an_unsafe_plan():
    sim = Sim()
    report(sim.post)
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(plan_data()))
    assert plans.check("P-1")["ok"]
    report(sim.post, pct=1, created=0.1)
    assert not plans.dispatch("P-1")["ok"]
    assert not sim.network.queues["CMD"]


def test_dispatch_is_idempotent_and_reaches_robot_only_through_radio_inbox():
    sim = Sim()
    report(sim.post)
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(plan_data()))
    assert plans.dispatch("P-1")["ok"]
    assert plans.dispatch("P-1")["ok"]
    assert len(sim.network.queues["CMD"]) == 1
    assert sim.ios["R1"].radio.receive() == []
    sim.time = 0.1
    sim._move_bundles(DT)
    arrived = sim.ios["R1"].radio.receive()
    assert len(arrived) == 1
    assert arrived[0]["kind"] == "plan"
    assert arrived[0]["hops"] == ["CMD", "R1"]
    assert arrived[0]["payload"]["zones"][0]["robot"] == "R1"
    assert sim.ios["R1"].radio.receive() == []
    assert sim.robots["R1"].state == "DEPLOYING"  # policy remains Rayan's responsibility
    changed = plan_data()
    changed["lost_link_budget_s"] = 90
    with pytest.raises(PlanError, match="new plan_id"):
        plans.save(SearchPlan.model_validate(changed))


def test_multi_robot_dispatch_filters_zones_and_validates_every_assignment():
    sim = Sim(n_robots=2)
    report(sim.post)
    report(sim.post, rid="R2")
    data = plan_data()
    data["zones"].append({**data["zones"][0], "id": "Z2", "robot": "R2"})
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(data))
    assert plans.dispatch("P-1")["ok"]
    assert {b["dst"] for b in sim.network.queues["CMD"]} == {"R1", "R2"}
    for b in sim.network.queues["CMD"]:
        assert all(z["robot"] == b["dst"] for z in b["payload"]["zones"])


def test_plan_storage_returns_copies_and_rejects_out_of_bounds_geometry():
    sim = Sim()
    plans = manager(sim)
    plans.save(SearchPlan.model_validate(plan_data()))
    value = plans.current()
    value["zones"].clear()
    assert plans.current()["zones"]
    data = plan_data()
    data["zones"][0]["poly"][0][0] = -1
    with pytest.raises(PlanError):
        plans.save(SearchPlan.model_validate(data))
    with pytest.raises(PlanError, match="Unknown plan"):
        plans.dispatch("missing")


@pytest.mark.parametrize("poly", [
    [[0, 0], [1, 1]], [[0, 0], [1, 1], [2, 2]],
    [[0, 0], [2, 2], [0, 2], [2, 0]],
    [[0, 0], [0, 0], [2, 2], [0, 2]],
    [[0, 0], [float("nan"), 0], [0, 2]],
    [[0, 0], [float("inf"), 0], [0, 2]],
    [[0, 0], ["2", 0], [0, 2]],
])
def test_invalid_polygon_inputs_are_rejected(poly):
    data = plan_data()
    data["zones"][0]["poly"] = poly
    with pytest.raises(ValidationError):
        SearchPlan.model_validate(data)


def test_duplicate_region_ids_are_rejected_and_closed_polygons_normalize():
    data = plan_data()
    data["zones"][0]["poly"].append(data["zones"][0]["poly"][0])
    assert len(SearchPlan.model_validate(data).zones[0].poly) == 4
    data["zones"].append(data["zones"][0])
    with pytest.raises(ValidationError):
        SearchPlan.model_validate(data)
