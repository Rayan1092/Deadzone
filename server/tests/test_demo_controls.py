"""Director controls, real thermal inputs, and delayed plan status for phones."""
import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.network.dtn import make_bundle  # noqa: E402
from deadzone.network.propagation import LinkGraph  # noqa: E402
from deadzone.robot import perception  # noqa: E402
from deadzone.sim import DT, Sim  # noqa: E402

api = importlib.import_module("deadzone.app")


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_ROBOTS", "3")
    monkeypatch.setattr(api, "hub", api.Hub())
    with TestClient(api.app) as client:
        yield client, api.hub


def director(client, action, robot="R1", **extra):
    return client.post("/api/control", json={"action": "director",
        "value": {"do": action, "robot": robot, **extra}})


def test_director_overload_causes_real_misses_but_not_safety_and_expires(session):
    client, hub = session
    assert director(client, "overload").status_code == 200
    sim = hub.sim
    assert sim.robots["R1"].overload_until == pytest.approx(sim.time + 3)
    events, slices = [], []
    for _ in range(40):
        sim.tick()
        events.extend(sim.drain_events())
        slices.extend(sim.robots["R1"].tasks)
    misses = [e for e in events if e["kind"] == "deadline_miss"]
    assert any(e["robot"] == "R1" and e["task"] == "perception" for e in misses)
    assert not any(e["task"] == "safety" for e in misses)
    assert not any(x["name"] == "safety" and x["missed"] for x in slices)
    assert sim.robots["R1"].overload_until is None
    assert sim.robots["R2"].overload_until is None


def test_resume_control_waits_for_network_and_robot_consumption(session):
    client, hub = session
    sim, robot = hub.sim, hub.sim.robots["R1"]
    robot.fault, robot.state = "SAFE_STOP", "FAULT"
    robot.fault_times, robot.fault_resume = [sim.time] * 3, "EXPLORING"
    assert director(client, "resume").status_code == 200
    commands = [b for b in sim.network.queues["CMD"] if b["kind"] == "command"]
    assert len(commands) == 1 and commands[0]["payload"] == {"cmd": "resume"}
    assert commands[0]["src"] == "CMD" and commands[0]["dst"] == "R1"
    sim.links = LinkGraph()  # no path: accepted control cannot clear SAFE_STOP
    sim._move_bundles(DT)
    assert commands[0] in sim.network.queues["CMD"] and robot.fault == "SAFE_STOP"
    sim._update_links()
    sim._move_bundles(DT)
    assert commands[0]["bid"] in {b["bid"] for b in sim.inboxes["R1"]}
    assert robot.fault == "SAFE_STOP"
    sim.tick()
    assert robot.fault is None and robot.fault_times == []
    assert any(e["kind"] == "resumed" and e["robot"] == "R1" for e in sim.drain_events())


@pytest.mark.parametrize("action", ["overload", "resume"])
def test_director_controls_validate_robot_and_schema_and_reset(session, action):
    client, hub = session
    assert director(client, action, robot="missing").status_code == 404
    assert director(client, action, unexpected=True).status_code == 422
    assert director(client, action, robot=1).status_code == 422
    assert director(client, action).status_code == 200
    client.post("/api/control", json={"action": "reset"})
    assert hub.sim.robots["R1"].overload_until is None
    assert not any(b["kind"] == "command" for b in hub.sim.network.queues["CMD"])


def test_director_websocket_recovers_from_invalid_control(session):
    client, hub = session
    with client.websocket_connect("/ws/screen") as ws:
        for _ in range(4):
            ws.receive_json()
        ws.send_json({"t": "control", "data": {"action": "director",
                     "value": {"do": "resume", "robot": "missing"}}})
        assert ws.receive_json()["data"]["code"] == "robot_not_found"
        ws.send_json({"t": "control", "data": {"action": "director",
                     "value": {"do": "overload", "robot": "R1"}}})
        assert ws.receive_json()["t"] == "control"
        assert hub.sim.robots["R1"].overload_until is not None


@pytest.mark.parametrize("pos,visible", [
    ((3, 15), True), ((1, 15), False), ((8, 15), False),
    ((3, 17), False), ((3, 14), False),
])
def test_decoys_and_survivors_obey_identical_sensor_visibility(monkeypatch, pos, visible):
    monkeypatch.setattr("deadzone.sim.get_detector", lambda: SimpleNamespace(mode="model"))
    sim = Sim()
    sim.bodies["R1"].update(x=2, y=15, th=0)
    sim.fp.data["survivors"] = [{"id": "S", "pos": pos, "thermal": "pos_0001.png"}]
    sim.fp.data["decoys"] = [{"id": "D", "pos": pos, "thermal": "neg_0001.png", "label": "radiator"}]
    monkeypatch.setattr(sim, "line_of_sight", lambda start, end: end != (3, 14))
    hits = sim.ios["R1"].thermal()
    assert {h["id"] for h in hits} == ({"S", "D"} if visible else set())
    for h in hits:
        assert set(h) == {"id", "pos", "crop", "conf"}  # no truth decoy label


@pytest.mark.parametrize("fallback", ["sim", "missing_model"])
def test_fallback_sensor_never_reports_decoys_as_survivors(monkeypatch, tmp_path, fallback):
    env = {"DETECTOR": "sim"} if fallback == "sim" else {"DETECTOR_MODEL": str(tmp_path / "missing.pt")}
    detector = perception.make_detector(env=env)
    assert detector.mode == "sim"
    monkeypatch.setattr(perception, "_detector", detector)
    sim = Sim()
    decoy = sim.fp.data["decoys"][0]
    sim.bodies["R1"].update(x=decoy["pos"][0], y=decoy["pos"][1], th=0)
    sim.fp.data["survivors"] = [{"id": "S-test", "pos": decoy["pos"], "thermal": "pos_0001.png"}]
    assert {h["id"] for h in sim.ios["R1"].thermal()} == {"S-test"}
    sim.robots["R1"]._perceive(sim.ios["R1"])
    assert set(sim.robots["R1"].found) == {"S-test"}


@pytest.mark.skipif(importlib.util.find_spec("torch") is None or
                    importlib.util.find_spec("torchvision") is None, reason="requires model dependencies")
def test_real_sensor_and_model_reject_all_floorplan_decoys(monkeypatch):
    detector = perception.make_detector(env={})
    assert detector.mode == "model", getattr(detector, "reason", "model not loaded")
    monkeypatch.setattr(perception, "_detector", detector)
    sim = Sim()
    for decoy in sim.fp.data["decoys"]:
        sim.bodies["R1"].update(x=decoy["pos"][0], y=decoy["pos"][1], th=0)
        assert decoy["id"] in {h["id"] for h in sim.ios["R1"].thermal()}
        sim.robots["R1"]._perceive(sim.ios["R1"])
    assert not ({"D1", "D2", "D3"} & sim.robots["R1"].found.keys())
    assert all(detector.score(f"pos_{i:04d}.png") >= detector.threshold for i in (1, 2, 3))


def test_plan_status_is_source_sampled_and_only_visible_after_delivery(session):
    client, hub = session
    sim = hub.sim
    for queue in sim.network.queues.values():
        queue.clear()
    robot = sim.robots["R1"]
    plan = {"plan_id": "P-delayed", "zones": [
        {"id": "Z-east", "robot": "R1", "poly": [[34, 24], [38, 24], [38, 28], [34, 28]]}]}
    robot.plan = plan
    robot._apply_plan(plan)
    b = make_bundle("R1", "CMD", "telemetry", {
        "id": "R1", "pose": [2, 15, 0], "state": robot.state, "battery_pct": 90}, sim.time, 120)
    robot.outbox.append(b)
    sim._queue_peer_telemetry({"R1": [b]})
    assert b["payload"]["plan_id"] == "P-delayed" and b["payload"]["zone"] == "Z-east"
    sim.links = LinkGraph()
    sim._move_bundles(DT)
    assert next(r for r in hub.phone_view()["robots"] if r["id"] == "R1")["plan_id"] is None
    robot.plan = {"plan_id": "P-new"}
    robot._apply_plan(robot.plan)
    assert b["payload"]["plan_id"] == "P-delayed"  # queued reports must not be rewritten
    sim._update_links()
    sim._move_bundles(DT)
    with client.websocket_connect("/ws/phone?client=observer") as ws:
        ws.receive_json()
        view = ws.receive_json()["data"]
        delivered = next(r for r in view["robots"] if r["id"] == "R1")
        assert (delivered["plan_id"], delivered["zone"]) == ("P-delayed", "Z-east")
    # A genuinely newer unassigned report clears the status; an old packet cannot restore it.
    newer = make_bundle("R1", "CMD", "telemetry", {
        **b["payload"], "plan_id": None, "zone": None}, sim.time + 1, 200)
    newer["custodian"] = "CMD"
    sim.post.receive(newer, sim.time + 1)
    old = make_bundle("R1", "CMD", "telemetry", b["payload"], sim.time - 1, 200)
    old["custodian"] = "CMD"
    sim.post.receive(old, sim.time + 1)
    assert sim.post.robots["R1"]["plan_id"] is None


def test_api_dispatch_reaches_robot_and_is_reported_back_to_phone(session):
    client, hub = session
    plan = {"plan_id": "P-roundtrip", "author": "planner", "zones": [
        {"id": "Z1", "robot": "R1", "poly": [[3, 14], [6, 14], [6, 16], [3, 16]]}]}
    assert client.post("/api/plan", json=plan).json()["ok"]
    assert client.post("/api/dispatch", json={"plan_id": plan["plan_id"]}).json()["ok"]
    assert hub.sim.robots["R1"].plan is None
    assert hub.phone_view()["robots"][0]["plan_id"] is None
    for _ in range(20):
        hub.sim.tick()
    assert hub.sim.robots["R1"].plan["plan_id"] == plan["plan_id"]
    with client.websocket_connect("/ws/phone?client=roundtrip") as ws:
        ws.receive_json()
        view = ws.receive_json()["data"]
        r = next(r for r in view["robots"] if r["id"] == "R1")
        assert r["plan_id"] == plan["plan_id"]
