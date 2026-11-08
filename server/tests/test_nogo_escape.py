"""rayan-ml's phone diagnosis, bug 1.3: a robot standing inside a no-go area that a new plan draws
over it used to sit in REPLANNING for ever (its own cell blocked, so A* had no start). Now it walks
out to the nearest cell plans may start from, then carries on."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.geometry import points_in_poly  # noqa: E402
from deadzone.robot import perception  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def test_robot_walks_out_of_a_no_go_drawn_over_it_and_resumes():
    perception.reset_detector()
    sim = Sim(n_robots=1, seed=7)
    r = sim.robots["R1"]
    while sim.time < 20:                       # R1 is well inside the building by now
        sim.tick()
        sim.drain_events()
    x, y = r.pose[:2]
    poly = [[x - 2.5, y - 2.5], [x + 2.5, y - 2.5], [x + 2.5, y + 2.5], [x - 2.5, y + 2.5]]
    cx, cy = sim.fp.cell_centers()
    mask = points_in_poly(cx, cy, poly)
    r.nogo = r.nogo | mask                     # what _apply_plan does with a plan no-go over us
    r.path = []
    assert r.nogo[r._cell(x, y)[1], r._cell(x, y)[0]]
    def deep_inside(px, py, margin=0.3):            # more than a cell inside, not grazing the edge
        return x - 2.5 + margin < px < x + 2.5 - margin and y - 2.5 + margin < py < y + 2.5 - margin

    log, inside_until, states = [], None, []
    while sim.time < 60:
        sim.tick()
        log += sim.drain_events()
        states.append((round(sim.time, 1), r.state))
        if deep_inside(*r.pose[:2]):
            inside_until = sim.time
    assert inside_until is not None and inside_until < 30, (inside_until, states[-5:])
    assert r.fault != "TRAPPED" and not any(e["kind"] == "fault" and e.get("fault") == "TRAPPED" for e in log)
    assert any(e["kind"] == "replan" and e.get("reason") == "walk_out" for e in log)
    assert not r.escaping and not deep_inside(*r.pose[:2])
    # it went back to exploring, not home: the no-go was not "nothing left to explore"
    assert any(s in ("EXPLORING", "LOST_LINK_EXPLORING") for t, s in states if t > inside_until)
    assert "RETURNING_HOME" not in {s for t, s in states if t < 30}


def test_escape_is_a_no_op_when_plans_can_start_here():
    perception.reset_detector()
    sim = Sim(n_robots=1, seed=7)
    for _ in range(50):
        sim.tick()
    r = sim.robots["R1"]
    path = list(r.path)
    assert not r._escape_blocked_cell() and r.path == path and not r.escaping
    assert not np.any(r.nogo[r._cell(*r.pose[:2])[1], r._cell(*r.pose[:2])[0]])
