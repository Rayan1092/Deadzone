import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FREE, OCC  # noqa: E402
from deadzone.network.dtn import make_bundle  # noqa: E402
from deadzone.robot.robot import LINK_HOLD_S, TRAPPED_AFTER_S, Robot  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def small_robot(grid, entry=(2.0, 2.0)):
    h, w = grid.shape
    r = Robot("R1", "Scout 1", "#fff", (2.0, 2.0, 0.0), (h, w), 0.25, entry)
    r.map.grid = grid
    return r


def test_link_events_once_per_outage():
    sim = Sim(n_robots=1, seed=7)
    seq = []
    for _ in range(2600):
        sim.tick()
        seq += [e["kind"] for e in sim.drain_events() if e["kind"] in ("link_lost", "link_restored")]
    assert seq and seq[0] == "link_lost"
    assert all(a != b for a, b in zip(seq, seq[1:])), f"events must alternate: {seq}"


def test_hold_after_reconnect_waits_for_backlog_at_most_10_s():
    r = small_robot(np.full((20, 20), FREE, dtype=np.uint8))
    r.state, r.linked, r.reconnect_t = "RETURNING_TO_SIGNAL", True, 100.0
    r.outbox.append(make_bundle("R1", "CMD", "map_patch", {}, 95.0, 64))   # made in the dark
    r.t = 100.0 + LINK_HOLD_S - 0.5
    r._behave()
    assert r.state == "RETURNING_TO_SIGNAL"          # backlog still waiting
    r.t = 100.0 + LINK_HOLD_S
    r._behave()
    assert r.state == "EXPLORING"                    # 10 s cap
    r.state, r.outbox = "RETURNING_TO_SIGNAL", [make_bundle("R1", "CMD", "telemetry", {}, 101.0, 64)]
    r.t = 101.5
    r._behave()
    assert r.state == "EXPLORING"                    # only fresh bundles left, go back to work


def test_rubble_ahead_triggers_visible_replan_and_no_collision():
    """The R key drops rubble 1.5 m ahead of the robot: it must replan around it, not hit it."""
    sim = Sim(n_robots=1, seed=7)
    r, body = sim.robots["R1"], sim.bodies["R1"]
    while sim.time < 90:
        sim.tick()
    sim.drain_events()
    x, y, th = r.pose
    sim.drop_rubble((x + math.cos(th) * 1.5, y + math.sin(th) * 1.5))
    states, kinds, blocked = set(), [], 0
    for _ in range(200):
        sim.tick()
        states.add(r.state)
        kinds += [e["kind"] for e in sim.drain_events()]
        blocked += body["blocked"]
    assert "replan" in kinds and "REPLANNING" in states
    assert blocked == 0
    assert math.dist((x, y), r.pose[:2]) > 5.0, "robot should keep exploring after the replan"


def test_sealed_in_robot_raises_trapped_fault():
    grid = np.zeros((24, 24), dtype=np.uint8)  # unknown outside
    grid[3:13, 3:13] = FREE
    grid[2, 2:14] = grid[13, 2:14] = OCC      # a closed 3 m box around the robot
    grid[2:14, 2] = grid[2:14, 13] = OCC
    r = small_robot(grid, entry=(5.0, 5.0))   # home is outside the box
    r.state = "EXPLORING"
    r.t = 0.0
    r._start_replan("obstacle")
    t = 0.0
    while t < TRAPPED_AFTER_S + 3.0 and r.fault != "TRAPPED":
        t += 0.1
        r.t = t
        r._behave()
    assert r.state == "REPLANNING" and r.fault == "TRAPPED"
    assert any(b["kind"] == "fault" and b["prio"] == 1 for b in r.outbox)
    assert sum(e["kind"] == "fault" for e in r.events) == 1
