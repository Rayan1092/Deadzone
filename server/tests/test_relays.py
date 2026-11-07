import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FREE, OCC  # noqa: E402
from deadzone.robot.power import RESERVE_PCT, Battery  # noqa: E402
from deadzone.robot.robot import RELAYS_PER_ROBOT, Robot, is_robot_id  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def test_robot_ids_vs_infrastructure():
    assert is_robot_id("R1") and is_robot_id("R12")
    assert not any(is_robot_id(n) for n in ("RL1", "CMD", "PH1"))


def test_dropped_relays_extend_the_network():
    """Relays drop on their own, keep 4 m spacing, and each one links back to CMD."""
    sim = Sim(n_robots=1, seed=7)
    useful = set()
    while sim.time < 160:
        sim.tick()
        sim.drain_events()
        for rid in sim.relays:
            if sim.links.path(rid, "CMD", avoid=tuple(sim.robots)):   # route with no robot hop
                useful.add(rid)
    r = sim.robots["R1"]
    assert len(sim.relays) >= 2 and r.relays_left == RELAYS_PER_ROBOT - len(sim.relays)
    assert useful == set(sim.relays), "a relay was dropped where it can never reach CMD"
    pos = [rl["pos"] for rl in sim.relays.values()]
    assert all(math.dist(a, b) >= 4.0 for i, a in enumerate(pos) for b in pos[i + 1:])
    assert sim.snapshot()["reality"]["robots"][0]["relays_left"] == r.relays_left


def test_home_cost_follows_the_astar_path():
    """A wall between robot and entry makes the A* distance longer than the straight line."""
    h, w, cell = 40, 40, 0.25
    robot = Robot("R1", "Scout 1", "#fff", (8.0, 2.0, 0.0), (h, w), cell, (2.0, 2.0))
    grid = np.full((h, w), FREE, dtype=np.uint8)
    grid[0:30, 20] = OCC           # wall at x = 5 m with a gap at the top
    robot.map.grid = grid
    robot.t = 10.0
    pct = robot._pct_home()
    straight = math.dist((8.0, 2.0), (2.0, 2.0))
    assert robot.home_m > straight + 8.0      # must detour around the wall end
    assert pct == Battery.pct_to_drive(robot.home_m)


def test_low_battery_sends_robot_home():
    sim = Sim(n_robots=1, seed=7)
    r = sim.robots["R1"]
    while sim.time < 40:
        sim.tick()
    assert r.state in ("EXPLORING", "LOST_LINK_EXPLORING")
    # leave just under the reserve plus the trip home
    r.battery.wh = (RESERVE_PCT + r._pct_home() - 0.5) / 100.0 * 90.0
    sim.tick()
    assert r.state == "RETURNING_HOME"
    for _ in range(1200):
        sim.tick()
        if r.state == "DONE":
            break
    assert r.state == "DONE" and math.dist(r.pose[:2], r.entry) < 0.6
