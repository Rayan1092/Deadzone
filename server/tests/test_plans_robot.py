"""Robots follow dispatched plans (zones, no-go, lost-link budget) delivered as bundles."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FREE  # noqa: E402
from deadzone.network.dtn import make_bundle  # noqa: E402
from deadzone.robot.robot import Robot  # noqa: E402
from deadzone.sim import Sim  # noqa: E402

OFFICE_B = [[10, 17], [20, 17], [20, 30], [10, 30]]
STORAGE = [[0.2, 0.2], [11.8, 0.2], [11.8, 12.8], [0.2, 12.8]]


def plan(rid="R1", zones=None, no_go=None, budget=30.0, pid="P-1"):
    return {"plan_id": pid, "author": "test", "lost_link_budget_s": budget,
            "zones": zones if zones is not None else [{"id": "Z1", "robot": rid, "priority": 1,
                                                       "poly": OFFICE_B, "comms": "relay"}],
            "no_go": no_go or []}


def test_apply_plan_sets_zone_no_go_and_budget():
    r = Robot("R1", "Scout 1", "#fff", (2.0, 2.0, 0.0), (120, 160), 0.25, (1.0, 15.0))
    other = {"id": "Z9", "robot": "R2", "priority": 1, "poly": STORAGE, "comms": "relay"}
    r._apply_plan(plan(zones=[{"id": "Z1", "robot": "R1", "priority": 1, "poly": OFFICE_B, "comms": "relay"}, other],
                       no_go=[{"id": "NG1", "reason": "t", "poly": STORAGE}]))
    assert [z["id"] for z in r.zones] == ["Z1"]                 # only our own zones
    assert r.nogo[r._cell(5, 5)[1], r._cell(5, 5)[0]]          # plan no-go is never planned through
    assert r.lost_budget == 30.0
    assert r.events[-1] == {"kind": "plan_applied", "robot": "R1", "plan_id": "P-1", "zones": ["Z1"]}
    r._apply_plan(plan(pid="P-2"))                               # a newer plan replaces the no-go
    assert not r.nogo[r._cell(5, 5)[1], r._cell(5, 5)[0]]


def test_dispatched_plan_sends_robot_to_its_zone_and_keeps_it_out_of_no_go():
    sim = Sim(n_robots=1, seed=7)
    r = sim.robots["R1"]
    sim.network.queues["CMD"].append(
        make_bundle("CMD", "R1", "plan", plan(no_go=[{"id": "NG1", "reason": "t", "poly": STORAGE}]), sim.time, 400))
    applied, entered = None, None
    for _ in range(400):
        sim.tick()
        if any(e["kind"] == "plan_applied" for e in sim.drain_events()):
            applied = sim.time
        x, y = r.pose[:2]
        if applied and entered is None and 10 <= x <= 20 and 17 <= y <= 30:
            entered = sim.time
        if applied:
            assert not (0.2 <= x <= 11.8 and 0.2 <= y <= 12.8), "robot entered the plan's no-go area"
    assert applied is not None and applied < 1.0                # arrives through the network
    assert entered is not None and entered < 40.0               # without a plan: about 97 s
    assert sim.snapshot()["reality"]["robots"][0]["plan_id"] == "P-1"


class FakeRadio:
    def neighbors(self):
        return [("CMD", -78.0)]                                 # inside the drop window

    def receive(self):
        return []


class FakeIO:
    def __init__(self):
        self.radio = FakeRadio()
        self.drops = 0

    def drop_relay(self):
        self.drops += 1


def test_no_relay_drops_inside_a_lost_link_ok_zone():
    r = Robot("R1", "Scout 1", "#fff", (15.0, 20.0, 0.0), (120, 160), 0.25, (1.0, 15.0))
    r.map.grid = np.full((120, 160), FREE, dtype=np.uint8)
    r.state, r.linked = "EXPLORING", True
    r._apply_plan(plan(zones=[{"id": "Z1", "robot": "R1", "priority": 1, "poly": OFFICE_B,
                               "comms": "lost_link_ok"}]))
    io = FakeIO()
    r._maybe_drop_relay(io)
    assert io.drops == 0
    r._apply_plan(plan(pid="P-2"))                              # same zone, comms: relay
    r._maybe_drop_relay(io)
    assert io.drops == 1
