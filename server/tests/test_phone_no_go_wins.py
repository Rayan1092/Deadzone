"""A no-go area drawn on the phone must actually keep the robots out, even when it overlaps a search
zone (it almost always does: the zones cover the building). It used to refuse the whole plan
(`no_go_overlap`), so nothing reached the robots and they drove straight through. Now a conflict
caused only by the plan's own no-go is a warning: the plan is dispatched and every robot obeys it.
Building hazards, walls and a blocked route home still refuse (tests/test_plans.py, test_global_no_go.py)."""
import pytest

from deadzone.command.plan import PlanManager, SearchPlan
from deadzone.command.safety import SafetyChecker
from deadzone.geometry import points_in_poly
from deadzone.sim import Sim

ZONES = [{"id": "ZW", "robot": "R1", "priority": 1, "comms": "relay", "poly": [[0, 17], [20, 17], [20, 30], [0, 30]]},
         {"id": "ZNE", "robot": "R2", "priority": 1, "comms": "lost_link_ok", "poly": [[32, 17], [40, 17], [40, 30], [32, 30]]},
         {"id": "ZB", "robot": "R3", "priority": 1, "comms": "relay", "poly": [[20, 17], [32, 17], [32, 30], [20, 30]]}]
BREAK_ROOM = [[20, 17], [32, 17], [32, 30], [20, 30]]      # all of R3's zone
PART_OF_ZB = [[24, 20], [28, 20], [28, 26], [24, 26]]      # a piece of it


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("DETECTOR", "sim")
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "0")
    monkeypatch.delenv("DZ_GLOBAL_NO_GO", raising=False)


def plan(plan_id, no_go=()):
    return SearchPlan.model_validate({"plan_id": plan_id, "author": "phone", "lost_link_budget_s": 60, "zones": ZONES,
                                      "no_go": [{"id": f"NG{i}", "poly": p} for i, p in enumerate(no_go)]})


def start():
    sim = Sim(n_robots=3, seed=7)
    sim.tick()
    plans = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
    plans.save(plan("P-1"))
    assert plans.dispatch("P-1")["ok"]
    return sim, plans


@pytest.mark.parametrize("poly,rules", [(PART_OF_ZB, {"no_go_overlap"}), (BREAK_ROOM, {"no_go_overlap"})])
def test_no_go_over_a_zone_is_sent_with_a_warning(poly, rules):
    sim, plans = start()
    plans.save(plan("P-2", [poly]))
    result = plans.check("P-2")
    assert result["ok"], result["violations"]
    assert rules <= {w["rule"] for w in result["warnings"]}
    assert all(w["level"] == "warning" for w in result["warnings"])
    assert plans.dispatch("P-2")["ok"]


def body_inside(x, y, poly, radius=0.3):
    """The robot's body (radius 0.3 m) overlaps the polygon: its centre or any point of its rim."""
    rim = [(x + radius * dx, y + radius * dy) for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (.7, .7), (-.7, .7), (.7, -.7), (-.7, -.7))]
    return any(points_in_poly(px, py, poly) for px, py in rim)


@pytest.mark.parametrize("poly", [BREAK_ROOM, PART_OF_ZB], ids=["whole zone", "part of a zone"])
def test_robots_obey_a_phone_no_go_that_overlaps_their_zones(poly):
    sim, plans = start()
    while sim.time < 40:
        sim.tick()
        sim.drain_events()
    plans.save(plan("P-2", [poly]))
    assert plans.dispatch("P-2")["ok"]
    BREAK = poly
    applied, inside_at_send = {}, {rid: body_inside(b["x"], b["y"], BREAK) for rid, b in sim.bodies.items()}
    while sim.time < 240:
        sim.tick()
        for e in sim.drain_events():
            if e.get("kind") == "plan_applied" and e.get("plan_id") == "P-2":
                applied.setdefault(e["robot"], sim.time)
        for rid, body in sim.bodies.items():
            inside = body_inside(body["x"], body["y"], BREAK)
            if not inside:
                inside_at_send[rid] = False          # a robot already inside walks out; it may never return
            elif not inside_at_send[rid] and rid in applied:
                pytest.fail(f"{rid} entered the no-go at {sim.time:.1f} s after applying P-2 at {applied[rid]:.1f} s")
    assert applied, "nobody received the plan"


def test_hazard_overlap_and_blocked_home_still_refuse():
    sim, plans = start()
    home_block = [[0, 13], [3, 13], [3, 17], [0, 17]]          # over the entry (1, 15)
    plans.save(plan("P-3", [home_block]))
    assert not plans.check("P-3")["ok"]
