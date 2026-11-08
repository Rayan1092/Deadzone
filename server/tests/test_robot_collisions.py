"""Hard robot-body contacts, isolated from robot yielding/autonomy policy."""
import json
import math
import random

import pytest

from deadzone.sim import ROBOT_RADIUS_M, Sim


@pytest.fixture
def sim(tmp_path, monkeypatch):
    monkeypatch.setenv("DZ_ROBOT_COLLISIONS", "1")
    monkeypatch.setenv("DETECTOR", "sim")
    data = {"id": "contacts", "name": "Contact test", "size": [20, 10], "cell": .25,
            "materials": {"concrete": 12}, "walls": [], "hazards": [], "survivors": [],
            "entry": [1, 5], "command_post": {"pos": [0, 5]}}
    path = tmp_path / "contacts.json"
    path.write_text(json.dumps(data))
    return Sim(plan_path=path, n_robots=3)


def place(sim, rid, x, y, v=0, th=0, w=0):
    sim.bodies[rid].update(x=x, y=y, th=th, cmd_v=v, cmd_w=w)


def positions(sim):
    return {rid: (body["x"], body["y"]) for rid, body in sim.bodies.items()}


def separated(sim):
    points = list(positions(sim).values())
    for i, a in enumerate(points):
        for b in points[i + 1:]:
            assert math.dist(a, b) >= 2 * ROBOT_RADIUS_M - 1e-8


def test_head_on_moves_stop_and_report_contact_on_both_robots(sim):
    place(sim, "R1", 2, 5, 2)
    place(sim, "R2", 4, 5, 2, math.pi)
    place(sim, "R3", 15, 8)
    before = positions(sim)
    sim._integrate_bodies(1)
    assert positions(sim) == before
    separated(sim)
    for rid, other in (("R1", "R2"), ("R2", "R1")):
        odo = sim.ios[rid].odometry()
        assert odo["blocked"] and odo["v"] == 0
        assert odo["blocked_by"] == [other]
    assert not sim.ios["R3"].odometry()["blocked"]


@pytest.mark.parametrize("reverse", [False, True])
def test_swept_contacts_prevent_high_speed_swapping_even_in_reverse(sim, reverse):
    place(sim, "R1", 2, 5, -8 if reverse else 8, math.pi if reverse else 0)
    place(sim, "R2", 8, 5, 8, math.pi)
    place(sim, "R3", 15, 8)
    before = positions(sim)
    sim._integrate_bodies(1)
    assert positions(sim) == before
    assert sim.bodies["R1"]["blocked"] and sim.bodies["R2"]["blocked"]
    separated(sim)


def test_crossing_paths_block_only_when_robots_arrive_together(sim):
    place(sim, "R1", 2, 5, 6)
    place(sim, "R2", 5, 2, 6, math.pi / 2)
    place(sim, "R3", 15, 8)
    before = positions(sim)
    sim._integrate_bodies(1)
    assert positions(sim) == before
    place(sim, "R2", 5, 1, 4, math.pi / 2)
    sim._integrate_bodies(1)
    assert sim.bodies["R1"]["x"] == 8
    assert sim.bodies["R2"]["y"] == 5
    separated(sim)


def test_stopping_a_leader_also_blocks_a_following_robot(sim):
    place(sim, "R1", 2, 5, 1)
    place(sim, "R2", 2.8, 5, 1)
    place(sim, "R3", 3.6, 5)
    before = positions(sim)
    sim._integrate_bodies(1)
    assert positions(sim) == before
    assert sim.ios["R1"].odometry()["blocked_by"] == ["R2"]
    assert sim.ios["R2"].odometry()["blocked_by"] == ["R3"]
    assert not sim.ios["R3"].odometry()["blocked"]
    separated(sim)


def test_rotation_and_separating_motion_clear_previous_contact(sim):
    place(sim, "R1", 2, 5, 1)
    place(sim, "R2", 2.7, 5)
    place(sim, "R3", 15, 8)
    sim._integrate_bodies(1)
    assert sim.bodies["R1"]["blocked"]
    place(sim, "R1", 2, 5, 0, w=1)
    sim._integrate_bodies(1)
    assert sim.bodies["R1"]["th"] == 1
    assert not sim.bodies["R1"]["blocked"]
    assert sim.ios["R1"].odometry()["blocked_by"] == []
    place(sim, "R1", 2, 5, -.5)
    sim._integrate_bodies(1)
    assert sim.bodies["R1"]["x"] == 1.5


def test_contact_outcome_does_not_depend_on_body_dictionary_order(sim):
    place(sim, "R1", 2, 5, 1)
    place(sim, "R2", 2.8, 5, 1)
    place(sim, "R3", 3.6, 5)
    sim.bodies = dict(reversed(list(sim.bodies.items())))
    sim._integrate_bodies(1)
    assert sim.bodies["R1"]["blocked"] and sim.bodies["R2"]["blocked"]
    separated(sim)


def test_flag_off_keeps_legacy_motion_and_payloads(sim, monkeypatch):
    monkeypatch.setenv("DZ_ROBOT_COLLISIONS", "0")
    sim.reset()
    place(sim, "R1", 2, 5, 2)
    place(sim, "R2", 4, 5, 2, math.pi)
    place(sim, "R3", 15, 8)
    sim._integrate_bodies(1)
    assert sim.bodies["R1"]["x"] == 4 and sim.bodies["R2"]["x"] == 2
    assert "blocked_by" not in sim.ios["R1"].odometry()
    assert "body_radius_m" not in sim.snapshot()["reality"]["robots"][0]


def test_contact_diagnostics_stay_in_reality_not_command(sim):
    place(sim, "R1", 2, 5, 2)
    place(sim, "R2", 4, 5, 2, math.pi)
    place(sim, "R3", 15, 8)
    sim._integrate_bodies(1)
    snapshot = sim.snapshot()
    assert snapshot["reality"]["robots"][0]["blocked_by"] == ["R2"]
    assert "blocked_by" not in json.dumps(snapshot["command"])


def test_contact_event_is_once_per_encounter_and_never_a_radio_bundle(sim):
    sim.drain_events()  # startup link-up events are unrelated to contacts
    place(sim, "R1", 2, 5, 1)
    place(sim, "R2", 2.7, 5)
    place(sim, "R3", 15, 8)
    sim._integrate_bodies(1)
    expected = {"kind": "robot_contact", "a": "R1", "b": "R2", "pos": [2.35, 5]}
    assert sim.events == [expected]
    sim._integrate_bodies(1)
    assert sim.events == [expected]
    sim.bodies["R1"]["cmd_v"] = 0
    sim._integrate_bodies(1)
    sim.bodies["R1"]["cmd_v"] = 1
    sim._integrate_bodies(1)
    assert sim.events == [expected, expected]
    assert not any(sim.network.queues.values())


def test_tick_exposes_real_blockage_to_robot_policy_on_next_step(sim, monkeypatch):
    place(sim, "R1", 2, 5)
    place(sim, "R2", 2.7, 5, th=math.pi)
    place(sim, "R3", 15, 8)
    observed = {rid: [] for rid in sim.robots}
    def policy(rid):
        def step(dt, io):
            observed[rid].append(io.odometry()["blocked"])
            io.drive(1 if rid != "R3" and len(observed[rid]) == 1 else 0, 0)
        return step
    for rid, robot in sim.robots.items():
        monkeypatch.setattr(robot, "step", policy(rid))
    sim.tick()
    separated(sim)
    sim.tick()
    assert observed["R1"] == observed["R2"] == [False, True]
    assert observed["R3"] == [False, False]


def test_many_seeded_motion_commands_never_overlap(sim):
    rng = random.Random(41)
    for rid, x in (("R1", 4), ("R2", 4.8), ("R3", 5.6)):
        place(sim, rid, x, 5)
    for _ in range(300):
        for body in sim.bodies.values():
            body.update(cmd_v=rng.uniform(-6, 6), cmd_w=rng.uniform(-3, 3))
        sim._integrate_bodies(.5)
        separated(sim)
