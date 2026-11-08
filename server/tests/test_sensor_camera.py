"""The screen camera must show IO observations, never inferred detections."""

import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot import perception
from deadzone.sensors import THERMAL_FOV, THERMAL_RANGE
from deadzone.sim import Sim


@pytest.fixture
def scene(monkeypatch, tmp_path):
    monkeypatch.setenv("DZ_SENSOR_VIEW", "1")
    monkeypatch.setenv("DZ_EXPLORATION_V2", "0")
    data = {
        "id": "camera-test",
        "name": "Camera test",
        "size": [12, 12],
        "cell": 0.25,
        "entry": [4, 4],
        "command_post": {"pos": [-2, 4], "tx_dbm": 30},
        "materials": {"brick": 4, "rubble": 8, "concrete": 16},
        "walls": [
            {"a": a, "b": b, "material": "brick"}
            for a, b in [
                ([0, 0], [12, 0]),
                ([12, 0], [12, 12]),
                ([12, 12], [0, 12]),
                ([0, 12], [0, 0]),
                ([6, 0], [6, 3.5]),
                ([6, 5.5], [6, 12]),
            ]
        ],
        "rooms": [],
        "hazards": [],
        "rubble": [],
        "survivors": [
            {"id": sid, "pos": pos, "thermal": "pos_0001.png"}
            for sid, pos in [
                ("front", [5.5, 4]),
                ("behind", [3, 4]),
                ("far", [10, 4]),
                ("outside-cone", [4, 7]),
                ("behind-wall", [7, 2]),
                (
                    "near-edge",
                    [
                        4 + 2 * math.cos(math.radians(59)),
                        4 + 2 * math.sin(math.radians(59)),
                    ],
                ),
            ]
        ],
        "decoys": [{"id": "radiator", "pos": [5, 3], "thermal": "neg_0001.png"}],
    }
    path = tmp_path / "camera.json"
    path.write_text(json.dumps(data))
    sim = Sim(plan_path=path, n_robots=1, seed=7)
    sim.bodies["R1"].update(x=4.0, y=4.0, th=0.0)
    sim.tick()
    return sim


def test_actual_fov_range_and_occlusion_determine_camera_hits(scene):
    frame = scene.snapshot()["reality"]["robots"][0]["camera"]
    expected = {"front", "near-edge"}
    if perception.get_detector().mode == "model":
        expected.add("radiator")
    assert {h["id"] for h in frame["hits"]} == expected
    assert frame["pose"] == scene.robots["R1"].pose
    assert frame["t"] == scene.time
    assert scene.hello()["sensor_view"]["fov_rad"] == THERMAL_FOV
    assert scene.hello()["sensor_view"]["range_m"] == THERMAL_RANGE


def test_camera_scores_are_the_actual_onboard_model_results(scene):
    if perception.get_detector().mode != "model":
        pytest.skip("trained detector unavailable; sensor fallback has separate coverage")
    hits = {h["id"]: h for h in scene.robots["R1"].camera_frame["hits"]}
    assert hits["front"]["verdict"] == "person"
    assert hits["radiator"]["verdict"] == "rejected"
    for hit in hits.values():
        assert hit["source"] == "model"
        assert hit["conf"] == perception.get_detector().score(hit["crop"])
    assert hits["front"]["conf"] == scene.robots["R1"].found["front"]["conf"]


def test_leaving_the_view_clears_boxes_instead_of_reusing_detection_history(scene):
    assert scene.robots["R1"].camera_frame["hits"]
    scene.fp.data["survivors"] = []
    scene.fp.data["decoys"] = []
    scene.tick()
    assert not scene.robots["R1"].camera_frame["hits"]
    assert scene.robots["R1"].found  # old discoveries remain; live boxes must not


def test_camera_cannot_leak_into_command_or_robot_radio_payloads(scene):
    snapshot = scene.snapshot()
    assert "camera" not in json.dumps(snapshot["command"])
    assert "camera" not in scene.robots["R1"].telemetry({})
    for queue in scene.network.queues.values():
        assert "camera" not in json.dumps(queue)
    from deadzone.app import Hub

    hub = Hub()
    hub.sim = scene
    hub._init_plans()
    hello = hub.phone_hello("phone", "planner")
    assert "sensor_view" not in hello
    assert '"camera":' not in json.dumps(hello)


def test_published_frame_cannot_mutate_onboard_observations(scene):
    snapshot = scene.snapshot()
    snapshot["reality"]["robots"][0]["camera"]["hits"].clear()
    assert scene.robots["R1"].camera_frame["hits"]


def test_reset_drops_previous_camera_observations(scene):
    scene.reset()
    assert scene.robots["R1"].camera_frame is None
    assert "camera" not in scene.snapshot()["reality"]["robots"][0]
    scene.tick()
    assert scene.robots["R1"].camera_frame["t"] == 0.1


def test_flag_off_preserves_default_wire_contract(monkeypatch):
    monkeypatch.setenv("DZ_SENSOR_VIEW", "0")
    sim = Sim(n_robots=1, seed=7)
    sim.tick()
    assert "sensor_view" not in sim.hello()
    assert "camera" not in sim.snapshot()["reality"]["robots"][0]
    assert sim.robots["R1"].camera_frame is None


def test_sensor_fallback_does_not_invent_model_confidence(scene, monkeypatch):
    monkeypatch.setattr(
        perception, "_detector", perception.Passthrough("test fallback")
    )
    scene.tick()
    hits = scene.robots["R1"].camera_frame["hits"]
    assert "radiator" not in {h["id"] for h in hits}  # existing fallback policy
    assert all(h["source"] == "sim" and h["conf"] is None for h in hits)


def test_missing_crop_is_explicit_sensor_fallback(scene):
    scene.fp.data["survivors"][0]["thermal"] = "missing-camera-crop.png"
    scene.tick()
    hit = next(h for h in scene.robots["R1"].camera_frame["hits"] if h["id"] == "front")
    assert hit["source"] == "sim" and hit["conf"] is None


def test_camera_follows_sampled_yaw_not_previous_detection_position(scene):
    scene.bodies["R1"]["th"] = math.pi
    scene.tick()
    frame = scene.robots["R1"].camera_frame
    assert frame["pose"][2] == math.pi
    assert {h["id"] for h in frame["hits"]} == {"behind"}


def test_paused_rubble_fall_invalidates_old_observations_until_next_io_sample(scene):
    assert scene.robots["R1"].camera_frame is not None
    scene.drop_rubble([4.75, 4], size=0.5)
    assert scene.robots["R1"].camera_frame is None
    assert "camera" not in scene.snapshot()["reality"]["robots"][0]
    scene.tick()
    frame = scene.robots["R1"].camera_frame
    assert frame is not None
    assert "front" not in {h["id"] for h in frame["hits"]}


def test_aftershock_cannot_leave_a_stale_camera_frame_on_the_screen(scene):
    assert scene.robots["R1"].camera_frame is not None
    scene.aftershock([8, 8])
    assert scene.robots["R1"].camera_frame is None
    scene.tick()
    assert scene.robots["R1"].camera_frame["t"] == scene.time
