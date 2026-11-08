"""User-confirmed heat-source schema, real sensor visibility and delivered-only metadata."""
import importlib
import json
import math
import random
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from deadzone.command.camera import delivered_frame
from deadzone.network.propagation import LinkGraph
from deadzone.robot import perception
from deadzone.sim import DT, Sim
from deadzone.thermal import HEAT_TYPES, thermal_metadata


@pytest.fixture
def data():
    return {"id": "heat-test", "name": "Heat test", "size": [12, 12], "cell": .25,
            "materials": {"brick": 4}, "walls": [
                {"a": [6, 0], "b": [6, 3.5], "material": "brick"},
                {"a": [6, 5.5], "b": [6, 12], "material": "brick"}],
            "doors": [], "rooms": [], "hazards": [], "rubble": [], "decoys": [],
            "survivors": [{"id": "S1", "pos": [5, 4], "thermal": "pos_0001.png"}],
            "heat_sources": [{"id": "H1", "type": "generator", "x": 5, "y": 4,
                              "temp_c": 65, "size_m": .8}],
            "entry": [4, 4], "command_post": {"pos": [3, 4], "tx_dbm": 30}}


@pytest.fixture
def model(monkeypatch):
    detector = SimpleNamespace(mode="model", threshold=.6,
        score=lambda crop: .01 if crop and crop.startswith("neg_") else .99,
        heatmap=lambda crop: None)
    monkeypatch.setattr(perception, "_detector", detector)
    return detector


def scene(data, tmp_path, monkeypatch, *, enabled=True, seed=7):
    monkeypatch.setenv("DZ_HEAT_SOURCES", "1" if enabled else "0")
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "0")
    path = tmp_path / "heat.json"
    path.write_text(json.dumps(data))
    sim = Sim(plan_path=path, n_robots=1, seed=seed)
    sim.bodies["R1"].update(x=4, y=4, th=0)
    sim.robots["R1"].pose = [4, 4, 0]
    return sim


@pytest.mark.parametrize("pos,visible", [((5, 4), True), ((3, 4), False), ((10, 4), False),
    ((4, 7), False), ((7, 2), False), ((9, 4), True), ((9.001, 4), False),
    ((5, 4 + math.sqrt(3) - .001), True), ((5, 4 + math.sqrt(3) + .001), False)])
def test_heat_and_survivor_share_actual_range_fov_and_wall_occlusion(data, tmp_path, monkeypatch, model, pos, visible):
    data["survivors"][0]["pos"] = list(pos)
    data["heat_sources"][0].update(x=pos[0], y=pos[1])
    sim = scene(data, tmp_path, monkeypatch)
    hits = {h["id"]: h for h in sim.ios["R1"].thermal()}
    assert set(hits) == ({"S1", "H1"} if visible else set())
    if visible:
        assert hits["S1"]["kind"] == "survivor"
        heat = hits["H1"]
        assert set(heat) == {"id", "pos", "crop", "conf", "kind", "type", "source_id", "temp_c"}
        assert (heat["kind"], heat["source_id"], heat["type"], heat["temp_c"]) == ("decoy", "H1", "generator", 65)


def test_all_types_are_deterministic_per_seed_order_reset_and_do_not_consume_rng(data, tmp_path, monkeypatch, model):
    data["heat_sources"] = [dict(data["heat_sources"][0], id=f"H{i}", type=kind)
                            for i, kind in enumerate(sorted(HEAT_TYPES))]
    sim = scene(data, tmp_path, monkeypatch)
    before = random.getstate()
    hits = sim.ios["R1"].thermal()
    assert random.getstate() == before
    assert len(hits) == 8 and {h["type"] for h in hits if h["kind"] == "decoy"} == HEAT_TYPES
    by_id = {h["id"]: h for h in hits}
    assert all(h["crop"] in {"neg_0001.png", "neg_0002.png", "neg_0003.png"}
               for h in hits if h["kind"] == "decoy")
    other = scene(data, tmp_path, monkeypatch)
    assert other.ios["R1"].thermal() == hits
    data["heat_sources"].reverse()
    reordered = scene(data, tmp_path, monkeypatch)
    assert {h["id"]: h for h in reordered.ios["R1"].thermal()} == by_id
    sim.reset()
    sim.bodies["R1"].update(x=4, y=4, th=0)
    assert {h["id"]: h for h in sim.ios["R1"].thermal()} == by_id
    assert not sim.post.robots


def test_typed_hits_take_real_model_path_and_reach_command_only_after_dtn(data, tmp_path, monkeypatch, model):
    sim = scene(data, tmp_path, monkeypatch)
    robot = sim.robots["R1"]
    robot._perceive(sim.ios["R1"])
    assert set(robot.found) == {"S1"}
    event = next(e for e in robot.events if e["kind"] == "hotspot_rejected")
    assert (event["hit_kind"], event["source_id"], event["type"], event["temp_c"], event["conf"]) == (
        "decoy", "H1", "generator", 65, .01)
    robot._emit_bundles()
    bundle = next(b for b in robot.outbox if b["kind"] == "telemetry")
    hits = bundle["payload"]["camera"]["hits"]
    heat = next(h for h in hits if h["id"] == "H1")
    assert heat["kind"] == "decoy" and heat["verdict"] == "rejected"
    assert heat["source_id"] == "H1" and heat["type"] == "generator" and heat["temp_c"] == 65
    assert bundle["size"] > 120 + 40 * len(hits)
    sim.links = LinkGraph()
    sim._move_bundles(DT)
    assert not sim.post.robots and not sim.post.survivors
    sim._update_links()
    sim._move_bundles(DT)
    frame = sim.post.view(sim.time)["robots"][0]["camera"]
    assert frame["hits"] == hits and frame["last_seen_s"] == 0
    sim.time = 5
    assert sim.post.view(sim.time)["robots"][0]["camera"]["last_seen_s"] == 5
    assert "heat_sources" not in sim.prior.planning_data()  # phone hello gets no unseen truth list
    assert set(sim.post.survivors) <= {"S1"}


@pytest.mark.parametrize("score,expected", [(None, "unsure"), (.01, "rejected"), (.95, "person")])
def test_truth_kind_never_overrides_model_verdict_or_invents_fallback_survivors(data, tmp_path, monkeypatch, model, score, expected):
    data["survivors"] = []
    monkeypatch.setattr(model, "score", lambda crop: score)
    if score is None:
        monkeypatch.setattr(model, "mode", "sim")
    sim = scene(data, tmp_path, monkeypatch)
    robot = sim.robots["R1"]
    robot._perceive(sim.ios["R1"])
    assert robot.camera_hits[0]["kind"] == "decoy"
    assert robot.camera_hits[0]["verdict"] == expected and robot.camera_hits[0]["conf"] == score
    assert bool(robot.found) == (expected == "person")
    if expected == "person":
        assert robot.found["H1"]["kind"] == "decoy"  # model false positives remain honest
        assert any(e["kind"] == "survivor_found" and e["hit_kind"] == "decoy" for e in robot.events)
    if score is None:
        assert not robot.rejected and not robot.events


def test_default_off_ignores_sources_even_invalid_and_preserves_old_shapes(data, tmp_path, monkeypatch, model):
    data["heat_sources"] = [{"bad": "ignored with flag off"}]
    sim = scene(data, tmp_path, monkeypatch, enabled=False)
    hit, = sim.ios["R1"].thermal()
    assert set(hit) == {"id", "pos", "crop", "conf"}
    robot = sim.robots["R1"]
    robot._perceive(sim.ios["R1"])
    robot._emit_bundles()
    assert not robot.camera_telemetry and not sim.post.camera_telemetry
    assert "kind" not in robot.found["S1"]
    assert all("camera" not in b["payload"] for b in robot.outbox if b["kind"] == "telemetry")


def test_old_camera_hits_default_to_survivor_only_when_enabled():
    raw = {"t": 1, "hits": [{"id": "S1", "pos": [3, 4], "crop": None, "conf": None, "verdict": "person"}]}
    assert delivered_frame(raw, 1, 2, (12, 12), heat_sources=True)["hits"][0]["kind"] == "survivor"
    assert set(delivered_frame(raw, 1, 2, (12, 12))["hits"][0]) == {"id", "pos", "crop", "conf", "verdict"}
    invalid = dict(raw["hits"][0], kind="decoy", source_id="bad/id", type="wrong", temp_c=float("nan"))
    assert thermal_metadata(invalid) == {"kind": "decoy"}


def test_trained_model_classifies_all_heat_exemplars(data, tmp_path, monkeypatch):
    detector = perception.make_detector(env={})
    if detector.mode != "model":
        pytest.skip("trained detector unavailable")
    monkeypatch.setattr(perception, "_detector", detector)
    data["heat_sources"] = [dict(data["heat_sources"][0], id=f"H{i}", type=kind)
                            for i, kind in enumerate(sorted(HEAT_TYPES))]
    sim = scene(data, tmp_path, monkeypatch)
    robot = sim.robots["R1"]
    robot._perceive(sim.ios["R1"])
    assert set(robot.found) == {"S1"}
    heats = [h for h in robot.camera_hits if h["kind"] == "decoy"]
    assert len(heats) == 7
    assert all(h["verdict"] == "rejected" and h["conf"] == detector.score(h["crop"])
               and h["conf"] < detector.threshold for h in heats)


def test_phone_websocket_gets_only_delivered_typed_observations(data, tmp_path, monkeypatch, model):
    api = importlib.import_module("deadzone.app")
    path = tmp_path / "heat-phone.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr("deadzone.scenarios.registered_floorplans", lambda: {"heat-test": path})
    for key, value in {"DZ_HEAT_SOURCES": "1", "DZ_PHONE_FRAMES": "0", "DZ_CAMERA_TELEMETRY": "0",
                       "DZ_FLOORPLAN": "heat-test", "DZ_ROBOTS": "1", "DZ_AUTOSTART": "0"}.items():
        monkeypatch.setenv(key, value)
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    with TestClient(api.app) as client, client.websocket_connect("/ws/phone?role=spectator") as ws:
        hello, view = ws.receive_json(), ws.receive_json()
        assert "heat_sources" not in hello["data"]["floorplan"]
        assert view["t"] == "cmd_view" and "reality" not in view["data"]
        hits = view["data"]["robots"][0]["camera"]["hits"]
        heat = next(h for h in hits if h["id"] == "H1")
        assert heat["kind"] == "decoy" and heat["type"] == "generator"
        assert heat["source_id"] == "H1" and heat["temp_c"] == 65 and heat["verdict"] == "rejected"


@pytest.mark.parametrize("change", [{"type": "radiator"}, {"size_m": 0}, {"temp_c": float("nan")},
    {"x": 99}, {"id": "S1"}, {"x": "5"}])
def test_enabled_sources_validate_the_exact_schema(data, tmp_path, monkeypatch, model, change):
    data["heat_sources"][0].update(change)
    with pytest.raises(ValueError):
        scene(data, tmp_path, monkeypatch)
