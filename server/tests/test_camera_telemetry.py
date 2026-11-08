"""Contract B: with DZ_CAMERA_TELEMETRY=1 the telemetry bundle carries `camera: {t, hits}` (what the
robot's thermal camera sees and what its onboard detector says), so Command and the phone learn it
when the bundle is delivered. Default off: telemetry unchanged."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot import perception  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


def building(tmp_path):
    data = {"id": "camera-telemetry-test", "name": "Camera telemetry", "size": [12, 8], "cell": 0.25,
            "materials": {"brick": 4, "rubble": 8, "concrete": 16},
            "walls": [{"a": a, "b": b, "material": "concrete"} for a, b in
                      [([0, 0], [12, 0]), ([12, 0], [12, 8]), ([12, 8], [0, 8]), ([0, 8], [0, 5]), ([0, 3], [0, 0])]],
            "doors": [{"at": [0, 4], "width": 2.0, "axis": "y", "state": "open"}],
            "rooms": [], "rubble": [], "hazards": [],
            "survivors": [{"id": "S1", "pos": [4.0, 4.0], "thermal": "pos_0001.png"}],
            "decoys": [{"id": "D1", "label": "radiator", "pos": [4.0, 5.0], "thermal": "neg_0001.png"}],
            "entry": [1.0, 4.0], "command_post": {"pos": [-2.0, 4.0], "tx_dbm": 30}}
    path = tmp_path / "b.json"
    path.write_text(json.dumps(data))
    return path


def telemetry_bundles(sim):
    return [b for b in sim.robots["R1"].outbox if b["kind"] == "telemetry"]


def test_camera_hits_ride_in_telemetry_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "1")
    perception.reset_detector()
    sim = Sim(plan_path=building(tmp_path), n_robots=1, seed=7)
    sim.tick()                                   # the robot sees S1 (and D1 with the model) from the entry
    r = sim.robots["R1"]
    assert r.camera_telemetry and r.camera_hits
    r.last_telemetry_t = -99.0
    r._emit_bundles()
    bundle = telemetry_bundles(sim)[-1]
    camera = bundle["payload"]["camera"]
    assert camera["t"] == round(sim.time, 1) and camera["hits"]
    by_id = {h["id"]: h for h in camera["hits"]}
    assert by_id["S1"]["verdict"] == "person" and by_id["S1"]["crop"] == "pos_0001.png"
    assert set(by_id["S1"]) == {"id", "pos", "verdict", "conf", "crop"}
    if perception.get_detector().mode == "model":
        assert by_id["D1"]["verdict"] == "rejected" and by_id["D1"]["conf"] < 0.6 and by_id["S1"]["conf"] >= 0.6
    else:
        assert by_id["S1"]["conf"] is None
    assert bundle["size"] == 120 + 40 * len(camera["hits"])
    # nothing in the Reality-only camera frame unless DZ_SENSOR_VIEW is also on
    assert r.camera_frame is None
    # the delivered bundle is what Command gets; no truth path: the hits came from io.thermal()
    for _ in range(15):
        sim.tick()
    assert sim.post.robots["R1"]["state"]        # delivered telemetry still parses


def test_default_telemetry_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("DZ_CAMERA_TELEMETRY", raising=False)
    perception.reset_detector()
    sim = Sim(plan_path=building(tmp_path), n_robots=1, seed=7)
    sim.tick()
    r = sim.robots["R1"]
    r.last_telemetry_t = -99.0
    r._emit_bundles()
    bundle = telemetry_bundles(sim)[-1]
    assert "camera" not in bundle["payload"] and bundle["size"] == 120
    assert r.camera_hits == [] and r.camera_frame is None


@pytest.mark.parametrize("flag", ["DZ_CAMERA_TELEMETRY", "DZ_SENSOR_VIEW"])
def test_unsure_hot_spots_are_labelled_unsure(tmp_path, monkeypatch, flag):
    if perception.get_detector().mode != "model" or not (perception.CROP_DIR / "unsure_person_01.png").is_file():
        pytest.skip("needs the trained detector and the unsure crops")
    monkeypatch.setenv(flag, "1")
    perception.reset_detector()
    data = json.loads(building(tmp_path).read_text())
    data["survivors"] = [{"id": "S1", "pos": [4.5, 4.0], "thermal": "unsure_person_01.png"}]
    data["decoys"] = []
    path = tmp_path / "u.json"
    path.write_text(json.dumps(data))
    sim = Sim(plan_path=path, n_robots=1, seed=7)
    sim.tick()
    r = sim.robots["R1"]
    hits = r.camera_hits if flag == "DZ_CAMERA_TELEMETRY" else r.camera_frame["hits"]
    assert [h["verdict"] for h in hits] == ["unsure"]
