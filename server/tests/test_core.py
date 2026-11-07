import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FloorPlan, OCC  # noqa: E402
from deadzone.network.propagation import rssi  # noqa: E402
from deadzone.robot import planning  # noqa: E402
from deadzone.robot.lidar import raycast  # noqa: E402
from deadzone.sim import DEFAULT_PLAN, Sim  # noqa: E402

FP = FloorPlan.load(DEFAULT_PLAN)


def test_rssi_falls_with_distance_and_walls():
    near = rssi(FP, FP.cmd_pos, (3, 15))
    far = rssi(FP, FP.cmd_pos, (25, 15))
    assert near > far
    # same distance, but through walls into the east wing
    behind = rssi(FP, FP.cmd_pos, (37.5, 26))
    assert behind < -88, "east wing must be a dead zone for the demo"
    assert rssi(FP, FP.cmd_pos, (10, 15)) > -82, "corridor near the entry must be solid"


def test_lidar_hits_east_corridor_wall():
    # robot in the corridor facing north, wall at y = 17 is 2 m away
    angles, ranges, hits = raycast(FP.occ, FP.cell, (8.0, 15.0, math.pi / 2))
    i = int(np.argmin(np.abs(((angles - math.pi / 2) + np.pi) % (2 * np.pi) - np.pi)))
    assert hits[i] and abs(ranges[i] - 2.0) <= FP.cell


def test_astar_avoids_walls_and_finds_door():
    grid = np.where(FP.occ, OCC, 1).astype(np.uint8)
    trav = planning.traversable(grid, FP.nogo)
    path = planning.astar(trav, FP.to_cell(2, 15), FP.to_cell(5, 25))
    assert path is not None
    assert all(not FP.occ[y, x] for x, y in path)
    # nothing gets through the gas room
    assert planning.astar(trav, FP.to_cell(2, 15), FP.to_cell(18, 6)) is None


def test_core_story_one_robot():
    """Explore, lose signal, find the east wing survivor in the dark, report it later."""
    sim = Sim(n_robots=1, seed=7)
    found_dark = reported = None
    for _ in range(3000):
        sim.tick()
        for e in sim.drain_events():
            if e["kind"] == "survivor_found" and e["survivor"] == "S1" and not e["linked"]:
                found_dark = sim.time
            if e["kind"] == "survivor_reported" and e["survivor"] == "S1":
                reported = sim.time
        if reported:
            break
    assert found_dark is not None, "S1 should be found while the robot has no link"
    assert reported is not None and reported > found_dark


def test_command_view_never_leaks():
    """The command post never knows a survivor before a bundle carrying it arrived."""
    sim = Sim(n_robots=1, seed=7)
    for _ in range(1500):
        sim.tick()
        for sid, rec in sim.post.survivors.items():
            assert rec["reported_t"] >= rec["t"]
        known = sim.post.map > 0
        assert not (known & (sim.reality_map() == 0)).any()
