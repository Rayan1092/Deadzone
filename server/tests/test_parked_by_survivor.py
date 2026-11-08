"""Tester's bug (2026-11-09): R1 reported TRAPPED right after parking beside a survivor it found.
A robot inside a survivor's 0.5 m clearance may always back away (only cells closer to the person
are blocked), and TRAPPED needs a real enclosure (no frontier and no way to the entrance)."""
import math

import numpy as np
import pytest

from deadzone.robot import planning
from deadzone.robot.mapping import FREE, OCC
from deadzone.robot.robot import SURVIVOR_CLEAR_M, Robot


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("DETECTOR", "sim")


def open_room_robot(pose):
    r = Robot("R1", "Scout 1", "#fff", pose, (40, 40), 0.25, (1.0, 5.0))
    r.map.grid[:, :] = FREE
    r.map.grid[0, :] = r.map.grid[-1, :] = r.map.grid[:, 0] = r.map.grid[:, -1] = OCC
    return r


def test_robot_parked_inside_the_clearance_can_back_away_but_never_closer():
    survivor = (5.0, 5.0)
    r = open_room_robot((5.3, 5.0, math.pi))          # 0.3 m from the person, facing them
    r.found["S1"] = {"pos": survivor}
    trav = r._drive_trav()
    mx, my = r._cell(*r.pose[:2])
    sx, sy = r._cell(*survivor)
    assert trav[my, mx]
    assert trav[my, mx + 1], "the cell away from the person is open"
    assert not trav[sy, sx] and not trav[my, mx - 1], "never toward the person"
    path = planning.astar(trav, (mx, my), r._cell(8.0, 5.0))
    assert path, "a way out from the parked pose exists"


def test_a_robot_outside_the_clearance_still_keeps_the_full_disk():
    r = open_room_robot((7.0, 5.0, 0.0))
    r.found["S1"] = {"pos": (5.0, 5.0)}
    trav = r._drive_trav()
    rad = int(math.ceil(SURVIVOR_CLEAR_M / r.cell))
    sx, sy = r._cell(5.0, 5.0)
    assert not trav[sy, sx + rad] and not trav[sy, sx - rad]


def test_trapped_only_inside_a_real_enclosure():
    r = open_room_robot((5.0, 5.0, 0.0))
    assert not r._enclosed(), "open room: the entrance is reachable"
    ix, iy = r._cell(5.0, 5.0)
    box = np.zeros_like(r.map.grid, dtype=bool)
    box[iy - 6:iy + 7, ix - 6:ix + 7] = True
    box[iy - 4:iy + 5, ix - 4:ix + 5] = False
    r.map.grid[box] = OCC                             # a sealed 2 m box around the robot
    assert r._enclosed()
