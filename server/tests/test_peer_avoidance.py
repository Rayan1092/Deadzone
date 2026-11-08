"""Robots never drive through each other: peers' delivered poses are dynamic obstacles for
planning, and the lower-priority robot (R1 > R2 > R3) yields when a higher-priority peer is close,
ahead and closing, sidestepping after PEER_WAIT_S. Only delivered poses count (lidar does not see
robots); the sim's hard body collision is the physical backstop."""
import itertools
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from deadzone.floorplan import FREE, OCC  # noqa: E402
from deadzone.robot.robot import PEER_BLOCK_M, PEER_POSE_FRESH_S, PEER_WAIT_S, PEER_YIELD_M, Robot  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def robot(rid, pose=(4.125, 4.125, 0.0)):
    os.environ["DZ_PEER_AVOID"] = "1"
    r = Robot(rid, "test", "#fff", pose, (32, 32), 0.25, (0.875, 4.125))
    os.environ.pop("DZ_PEER_AVOID", None)
    r.state = "EXPLORING"
    r.linked = True
    r.t = 10.0
    r.map.grid[:] = FREE
    r.map.grid[[0, -1], :] = OCC
    r.map.grid[:, [0, -1]] = OCC
    r.path = [(7.0, 4.125)]
    return r


def peer(r, pid, pos, age=0.5, vel=(-0.8, 0.0)):
    """A delivered peer pose; by default the peer drives toward -x (oncoming for a robot facing +x)."""
    r.peers[pid] = {"target": None, "pose": [pos[0], pos[1], math.pi], "vel": list(vel), "relays": [], "found": [],
                    "t": r.t - age}


def test_lower_priority_robot_yields_to_a_closing_higher_priority_peer_ahead():
    r2 = robot("R2")
    peer(r2, "R1", (5.4, 4.125))                 # 1.3 m ahead: beyond PEER_YIELD_M
    assert r2._yield_to_peers(0.8, 0.0) == (0.8, 0.0)
    peer(r2, "R1", (5.125, 4.125))               # 1.0 m ahead, oncoming, on our segment
    assert r2._yield_to_peers(0.8, 0.0) == (0.0, 0.0)
    assert r2.yield_to == "R1" and r2.counters["peer_yields"] == 1
    assert any(e["kind"] == "peer_yield" and e["peer"] == "R1" for e in r2.events)


def test_priority_behind_leaving_and_stale_peers_do_not_make_a_robot_yield():
    r1 = robot("R1")
    peer(r1, "R2", (5.0, 4.125), vel=(0.0, 0.0))                 # a stopped R2 on R1's segment
    assert r1._yield_to_peers(0.8, 0.0) == (0.8, 0.0)          # R1 has right of way: keeps moving ...
    assert r1.path == [] and r1.avoid_peers                      # ... but replans around it
    r1 = robot("R1")
    peer(r1, "R2", (5.0, 4.125), vel=(0.8, 0.0))                 # R2 ahead and leaving: just follow
    assert r1._yield_to_peers(0.8, 0.0) == (0.8, 0.0) and r1.path
    r2 = robot("R2")
    peer(r2, "R1", (3.2, 4.125))                                 # behind us
    assert r2._yield_to_peers(0.8, 0.0) == (0.8, 0.0)
    r2 = robot("R2")
    peer(r2, "R1", (5.1, 4.125), vel=(0.8, 0.0))                 # ahead but leaving: we follow, no yield
    assert r2._yield_to_peers(0.8, 0.0) == (0.8, 0.0)
    r2 = robot("R2")
    peer(r2, "R1", (5.0, 5.0))                                   # ahead-left but not on our segment
    assert r2._yield_to_peers(0.8, 0.0) == (0.8, 0.0)
    r2 = robot("R2")
    peer(r2, "R1", (5.0, 4.125), age=PEER_POSE_FRESH_S + 1)      # too old to trust
    assert r2._yield_to_peers(0.8, 0.0) == (0.8, 0.0)
    r2 = robot("R2")
    r2.state = "DEPLOYING"
    peer(r2, "R1", (4.9, 4.125))
    assert r2._yield_to_peers(0.8, 0.0) == (0.8, 0.0)           # parked robots are left alone


def test_waiting_too_long_drops_the_path_so_the_next_plan_sidesteps():
    r2 = robot("R2")
    peer(r2, "R1", (5.0, 4.125))
    r2._yield_to_peers(0.8, 0.0)
    assert r2.path
    r2.t += PEER_WAIT_S + 0.2
    peer(r2, "R1", (5.0, 4.125))
    assert r2._yield_to_peers(0.8, 0.0) == (0.0, 0.0) and r2.path == [] and r2.avoid_peers
    trav = r2._drive_trav()                                     # the waited-for peer gets the wide berth
    cx, cy = r2._cell(5.0, 4.125)
    assert not trav[cy, cx] and not trav[cy, cx + int(PEER_YIELD_M / r2.cell) - 1]


def test_fresh_peers_block_motion_plans_but_not_the_obstacle_check():
    r2 = robot("R2")
    peer(r2, "R3", (5.0, 4.125))
    cx, cy = r2._cell(5.0, 4.125)
    assert r2._drive_trav()[cy, cx]                             # ordinary plans ignore peers ...
    r2.avoid_peers = True                                       # ... until an encounter asks for it
    assert not r2._drive_trav()[cy, cx]
    assert not r2._drive_trav()[cy, cx + int(PEER_BLOCK_M / r2.cell) - 1]
    assert r2._drive_trav(peers=False)[cy, cx] and r2._trav()[cy, cx]
    mx, my = r2._cell(*r2.pose[:2])
    assert r2._drive_trav()[my, mx]                             # own cell stays open
    assert not r2._path_blocked()                               # a robot on the path is not "new rubble"
    assert r2._plan_to((7.0, 4.125))
    assert all(math.dist(p, (5.0, 4.125)) >= PEER_BLOCK_M - r2.cell for p in r2.path)


def test_flag_off_is_a_no_op():
    os.environ.pop("DZ_PEER_AVOID", None)
    r2 = Robot("R2", "test", "#fff", (4.125, 4.125, 0.0), (32, 32), 0.25, (0.875, 4.125))
    r2.state, r2.t, r2.path = "EXPLORING", 10.0, [(7.0, 4.125)]
    peer(r2, "R1", (5.0, 4.125))
    assert r2._yield_to_peers(0.8, 0.0) == (0.8, 0.0) and r2.path and not r2.events


def test_seed_7_robots_keep_apart(monkeypatch):
    """Same demo run as the guard (3 robots, seed 7, P-1) with DZ_PEER_AVOID=1: fewer
    near-collisions than before the rule (25 ticks under 0.6 m, closest 0.19 m) and no overlap."""
    from test_demo_guard import demo_plan
    from deadzone.command.plan import PlanManager, SearchPlan
    from deadzone.command.safety import SafetyChecker
    monkeypatch.setenv("DZ_PEER_AVOID", "1")
    sim = Sim(n_robots=3, seed=7)
    sim.tick()
    plans = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
    plans.save(SearchPlan.model_validate(demo_plan("P-1", "lost_link_ok")))
    assert plans.dispatch("P-1")["ok"]
    closest, under = 99.0, 0
    while sim.time < 250:
        sim.tick()
        for a, b in itertools.combinations(sim.bodies.values(), 2):
            d = math.dist((a["x"], a["y"]), (b["x"], b["y"]))
            closest = min(closest, d)
            under += d < 0.6
    assert closest >= 0.35, closest                             # never inside each other
    assert under < 25, under
