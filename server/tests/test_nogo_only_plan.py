"""Rayan's P0 (2026-11-08): a plan with no-go areas and no search zone is accepted. Robots keep
their current zone assignments and lost-link budget, every deployed robot gets the exclusion and
replans around it at once; a robot the no-go walls in holds in WAITING ("no reachable area,
holding") and resumes on its own when the no-go is edited or removed. Never driven through, never
refused."""
import math

import pytest

from deadzone.command.plan import PlanManager, SearchPlan
from deadzone.command.safety import SafetyChecker
from deadzone.geometry import points_in_poly
from deadzone.robot.robot import WAITING_PLAN_STATE
from deadzone.sim import Sim

ENTRY = (1.0, 15.0)
# across the main corridor (y 13-17) east of the entrance, west of every corridor door (x >= 4.6)
WALL_OFF = [[2.5, 12.5], [4.0, 12.5], [4.0, 17.5], [2.5, 17.5]]
# across the corridor further east: Office A and Storage stay reachable through their doors
MID_CORRIDOR = [[8.0, 12.5], [10.0, 12.5], [10.0, 17.5], [8.0, 17.5]]
ZONES = [{"id": "ZW", "robot": "R1", "priority": 1, "comms": "relay", "poly": [[0, 17], [20, 17], [20, 30], [0, 30]]},
         {"id": "ZNE", "robot": "R2", "priority": 1, "comms": "lost_link_ok", "poly": [[32, 17], [40, 17], [40, 30], [32, 30]]},
         {"id": "ZB", "robot": "R3", "priority": 1, "comms": "relay", "poly": [[20, 17], [32, 17], [32, 30], [20, 30]]}]


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("DETECTOR", "sim")
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "0")
    monkeypatch.delenv("DZ_GLOBAL_NO_GO", raising=False)


def plan(plan_id, zones=(), no_go=(), budget=60):
    return SearchPlan.model_validate({"plan_id": plan_id, "author": "judge-phone", "lost_link_budget_s": budget,
                                      "zones": list(zones),
                                      "no_go": [{"id": f"NG-{plan_id}", "poly": poly} for poly in no_go]})


def start():
    sim = Sim(n_robots=3, seed=7)
    sim.tick()                                     # Command hears every robot once
    plans = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
    return sim, plans


def run(sim, until, forbidden=None, log=None):
    while sim.time < until:
        sim.tick()
        events = sim.drain_events()
        if log is not None:
            log.extend((round(sim.time, 1), e) for e in events)
        if forbidden is not None:
            for rid, body in sim.bodies.items():
                assert not points_in_poly(body["x"], body["y"], forbidden), f"{rid} entered the no-go at {sim.time:.1f} s"


def test_no_go_only_plan_keeps_assignments_and_budget_and_reaches_every_robot():
    sim, plans = start()
    plans.save(plan("P-1", ZONES, budget=45))
    assert plans.dispatch("P-1")["ok"]
    run(sim, 3.0)
    before = {rid: [z["id"] for z in r.zones] for rid, r in sim.robots.items()}
    assert before == {"R1": ["ZW"], "R2": ["ZNE"], "R3": ["ZB"]}
    sim.network.queues["CMD"].clear()              # look only at the no-go plan's bundles below

    plans.save(plan("P-ng", no_go=[MID_CORRIDOR]))
    assert plans.check("P-ng") == {"ok": True, "plan_id": "P-ng", "violations": []}
    assert plans.dispatch("P-ng")["ok"]
    queued = list(sim.network.queues["CMD"])
    assert {b["dst"] for b in queued} == {"R1", "R2", "R3"}
    for b in queued:
        assert b["kind"] == "plan"
        assert [z["id"] for z in b["payload"]["zones"]] == before[b["dst"]], "the robot's current zones travel with it"
        assert b["payload"]["lost_link_budget_s"] == 45
        assert b["payload"]["no_go"][0]["id"] == "NG-P-ng"

    log = []
    run(sim, 6.0, log=log)
    applied = {e["robot"]: e for t, e in log if e["kind"] == "plan_applied" and e["plan_id"] == "P-ng"}
    assert set(applied) == {"R1", "R2", "R3"}
    assert {rid: [z["id"] for z in r.zones] for rid, r in sim.robots.items()} == before
    assert all(r.lost_budget == 45 for r in sim.robots.values())
    ix, iy = sim.fp.to_cell(9, 15)
    assert all(r.nogo[iy, ix] for r in sim.robots.values())
    run(sim, 60.0, forbidden=MID_CORRIDOR)
    # they search what the exclusion leaves them (Office A, Storage, the corridor stub) and then
    # hold for an edit; nobody drives home, nobody shuts down, nobody crosses
    states = {rid: r.state for rid, r in sim.robots.items()}
    assert all(s in ("EXPLORING", "REPLANNING", "WAITING") for s in states.values()), states
    assert any(r.pose[0] > 3.0 for r in sim.robots.values()), "they kept exploring west of the no-go"


def test_corridor_no_go_at_start_holds_all_three_at_the_entrance_then_resumes():
    sim, plans = start()
    plans.save(plan("P-wall", no_go=[WALL_OFF]))
    assert plans.check("P-wall")["ok"], "never refused"
    assert plans.dispatch("P-wall")["ok"]
    assert {b["dst"] for b in sim.network.queues["CMD"]} == {"R1", "R2", "R3"}
    log = []
    run(sim, 25.0, forbidden=WALL_OFF, log=log)
    waiting = {e["robot"] for t, e in log if e["kind"] == "robot_waiting"}
    assert waiting == {"R1", "R2", "R3"}
    for rid, r in sim.robots.items():
        assert r.state == "WAITING", (rid, r.state)
        assert r.telemetry(None)["plan_state"] == WAITING_PLAN_STATE
        assert r.telemetry(None)["state"] == "WAITING"
        assert math.dist(r.pose[:2], ENTRY) < 4.0, f"{rid} holds at the entrance, is at {r.pose[:2]}"
        assert r.fault is None and r.lights

    # the judge removes the no-go: an empty plan clears the exclusions, assignments unchanged
    plans.save(plan("P-open"))
    assert plans.dispatch("P-open")["ok"]
    t0 = sim.time
    log = []
    while sim.time < t0 + 2.0 and any(r.state == "WAITING" for r in sim.robots.values()):
        run(sim, sim.time + 0.1, log=log)
    assert all(r.state != "WAITING" for r in sim.robots.values()), \
        f"resume within 2 s: {[(rid, r.state) for rid, r in sim.robots.items()]}"
    assert {e["robot"] for t, e in log if e["kind"] == "robot_resumed"} == {"R1", "R2", "R3"}
    run(sim, t0 + 30.0)
    assert all(not r.nogo.any() or (r.nogo == r.base_nogo).all() for r in sim.robots.values())
    assert any(r.pose[0] > 5.0 for r in sim.robots.values()), "they move on east through the corridor"
    assert all(r.state not in ("WAITING", "DONE", "SHUTDOWN") for r in sim.robots.values())


def test_no_go_drawn_mid_run_is_held_not_driven_home(monkeypatch):
    """A robot already exploring whose path the new no-go cuts replans; if the no-go walls it in it
    holds (WAITING), it never goes DONE / SHUTDOWN through the exclusion."""
    sim, plans = start()
    plans.save(plan("P-1", ZONES))
    assert plans.dispatch("P-1")["ok"]
    run(sim, 2.0)                                   # robots have paths east through the corridor
    plans.save(plan("P-wall", no_go=[WALL_OFF]))
    assert plans.dispatch("P-wall")["ok"]
    log = []
    run(sim, 30.0, forbidden=WALL_OFF, log=log)
    states = {rid: r.state for rid, r in sim.robots.items()}
    assert all(s == "WAITING" for s in states.values()), states
    assert not any(e["kind"] in ("robot_shutdown",) for t, e in log)
    assert {rid: [z["id"] for z in r.zones] for rid, r in sim.robots.items()} == {"R1": ["ZW"], "R2": ["ZNE"], "R3": ["ZB"]}
