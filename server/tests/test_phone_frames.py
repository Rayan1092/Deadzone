"""Screen JPEGs respect delivered Command contact, incident resets and size/rate bounds."""
import asyncio
import base64
import importlib
from io import BytesIO
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from deadzone.command.frames import MAX_BODY_BYTES
from deadzone.network.dtn import make_bundle
from deadzone.network.propagation import LinkGraph

api = importlib.import_module("deadzone.app")


def jpeg(size=(320, 180), fmt="JPEG", color="red"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode()


@pytest.fixture
def session(monkeypatch):
    for key, value in {"DZ_PHONE_FRAMES": "1", "DZ_AUTOSTART": "0", "DZ_ROBOTS": "3",
                       "DZ_STREAM_OPTIMIZE": "0", "DZ_COMPACT_STREAM": "0"}.items():
        monkeypatch.setenv(key, value)
    instance = api.Hub()
    wall = [10.0]
    instance.phone_frames.clock = lambda: wall[0]
    monkeypatch.setattr(api, "hub", instance)
    with TestClient(api.app) as client:
        yield client, instance, wall


def body(hub, **changes):
    return {"epoch": hub.plan_epoch, "t": hub.sim.time, "jpeg": jpeg(), **changes}


def upload(client, hub, rid="R1", **changes):
    return client.post(f"/api/frames/{rid}", json=body(hub, **changes))


def report(hub, created):
    p = {"id": "R1", "pose": [2, 15, 0], "state": "EXPLORING", "battery_pct": 90}
    b = make_bundle("R1", "CMD", "telemetry", p, created, 120)
    hub.sim.robots["R1"].outbox.append(b)


def test_feature_off_has_no_wire_changes_or_uploads(session, monkeypatch):
    client, _, _ = session
    monkeypatch.setenv("DZ_PHONE_FRAMES", "0")
    instance = api.Hub()
    monkeypatch.setattr(api, "hub", instance)
    assert client.post("/api/frames/R1", content=b"invalid").status_code == 404
    assert "phone_frames" not in json.loads(instance.hello())["data"]
    assert "phone_frames" not in instance.phone_hello("test", "spectator")
    assert all("phone_frame" not in r for r in instance.phone_view()["robots"])


def test_upload_reaches_paused_phone_but_not_ticks_ai_or_screen(session):
    client, hub, _ = session
    with client.websocket_connect("/ws/phone?role=spectator") as phone:
        hello, before = phone.receive_json(), phone.receive_json()
        assert hello["data"]["phone_frames"] == {"epoch": hub.plan_epoch,
            "max_width": 320, "max_height": 180, "max_fps": 3}
        assert not any("phone_frame" in r for r in before["data"]["robots"])
        assert upload(client, hub).status_code == 200
        frame = phone.receive_json()
        assert frame["t"] == "cmd_view"
        robot = next(r for r in frame["data"]["robots"] if r["id"] == "R1")
        image = robot["phone_frame"]
        assert image == {"jpeg": jpeg(), "mime": "image/jpeg", "width": 320, "height": 180,
                         "t": hub.sim.time, "last_seen_s": 0}
        assert not hub.running and "reality" not in frame["data"]
        assert "phone_frame" not in json.dumps(hub.sim.post.view(hub.sim.time))
        assert '"jpeg"' not in json.dumps(hub.screen_snapshot())
        assert '"jpeg"' not in json.dumps(hub.screen_maps())


def test_dark_gate_uses_delivered_reports_not_live_graph_and_recovers(session):
    client, hub, wall = session
    assert upload(client, hub).status_code == 200
    accepted = hub.phone_frames.view("R1", hub.sim.time)
    hub.sim.time = 5
    report(hub, 5)
    hub.sim.links = LinkGraph()
    hub.sim._move_bundles(.1)
    assert upload(client, hub, jpeg=jpeg(color="blue")).status_code == 409
    assert all("phone_frame" not in r for r in hub.phone_view()["robots"])
    assert hub.phone_frames.latest["R1"]["jpeg"] == accepted["jpeg"]
    hub.sim._update_links()
    hub.sim._move_bundles(.1)
    wall[0] += 1
    assert upload(client, hub, jpeg=jpeg(color="blue")).status_code == 200
    frame = next(r for r in hub.phone_view()["robots"] if r["id"] == "R1")["phone_frame"]
    assert frame["t"] == 5 and frame["jpeg"] != accepted["jpeg"]


def test_boundary_age_and_shutdown_gate(session):
    client, hub, _ = session
    sent = hub.sim.post.robots["R1"]["sent_t"]
    hub.sim.time = sent + 3
    assert upload(client, hub).status_code == 200
    hub.sim.time += .001
    assert upload(client, hub).status_code == 409
    hub.sim.time = sent
    hub.sim.post.robots["R1"]["state"] = "SHUTDOWN"
    assert upload(client, hub).status_code == 409


def test_rate_is_per_robot_real_time_and_latest_only(session):
    client, hub, wall = session
    assert upload(client, hub).status_code == 200
    assert upload(client, hub, jpeg=jpeg(color="blue")).status_code == 429
    assert upload(client, hub, "R2").status_code == 200
    wall[0] += .334
    assert upload(client, hub, jpeg=jpeg(color="blue")).status_code == 200
    assert len(hub.phone_frames.latest) == 2
    assert hub.phone_frames.latest["R1"]["jpeg"] == jpeg(color="blue")
    result = hub.phone_frames.view("R1", hub.sim.time + 2)
    assert result["last_seen_s"] == 2
    result["jpeg"] = "changed"
    assert hub.phone_frames.latest["R1"]["jpeg"] != "changed"


@pytest.mark.parametrize("image", ["not base64!", base64.b64encode(b"not an image").decode(),
    jpeg((321, 180)), jpeg((320, 181)), jpeg(fmt="PNG"), jpeg()[:100]])
def test_rejects_invalid_images_without_replacing_last(session, image):
    client, hub, wall = session
    assert upload(client, hub).status_code == 200
    wall[0] += 1
    result = upload(client, hub, jpeg=image)
    assert result.status_code == 422
    assert hub.phone_frames.latest["R1"]["jpeg"] == jpeg()


@pytest.mark.parametrize("changes", [{"t": -1}, {"t": "1"}, {"epoch": "bad"},
    {"jpeg": None}, {"extra": True}])
def test_request_validation_is_strict_and_redacted(session, changes):
    client, hub, _ = session
    result = upload(client, hub, **changes)
    assert result.status_code == 422
    assert jpeg() not in result.text


def test_reset_clears_images_rate_and_rejects_old_incident(session):
    client, hub, _ = session
    old = body(hub)
    assert upload(client, hub).status_code == 200
    asyncio.run(hub.reset())
    assert not hub.phone_frames.latest and not hub.phone_frames.accepted_at
    assert client.post("/api/frames/R1", json=old).status_code == 409
    assert upload(client, hub).status_code == 200


def test_unknown_robot_unreported_robot_future_and_out_of_order(session):
    client, hub, wall = session
    assert upload(client, hub, "R99").status_code == 404
    assert upload(client, hub, t=hub.sim.time + .1).status_code == 409
    assert upload(client, hub).status_code == 200
    wall[0] += 1
    assert upload(client, hub, t=0).status_code == 409
    hub.sim.post.robots.pop("R1")
    assert upload(client, hub).status_code == 409


def test_bounded_body_and_small_valid_jpeg(session):
    client, hub, _ = session
    assert client.post("/api/frames/R1", content=b"x" * (MAX_BODY_BYTES + 1)).status_code == 413
    assert upload(client, hub, jpeg=jpeg((1, 1))).status_code == 200
