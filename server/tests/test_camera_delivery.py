"""Camera privacy/delivery boundary and stale-frame semantics for phone pickers."""
import importlib
import json

from fastapi.testclient import TestClient
import pytest

from deadzone.network.dtn import DTNNetwork, make_bundle
from deadzone.network.propagation import LinkGraph
from deadzone.sim import Sim

api = importlib.import_module("deadzone.app")


@pytest.fixture
def sim(monkeypatch):
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "1")
    monkeypatch.setenv("DETECTOR", "sim")
    return Sim()


def frame(t=4):
    return {"t": t, "hits": [{"id": "H1", "pos": [3, 4], "verdict": "unsure",
                              "conf": .58, "crop": "unsure_person_01.png"}]}


def telemetry(created, camera=None, source="R1"):
    payload = {"id": "R1", "pose": [3, 14, 0], "state": "EXPLORING", "battery_pct": 80}
    if camera is not None:
        payload["camera"] = camera
    bundle = make_bundle(source, "CMD", "telemetry", payload, created, 500)
    bundle.update(custodian="CMD", hops=[source, "RL1", "CMD"])
    return bundle


def camera(sim, now):
    return sim.post.view(now)["robots"][0].get("camera")


def test_delayed_frame_keeps_capture_age_and_original_timestamp_names(sim):
    sim.robots["R1"].camera_frame = {"t": 12, "hits": [{"id": "HIDDEN_LIVE_HIT"}]}
    assert "HIDDEN_LIVE_HIT" not in json.dumps(sim.post.view(12))
    bundle = telemetry(5, frame())
    assert sim.post.receive(bundle, 12)
    view = camera(sim, 12)
    assert view["last_seen_s"] == 8
    assert view["delivered_t"] == 5 and view["reported_t"] == 12
    assert view["hits"][0]["conf"] == .58
    assert "HIDDEN_LIVE_HIT" not in json.dumps(view)
    bundle["payload"]["camera"]["hits"][0]["pos"][0] = 100
    view["hits"][0]["pos"][0] = 200
    assert camera(sim, 13)["hits"][0]["pos"] == [3, 4]


def test_new_status_does_not_freshen_camera_and_out_of_order_frames_do_not_rewind(sim):
    assert sim.post.receive(telemetry(5, frame()), 6)
    assert sim.post.receive(telemetry(15), 16)
    assert camera(sim, 20)["last_seen_s"] == 16
    assert camera(sim, 20)["reported_t"] == 6
    # A delayed camera can still be newer than the last camera even if its telemetry is old.
    assert sim.post.receive(telemetry(10, frame(9)), 17)
    assert camera(sim, 20)["t"] == 9
    assert sim.post.view(20)["robots"][0]["last_seen"] == 15
    assert sim.post.receive(telemetry(18, frame(3)), 19)
    assert camera(sim, 20)["t"] == 9
    assert sim.post.receive(telemetry(20, {"t": 20, "hits": []}), 21)
    assert camera(sim, 22)["hits"] == [] and camera(sim, 22)["last_seen_s"] == 2


@pytest.mark.parametrize("change", [
    lambda f: f.update(t=6),
    lambda f: f.update(t=float("nan")),
    lambda f: f["hits"][0].update(conf=True),
    lambda f: f["hits"][0].update(conf=1.1),
    lambda f: f["hits"][0].update(pos=[1000, 4]),
    lambda f: f["hits"][0].update(verdict="invented"),
    lambda f: f["hits"][0].update(crop="../private.png"),
    lambda f: f.update(hits=f["hits"] * 65),
])
def test_bad_camera_is_ignored_without_dropping_valid_robot_status(sim, change):
    raw = frame()
    change(raw)
    assert sim.post.receive(telemetry(5, raw), 8)
    assert camera(sim, 8) is None
    assert sim.post.view(8)["robots"][0]["state"] == "EXPLORING"


def test_unknown_fields_are_stripped_and_wrong_source_cannot_set_robot_camera(sim):
    raw = frame()
    raw.update(secret_truth="hidden")
    raw["hits"][0]["secret_truth"] = "hidden"
    assert sim.post.receive(telemetry(5, raw), 8)
    assert "secret_truth" not in json.dumps(camera(sim, 8))
    assert sim.post.receive(telemetry(6, frame(6), source="R2"), 9)
    assert camera(sim, 9)["t"] == 4


def test_undelivered_duplicate_and_expired_bundles_do_not_update_camera(sim):
    bundle = telemetry(5, frame())
    bundle["custodian"] = "RL1"
    assert not sim.post.receive(bundle, 8)
    assert not sim.post.view(8)["robots"]
    bundle["custodian"] = "CMD"
    assert sim.post.receive(bundle, 8)
    bundle["payload"]["camera"] = frame(5)
    assert not sim.post.receive(bundle, 9)
    expired = telemetry(5, frame(5))
    expired["ttl"] = 1
    assert not sim.post.receive(expired, 9)
    assert camera(sim, 9)["t"] == 4


def test_flag_off_and_reset_keep_camera_out_of_legacy_views(sim, monkeypatch):
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "0")
    sim.reset()
    assert sim.post.receive(telemetry(5, frame()), 6)
    assert "camera" not in sim.post.robots["R1"]
    assert camera(sim, 8) is None
    monkeypatch.setenv("DZ_CAMERA_TELEMETRY", "1")
    sim.reset()
    assert not sim.post.view(8)["robots"]


def test_outage_custody_preserves_original_camera_until_actual_transport_delivery(sim):
    network = DTNNetwork()
    network.register("R1")
    network.register("CMD")
    raw = frame()
    bundle = telemetry(5, raw)
    bundle.update(custodian="R1", hops=["R1"])
    network.queues["R1"].append(bundle)
    raw["hits"][0]["id"] = "FUTURE_LIVE_HIT"
    raw["t"] = 999
    links = LinkGraph()
    assert network.step(links, .1, 6) == []
    assert not sim.post.view(6)["robots"]
    links.up[("CMD", "R1")] = True
    links.rssi[("CMD", "R1")] = -60
    arrived = network.step(links, .1, 8)
    assert len(arrived) == 1
    assert sim.post.receive(arrived[0], 8)
    assert camera(sim, 8)["t"] == 4
    assert camera(sim, 8)["hits"][0]["id"] == "H1"
    assert "FUTURE_LIVE_HIT" not in json.dumps(camera(sim, 8))


def test_real_robot_producer_reaches_command_without_copying_reality_camera(sim):
    sim.robots["R1"].camera_frame = {"t": 999, "hits": [{"id": "PRIVATE_LIVE_CAMERA"}]}
    for _ in range(20):
        sim.tick()
        reports = sim.post.view(sim.time)["robots"]
        if reports and reports[0].get("camera"):
            break
    received = reports[0]["camera"]
    assert received["t"] <= received["delivered_t"] <= received["reported_t"] <= sim.time
    assert received["last_seen_s"] == round(sim.time - received["t"], 1)
    assert "PRIVATE_LIVE_CAMERA" not in json.dumps(received)


def test_two_phones_share_delivered_camera_without_bypassing_exclusive_control(monkeypatch):
    for name, value in {"DZ_CAMERA_TELEMETRY": "1", "DZ_CONTROL_LEASES": "1", "DZ_AUTOSTART": "0",
                        "DZ_ROBOTS": "1", "DZ_VOICE": "0", "DETECTOR": "sim"}.items():
        monkeypatch.setenv(name, value)
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    with TestClient(api.app) as client, client.websocket_connect("/ws/phone?client=a") as a, \
            client.websocket_connect("/ws/phone?client=b") as b:
        hello_a, hello_b = a.receive_json()["data"], b.receive_json()["data"]
        assert a.receive_json()["t"] == b.receive_json()["t"] == "cmd_view"
        ha = {"X-Controller-Token": hello_a["controller_token"]}
        hb = {"X-Controller-Token": hello_b["controller_token"]}
        assert client.post("/api/leases/claim", headers=ha, json={"robot": "R1", "name": "A"}).status_code == 200
        assert client.post("/api/leases/claim", headers=hb, json={"robot": "R1", "name": "B"}).status_code == 409
        assert client.post("/api/robot-command", headers=hb, json={"robot": "R1", "action": "resume"}).status_code == 403
        # Startup now includes Rayan's real camera frame: deliver a current frame,
        # since an older synthetic capture must correctly be ignored.
        delivered = telemetry(hub.sim.time, frame(hub.sim.time))
        assert client.portal.call(hub.sim.post.receive, delivered, hub.sim.time)
        client.portal.call(hub.broadcast_tick, True)
        views = []
        for phone in (a, b):
            for _ in range(5):
                message = phone.receive_json()
                if message["t"] == "cmd_view":
                    views.append(message["data"])
                    break
        assert len(views) == 2
        assert views[0]["robots"][0]["camera"] == views[1]["robots"][0]["camera"]
        assert views[0]["robots"][0]["camera"]["hits"][0]["conf"] == .58
        assert "reality" not in json.dumps(views)
