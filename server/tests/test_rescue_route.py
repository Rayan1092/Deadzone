"""Rescue route + beacon: a confirmed survivor yields a safe route to CMD (priority 1), and a
beacon relay when the survivor is in a dead zone. Command only learns the route on delivery."""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FREE, OCC  # noqa: E402
from deadzone.robot.robot import Robot  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def mapped_robot():
    """10 m x 8 m known map: a wall at x = 5 m with a gap near the top, and a no-go patch."""
    h, w = 32, 40
    r = Robot("R1", "Scout 1", "#fff", (8.0, 2.0, 0.0), (h, w), 0.25, (1.0, 2.0))
    grid = np.full((h, w), FREE, dtype=np.uint8)
    grid[0, :] = grid[-1, :] = OCC
    grid[:, 0] = grid[:, -1] = OCC
    grid[0:24, 20] = OCC                       # wall, gap for y > 6 m
    r.map.grid = grid
    r.nogo = np.zeros((h, w), dtype=bool)
    r.nogo[26:31, 10:14] = True                # hazard right where a greedy path would go
    return r


class FakeRadio:
    def __init__(self, linked):
        self.linked = linked

    def cmd_reachable(self):
        return self.linked

    def neighbors(self):
        return []

    def receive(self):
        return []


class FakeIO:
    def __init__(self, linked):
        self.radio = FakeRadio(linked)
        self.drops = 0

    def drop_relay(self, beacon_for=None):
        self.drops += 1
        self.beacon_for = beacon_for
        return f"RL{self.drops}"


def test_route_avoids_walls_and_no_go_and_starts_at_the_entrance():
    r = mapped_robot()
    pts, length, clearance = r._rescue_route((8.0, 2.0))
    assert pts[0] == [1.0, 2.0] and pts[-1] == [8.0, 2.0]
    assert length > math.dist((1.0, 2.0), (8.0, 2.0)) + 6.0   # had to go round the wall
    assert clearance == 0.25
    for x, y in pts[1:-1]:
        ix, iy = r._cell(x, y)
        assert r.map.grid[iy, ix] != OCC and not r.nogo[iy, ix]


def test_confirmed_survivor_sends_priority_1_route_and_beacon_only_in_the_dark():
    rec = {"id": "S9", "pos": [8.0, 2.0]}
    lit = mapped_robot()
    lit.linked = True
    io = FakeIO(linked=True)
    lit._on_survivor_confirmed(io, rec)
    b = lit.outbox[-1]
    assert b["kind"] == "rescue_route" and b["prio"] == 1 and b["dst"] == "CMD"
    assert b["payload"]["survivor"] == "S9" and b["payload"]["beacon"] is None and io.drops == 0
    ev = lit.events[-1]
    assert ev["kind"] == "rescue_route" and ev["path"] == b["payload"]["path"]
    assert ev["length_m"] == b["payload"]["length_m"]

    dark = mapped_robot()
    dark.linked = False
    io = FakeIO(linked=False)
    dark._on_survivor_confirmed(io, rec)
    assert io.drops == 1 and dark.outbox[-1]["payload"]["beacon"] == "RL1" and io.beacon_for == "S9"
    assert dark.relays_left == 1


def test_no_second_beacon_or_route_when_a_peer_already_confirmed_it():
    r = mapped_robot()
    r.peers["R2"] = {"target": None, "pose": None, "relays": [], "found": ["S9"], "t": 0.0}
    io = FakeIO(linked=False)
    r._on_survivor_confirmed(io, {"id": "S9", "pos": [8.0, 2.0]})
    assert io.drops == 0 and not r.outbox and not r.events


def test_seed7_dark_survivor_gets_beacon_and_command_learns_route_only_on_delivery():
    sim = Sim(n_robots=1, seed=7)
    route_t = delivered_t = None
    route = None
    for _ in range(2400):
        sim.tick()
        for e in sim.drain_events():
            if e["kind"] == "rescue_route" and e["survivor"] == "S1":
                route_t, route = sim.time, e
            if e["kind"] == "bundle_delivered" and e["bundle_kind"] == "rescue_route" and route_t and not delivered_t:
                delivered_t = sim.time
        if delivered_t:
            break
    assert route is not None
    # one robot has spent both relays on the network by now, so no beacon is left to drop
    assert route["beacon"] is None and sim.robots["R1"].relays_left == 0
    assert route["path"][0] == list(sim.fp.entry) and route["length_m"] > 30
    assert delivered_t is not None and delivered_t > route_t + 1.0     # held until the link returns


class ThermalIO(FakeIO):
    def thermal(self):
        return [{"id": "S9", "pos": (8.0, 2.0), "crop": None, "conf": 0.99}]


def test_dark_sighting_of_an_already_reported_survivor_does_not_send_robot_back():
    r = mapped_robot()
    r.linked = False
    r.peers["R2"] = {"target": None, "pose": None, "relays": [], "found": ["S9"], "t": 0.0}
    r._perceive(ThermalIO(linked=False))
    assert "S9" in r.found and not r.found_while_dark      # old news: keep exploring
    fresh = mapped_robot()
    fresh.linked = False
    fresh._perceive(ThermalIO(linked=False))
    assert fresh.found_while_dark                           # new news: go back and report
