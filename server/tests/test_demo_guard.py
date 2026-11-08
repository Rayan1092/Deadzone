"""Demo guard: replays the docs/DEMO.md demo and fails if any beat moves.

Seed 7, 3 robots, solid furniture on (DZ_OBSTACLES=1, the main-run setting since the
2026-11-08 20:30 re-baseline), plan P-1 (rejected: R2's north-east zone is a dead zone) then
fixed to lost_link_ok and dispatched after the startup tick, exactly like the phone beat.
Robot collisions on (DZ_ROBOT_COLLISIONS=1, main run since 2026-11-08 23:50). The reroute beat
is not a key press: collapse_01.json's scenario event (`events`: collapse at [25.31, 15.65], on
S1's rescue route by the break-room door, at 162.5 s; rubble_fall, cause "collapse") lands 3.3 m
ahead of R1 with R2 3 m away. Director presses at the DEMO.md times: F (overcurrent on R3)
at 177.5 s, O (perception overload on R1) at 187.5 s.

If you change robot, network or floor plan behavior and a beat moves, this fails on purpose.
Re-measure, update the BEATS table below AND docs/DEMO.md together, and tell the team.
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.command.plan import PlanManager, SearchPlan  # noqa: E402
from deadzone.command.safety import SafetyChecker  # noqa: E402
from deadzone.robot import perception  # noqa: E402
from deadzone.sim import Sim  # noqa: E402

TOL = 0.25            # seconds of sim time (2 ticks); any real change moves a beat further

# Sim-time beats from docs/DEMO.md (keep both in sync)
BEATS = {
    "S3_found": 14.1,       # R1, linked
    "D1_rejected": 57.9,    # R1, trained model only (decoys are off in sim fallback)
    "RL1_dropped": 67.5,    # R3
    "R2_dark": 91.3,        # R2 enters the steel cage
    "S1_found": 102.7,      # R2, dark, beacon next to the survivor
    "S1_reported": 118.5,   # S1 + rescue route reach Command
    "S1_rerouted": 162.8,   # R2 sees the collapse rubble on S1's rescue route and resends it
    "S2_found": 217.2,      # the finale, only with F/O on time (219.4 before robot collisions)
}
COLLAPSE_AT = 162.5     # collapse_01.json scenario event: collapse near R1
DIRECTOR = {177.5: ("overcurrent", "R3"), 187.5: ("overload", "R1")}
END = 230.0
FLAGS = {"DZ_OBSTACLES": "1", "DZ_SMART_RUBBLE": "1", "DZ_ROBOT_COLLISIONS": "1"}   # the main run's environment (docs/DEMO.md pre-flight step 4)

ZW = [[0, 17], [20, 17], [20, 30], [0, 30]]
ZB = [[20, 17], [32, 17], [32, 30], [20, 30]]
ZNE = [[32, 17], [40, 17], [40, 30], [32, 30]]


def demo_plan(plan_id, ne_comms):
    return {"plan_id": plan_id, "author": "judge-phone", "lost_link_budget_s": 60, "no_go": [], "zones": [
        {"id": "ZW", "robot": "R1", "priority": 1, "comms": "relay", "poly": ZW},
        {"id": "ZNE", "robot": "R2", "priority": 1, "comms": ne_comms, "poly": ZNE},
        {"id": "ZB", "robot": "R3", "priority": 1, "comms": "relay", "poly": ZB}]}


@pytest.fixture(scope="module")
def run():
    with pytest.MonkeyPatch.context() as env:
        for k, v in FLAGS.items():
            env.setenv(k, v)
        return _run()


def _run():
    perception.reset_detector()
    sim = Sim(n_robots=3, seed=7)
    sim.tick()                                     # startup tick: Command hears the robots
    plans = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
    plans.save(SearchPlan.model_validate(demo_plan("P-1", "relay")))
    rejected = plans.check("P-1")
    plans.save(SearchPlan.model_validate(demo_plan("P-1", "lost_link_ok")))   # "Allow ZNE to go dark"
    accepted = plans.check("P-1")
    dispatched = plans.dispatch("P-1")
    log = []
    while sim.time < END:
        act = DIRECTOR.get(round(sim.time, 1))
        if act:
            name, rid = act
            r = sim.robots[rid]
            if name == "rubble":        # the R key, as the screen sends it (1.5 m ahead of the followed robot)
                x, y, th = r.pose
                sim.press_rubble((x + math.cos(th) * 1.5, y + math.sin(th) * 1.5))
            elif name == "overcurrent":
                r.inject_overcurrent()
            else:
                r.inject_perception_overload()
        sim.tick()
        log += [(round(sim.time, 1), e) for e in sim.drain_events()]
    return {"sim": sim, "log": log, "rejected": rejected, "accepted": accepted, "dispatched": dispatched,
            "detector": perception.get_detector().mode}


def first(log, pred):
    return next(((t, e) for t, e in log if pred(e)), (None, None))


def at(beat, t):
    assert t is not None, f"{beat} never happened"
    assert abs(t - BEATS[beat]) <= TOL, f"{beat} moved: {t} s, DEMO.md says {BEATS[beat]} s"


def test_safety_beat_rejects_then_accepts(run):
    assert not run["rejected"]["ok"]
    assert {(v["robot"], v["zone"], v["rule"]) for v in run["rejected"]["violations"]} == {("R2", "ZNE", "comms_plan")}
    assert run["accepted"]["ok"] and run["dispatched"]["ok"]
    applied = {e["robot"] for t, e in run["log"] if e["kind"] == "plan_applied" and t <= 1.0}
    assert applied == {"R1", "R2", "R3"}


def test_s3_found_linked_and_reported_at_once(run):
    t, e = first(run["log"], lambda e: e["kind"] == "survivor_found" and e["survivor"] == "S3")
    at("S3_found", t)
    assert e["robot"] == "R1" and e["linked"]
    t2, _ = first(run["log"], lambda e: e["kind"] == "survivor_reported" and e["survivor"] == "S3")
    assert t2 == t


def test_radiator_rejected_by_the_model(run):
    if run["detector"] != "model":
        pytest.skip("trained model not loaded: decoys are off in sim fallback")
    t, e = first(run["log"], lambda e: e["kind"] == "hotspot_rejected" and e["id"] == "D1")
    at("D1_rejected", t)
    assert e["robot"] == "R1"


def test_first_relay(run):
    t, e = first(run["log"], lambda e: e["kind"] == "relay_dropped")
    at("RL1_dropped", t)
    assert e["id"] == "RL1" and e["owner"] == "R3"


def test_dark_moment(run):
    log = run["log"]
    t_dark, _ = first(log, lambda e: e["kind"] == "link_lost" and e["robot"] == "R2")
    at("R2_dark", t_dark)
    t, e = first(log, lambda e: e["kind"] == "survivor_found" and e["survivor"] == "S1")
    at("S1_found", t)
    assert e["robot"] == "R2" and not e["linked"] and e["conf"] >= 0.6
    tb, b = first(log, lambda e: e["kind"] == "relay_dropped" and e.get("beacon_for") == "S1")
    assert tb == t and b["owner"] == "R2"
    tr, route = first(log, lambda e: e["kind"] == "rescue_route" and e["survivor"] == "S1")
    assert tr == t and route["beacon"] == b["id"] and 45 < route["length_m"] < 55


def test_s1_reaches_command_late(run):
    log = run["log"]
    t, e = first(log, lambda e: e["kind"] == "survivor_reported" and e["survivor"] == "S1")
    at("S1_reported", t)
    assert e["delay_s"] >= 10
    tr, _ = first(log, lambda e: e["kind"] == "rescue_route_reported"
                  and (e.get("survivor_id") or e.get("survivor")) == "S1")
    assert tr == t, "the rescue route arrives with the survivor report"


def test_director_beats(run):
    log = run["log"]
    falls = [(t, e) for t, e in log if e["kind"] == "rubble_fall"]
    assert [(t, e.get("cause"), e.get("robot")) for t, e in falls] == [(round(COLLAPSE_AT + 0.1, 1), "collapse", "R1")], \
        f"exactly one scripted collapse ahead of R1, nothing pressed: {falls}"
    t = next((t for t, e in log if t >= COLLAPSE_AT and e["kind"] == "replan" and e["robot"] == "R1"), None)
    # the rubble is pinned 3.3 m ahead of R1 (path check 3 m): R1 replans at 164.0 with collisions on
    assert t is not None and t <= COLLAPSE_AT + 2.0, f"collapse: R1 replan at {t}"
    t, e = first(log, lambda e: e["kind"] == "fault" and e["robot"] == "R3")
    assert t is not None and 177.5 <= t <= 178.5 and e["fault"] == "OVERCURRENT", f"F key: {t} {e}"
    misses = [t for t, e in log if e["kind"] == "deadline_miss" and e["robot"] == "R1"]
    assert misses and all(187.5 <= t <= 191.5 for t in misses), f"O key: misses at {misses}"
    assert not any(e["kind"] == "deadline_miss" and e["task"] == "safety" for _, e in log)


def test_s2_finale(run):
    t, e = first(run["log"], lambda e: e["kind"] == "survivor_found" and e["survivor"] == "S2")
    at("S2_found", t)
    assert e["linked"]


def test_no_decoy_ever_reported(run):
    found = {e["survivor"] for _, e in run["log"] if e["kind"] == "survivor_found"}
    assert found <= {"S1", "S2", "S3"}


def test_rescue_routes_in_the_demo(run):
    """The scripted collapse (162.5 s) lands on S1's rescue corridor with R2 4 m away. R2's lidar
    sees it, R2 reroutes S1's route and resends it (Command replaces the old one); nothing else
    is resent."""
    log = run["log"]
    routes = [(e["survivor"], e.get("reason")) for _, e in log if e["kind"] == "rescue_route"]
    assert routes == [("S3", "found"), ("S1", "found"), ("S1", "blocked"), ("S2", "found")], routes
    t, e = first(log, lambda e: e["kind"] == "rescue_route" and e.get("reason") == "blocked")
    at("S1_rerouted", t)
    assert e["robot"] == "R2" and 50 < e["length_m"] < 56
    tr = next((tt for tt, ee in log if tt >= t and ee["kind"] == "rescue_route_reported"
               and ee.get("survivor") == "S1"), None)
    assert tr == t, "R2 is linked, so the rerouted S1 route reaches Command at once"
    assert not any(e["kind"] == "rescue_route_blocked" for _, e in log)
