"""DZ_EXPLORATION_V2 path following must respect the survivor clearance disk (review finding A1).

The V2 follower shortcuts to path[1] whenever the straight line is clear. That check has to run on
the same survivor-aware mask the path was planned on (_drive_trav), or a detour around a confirmed
survivor gets cut straight across the person."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FREE, OCC  # noqa: E402
from deadzone.robot.exploration import line_clear  # noqa: E402
from deadzone.robot.robot import Robot  # noqa: E402


def v2_robot(monkeypatch):
    monkeypatch.setenv("DZ_EXPLORATION_V2", "1")
    robot = Robot("R1", "test", "#fff", (4.125, 4.125, 0), (32, 32), 0.25, (0.875, 4.125))
    robot.state = "EXPLORING"
    robot.linked = True
    robot.t = 1.0
    robot.map.grid[:] = FREE
    robot.map.grid[[0, -1], :] = OCC
    robot.map.grid[:, [0, -1]] = OCC
    assert robot.explorer is not None
    return robot


def test_v2_shortcut_never_cuts_across_a_confirmed_survivor(monkeypatch):
    robot = v2_robot(monkeypatch)
    robot.found = {"S1": {"pos": [4.9, 4.125]}}            # confirmed person 0.8 m straight ahead
    detour, beyond = (4.7, 4.8), (5.7, 4.125)              # planned path bends over the person
    robot.path = [detour, beyond]
    # the wall mask alone would allow the shortcut; the survivor-aware mask must not
    assert line_clear(robot._trav(), (4.125, 4.125), beyond, robot.cell)
    assert not line_clear(robot._drive_trav(), (4.125, 4.125), beyond, robot.cell)
    robot._follow()
    assert robot.path == [detour, beyond], "the detour waypoint around the person was dropped"


def test_v2_shortcut_still_works_when_no_person_is_in_the_way(monkeypatch):
    robot = v2_robot(monkeypatch)
    robot.found = {"S1": {"pos": [4.9, 6.5]}}              # confirmed person well off the line
    robot.path = [(4.7, 4.8), (5.7, 4.125)]
    robot._follow()
    assert robot.path == [(5.7, 4.125)], "a clear shortcut should still advance the path"
