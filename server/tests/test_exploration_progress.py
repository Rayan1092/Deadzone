"""Room-entry, viewpoint commitment and collision-safe exploration regressions."""

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import itertools

from deadzone.floorplan import FREE, OCC
from deadzone.robot.exploration import (
    ProgressExplorer,
    line_clear,
    reachable_paths,
    safe_waypoints,
)
from deadzone.robot.robot import Robot
from deadzone.sim import Sim


def room(monkeypatch, enabled=True):
    monkeypatch.setenv("DZ_EXPLORATION_V2", "1" if enabled else "0")
    robot = Robot(
        "R1", "test", "#fff", (0.875, 4.125, 0), (32, 32), 0.25, (0.875, 4.125)
    )
    robot.state = "EXPLORING"
    robot.linked = True
    robot.t = 1
    robot.map.grid[:] = FREE
    robot.map.grid[[0, -1], :] = OCC
    robot.map.grid[:, [0, -1]] = OCC
    if robot.explorer is not None:
        robot.explorer.observe(robot.map.grid, robot.pose, robot.t, True)
    return robot


def test_mapped_room_is_entered_when_camera_has_not_searched_it(monkeypatch):
    legacy = room(monkeypatch, False)
    assert not legacy._plan_frontier()  # lidar knows the room, so there is no frontier
    robot = room(monkeypatch)
    assert robot._plan_frontier()
    assert math.dist(robot.pose[:2], robot.target) > 2
    assert robot.target[0] > 3  # head inside, not back to the doorway
    assert all(
        line_clear(robot._trav(), a, b, robot.cell)
        for a, b in zip(robot.path, robot.path[1:])
    )


def test_camera_coverage_respects_fov_range_and_mapped_occlusion():
    grid = np.full((48, 48), FREE, dtype=np.uint8)
    grid[:, 24] = OCC
    explorer = ProgressExplorer(grid.shape, 0.25)
    explorer.observe(grid, (3.125, 6.125, 0), 1, True)
    assert explorer.surveyed[:, 13:24].any()
    assert not explorer.surveyed[:, 25:].any()  # other side of the wall
    assert not explorer.surveyed[:, :12].any()  # behind the camera
    ys, xs = np.nonzero(explorer.surveyed)
    assert np.hypot((xs + 0.5) * 0.25 - 3.125, (ys + 0.5) * 0.25 - 6.125).max() < 5.2


def test_committed_goal_survives_periodic_replanning(monkeypatch):
    robot = room(monkeypatch)
    assert robot._plan_frontier()
    goal = robot.goal_cell
    path = robot.path.copy()
    searches = robot.explorer.searches
    for tick in range(2, 8):
        robot.t = float(tick)
        assert robot._plan_frontier()
        assert robot.goal_cell == goal and robot.path == path
    assert robot.explorer.searches == searches


def test_arrival_sweeps_camera_then_moves_to_a_new_view(monkeypatch):
    robot = room(monkeypatch)
    robot._plan_frontier()
    old = robot.target.copy()
    robot.pose[:2] = old
    robot.path = []
    robot.t = 2
    assert robot._plan_frontier() and robot.explorer.scan_left > 0
    before = robot.explorer.surveyed.sum()
    for tick in range(36):
        robot.t += 0.1
        robot.pose[2] += 0.18
        robot.explorer.observe(robot.map.grid, robot.pose, robot.t, True)
    assert robot.explorer.scan_left < 0.05
    assert robot.explorer.surveyed.sum() > before
    if robot._plan_frontier():
        assert math.dist(old, robot.target) >= 1


def test_search_and_smoothing_never_cut_diagonal_obstacle_corners():
    grid = np.array([[FREE, OCC], [OCC, FREE]], dtype=np.uint8)
    trav = grid == FREE
    distances, _, _, _ = reachable_paths(trav, grid, (0, 0), 1)
    assert np.isinf(distances[1, 1])
    assert not line_clear(trav, (0.5, 0.5), (1.5, 1.5), 1)
    trav = np.ones((8, 8), dtype=bool)
    trav[2:6, 3] = False
    cells = [
        (1, 4),
        (1, 3),
        (1, 2),
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 1),
        (5, 1),
        (5, 2),
        (5, 3),
        (5, 4),
    ]
    path = safe_waypoints(cells, trav, 1)
    assert all(line_clear(trav, a, b, 1) for a, b in itertools.pairwise(path))


def test_visible_lookahead_advances_path_permanently(monkeypatch):
    robot = room(monkeypatch)
    robot.pose = [4.125, 4.125, math.pi]
    robot.path = [(4.875, 4.625), (3.625, 3.375), (1.875, 3.125)]
    robot._follow()
    assert (4.875, 4.625) not in robot.path
    # Crossing the old 1m lookahead boundary cannot resurrect the discarded point.
    robot.pose[:2] = [4.05, 4.05]
    robot._follow()
    assert (4.875, 4.625) not in robot.path


def test_mapped_zone_is_not_complete_until_camera_survey(monkeypatch):
    robot = room(monkeypatch)
    mask = np.ones(robot.map.grid.shape, dtype=bool)
    zone = {"id": "Z", "mask": mask}
    assert not robot._zone_complete(zone)
    robot.explorer.surveyed[:] = True
    assert robot._zone_complete(zone)
    legacy = room(monkeypatch, False)
    assert legacy._zone_complete(zone)


def test_new_obstacle_invalidates_committed_path(monkeypatch):
    robot = room(monkeypatch)
    assert robot._plan_frontier()
    old = robot.goal_cell
    robot.map.grid[old[1], old[0]] = OCC
    robot.path = []  # obstacle recovery clears the path before asking for a replacement
    robot.t += 1
    assert robot._plan_frontier()
    assert robot.goal_cell != old
    assert all(
        line_clear(robot._trav(), a, b, robot.cell)
        for a, b in zip(robot.path, robot.path[1:])
    )


def test_peer_coverage_comes_from_delivered_poses_and_keeps_own_observations_separate(
    monkeypatch,
):
    robot = room(monkeypatch)
    before = robot.explorer.surveyed.copy()
    assert not robot.explorer.team_surveyed.any()
    robot._learn_peer(
        {
            "kind": "telemetry",
            "created": 1,
            "payload": {"id": "R2", "pose": [6, 4, math.pi]},
        }
    )
    assert robot.explorer.team_surveyed.any()
    assert np.array_equal(robot.explorer.surveyed, before)
    for invalid in (None, [], [float("nan"), 1, 0], ["bad", 1, 0]):
        robot.explorer.observe_peer(robot.map.grid, invalid)


def test_safety_return_to_signal_interrupts_camera_sweep(monkeypatch):
    robot = room(monkeypatch)
    robot.explorer.scan_left = 2
    robot.explorer.scan_deadline = 100
    robot.linked = False
    robot.dark_declared = True
    robot.found_while_dark = True
    robot._behave()
    assert robot.state == "RETURNING_TO_SIGNAL"
    _, turn = robot._follow()
    assert turn != 1.8  # camera search cannot override a required radio return


def test_no_go_and_unknown_cells_are_never_used_as_shortcuts(monkeypatch):
    robot = room(monkeypatch)
    robot.nogo[:, 20:] = True
    robot.map.grid[:12, 8:20] = 0
    assert robot._plan_frontier()
    assert all(
        line_clear(robot._trav(), a, b, robot.cell)
        for a, b in zip(robot.path, robot.path[1:])
    )
    for x, y in robot.path:
        ix, iy = robot._cell(x, y)
        assert robot.map.grid[iy, ix] == FREE and not robot.nogo[iy, ix]


def test_intentional_camera_turn_does_not_raise_stuck_on_resuming_travel(monkeypatch):
    robot = room(monkeypatch)
    robot.cmd_v = 0.0
    for tick in range(40):
        robot.t = tick * 0.1
        robot._check_faults({"blocked": False})
    robot.t = 4.0
    robot.cmd_v = 0.4
    robot._check_faults({"blocked": False})
    assert robot.fault is None
    # A genuine failure to move while driving still raises the safety fault.
    robot.t = 7.1
    robot._check_faults({"blocked": False})
    assert robot.fault == "STUCK"


def test_new_operator_task_cancels_old_scan_without_forgetting_coverage(monkeypatch):
    robot = room(monkeypatch)
    coverage = robot.explorer.surveyed.copy()
    robot.explorer.scan_left = 2
    robot.explorer.scan_deadline = 100
    robot.explorer.goal = (10, 10)
    robot._on_command(
        {
            "cmd_id": "new-room",
            "cmd": "explore_zone",
            "zone": {
                "id": "A",
                "name": "Room A",
                "poly": [[1, 1], [7, 1], [7, 7], [1, 7]],
            },
        }
    )
    assert robot.explorer.goal is None and robot.explorer.scan_left == 0
    assert np.array_equal(robot.explorer.surveyed, coverage)
    assert robot.cmds["new-room"]["status"] == "accepted"
    assert "already searched" not in robot.cmds["new-room"]["say"]
    assert robot.active_cmd is not None  # lidar coverage alone cannot complete it


def test_robot_physically_enters_room_and_finds_person_beyond_doorway_camera_range(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DZ_EXPLORATION_V2", "1")
    monkeypatch.setenv("DZ_MODE", "deadzone")
    plan = {
        "id": "room-entry-test",
        "name": "room entry",
        "size": [14, 10],
        "cell": 0.25,
        "materials": {"brick": 4, "rubble": 8},
        "entry": [0.8, 1.5],
        "command_post": {"pos": [-2, 1.5], "tx_dbm": 30},
        "walls": [
            {"a": a, "b": b, "material": "brick"}
            for a, b in (
                ([0, 0], [14, 0]),
                ([14, 0], [14, 10]),
                ([14, 10], [0, 10]),
                ([0, 10], [0, 2.5]),
                ([0, 0.5], [0, 0]),
                ([0, 3], [3, 3]),
                ([5, 3], [14, 3]),
            )
        ],
        "rooms": [
            {"id": "A", "name": "Room A", "poly": [[0, 3], [14, 3], [14, 10], [0, 10]]}
        ],
        "rubble": [],
        "hazards": [],
        "survivors": [{"id": "S1", "pos": [12, 8], "thermal": "pos_0001.png"}],
    }
    path = tmp_path / "room.json"
    path.write_text(json.dumps(plan))
    sim = Sim(plan_path=path, n_robots=1, seed=7)
    entered = False
    while sim.time < 120 and "S1" not in sim.robots["R1"].found:
        sim.tick()
        sim.drain_events()
        entered |= sim.robots["R1"].pose[1] > 3.75
    assert entered
    assert "S1" in sim.robots["R1"].found
