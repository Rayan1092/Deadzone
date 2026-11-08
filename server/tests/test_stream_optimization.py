"""Legacy-compatible updates and explicitly negotiated compressed map frames."""
import asyncio
import base64
from copy import deepcopy
import importlib
import json
import zlib

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from deadzone.network.dtn import make_bundle
from deadzone.network.propagation import LinkGraph
from deadzone.network.stream import compact_message, StreamState, thin_tick

api = importlib.import_module("deadzone.app")


@pytest.fixture
def hub(monkeypatch):
    for key, value in {"DZ_STREAM_OPTIMIZE": "1", "DZ_NETWORK_TRAFFIC": "1", "DZ_AUTOSTART": "0",
                       "DZ_CONTROL_LEASES": "0", "DZ_VOICE": "0", "DZ_CAMERA_TELEMETRY": "0",
                       "DZ_ROBOTS": "1", "DETECTOR": "sim"}.items():
        monkeypatch.setenv(key, value)
    instance = api.Hub()
    monkeypatch.setattr(api, "hub", instance)
    return instance


class Sink:
    def __init__(self): self.frames = []
    async def send_text(self, value): self.frames.append(json.loads(value))
    def of_type(self, kind): return [f for f in self.frames if f["t"] == kind]


def unpack(value):
    return zlib.decompress(base64.b64decode(value))


def test_compact_screen_and_phone_round_trip_without_changing_ordinary_clients(hub):
    with TestClient(api.app) as client, client.websocket_connect("/ws/screen?compact=1") as compact, \
            client.websocket_connect("/ws/screen") as ordinary, \
            client.websocket_connect("/ws/phone?compact=1&role=spectator") as phone:
        encoded = [compact.receive_json() for _ in range(4)]
        plain = [ordinary.receive_json() for _ in range(4)]
        assert [f["t"] for f in encoded] == ["hello", "maps", "tick", "plan_state"]
        assert encoded[0]["data"]["stream"]["map_encoding"] == "zlib-base64"
        assert plain[0]["data"]["stream"]["map_encoding"] == "base64"
        assert encoded[2]["data"] == thin_tick(hub.sim.snapshot())
        for key in ("reality", "command"):
            assert unpack(encoded[1]["data"][key]) == base64.b64decode(plain[1]["data"][key])
            assert len(encoded[1]["data"][key]) < len(plain[1]["data"][key]) / 2
        assert "encoding" not in plain[1]["data"]
        hello, view = phone.receive_json(), phone.receive_json()
        assert hello["data"]["stream"]["map_encoding"] == "zlib-base64"
        assert view["data"]["map_encoding"] == "zlib-base64"
        assert unpack(view["data"]["map"]) == hub.sim.post.map.tobytes()
        assert "reality" not in view["data"] and "survivors" not in hello["data"]["floorplan"]
    assert not hub.compact_clients


def test_compact_gate_off_rejects_without_registering_sessions(hub, monkeypatch):
    monkeypatch.setenv("DZ_STREAM_OPTIMIZE", "0")
    instance = api.Hub()
    monkeypatch.setattr(api, "hub", instance)
    with TestClient(api.app) as client:
        for path in ("/ws/screen?compact=1", "/ws/phone?compact=1"):
            with pytest.raises(WebSocketDisconnect) as error:
                with client.websocket_connect(path) as ws:
                    ws.receive_json()
            assert error.value.code == 1008
        with client.websocket_connect("/ws/screen") as ws:
            hello, maps = ws.receive_json(), ws.receive_json()
            assert "stream" not in hello["data"] and "version" not in maps["data"]
            assert maps["data"] == instance.sim.maps()
            assert ws.receive_json()["data"] == instance.sim.snapshot()
    assert not instance.compact_clients and not instance.phone_sessions and not instance.screens


def test_periodic_ticks_are_capped_but_control_and_events_are_not(hub):
    sink = Sink()
    hub.screens.add(sink)
    clock = [0.0]
    hub.stream.clock = lambda: clock[0]
    sent = []
    async def run():
        for i in range(101):
            clock[0] = i / 100
            before = len(sink.of_type("tick"))
            await hub.broadcast_tick()
            if len(sink.of_type("tick")) != before:
                sent.append(clock[0])
        before = len(sink.of_type("tick"))
        hub.sim.events.append({"kind": "test_observation"})
        await hub.broadcast_tick()  # same wall time: tick withheld, event still delivered
        assert len(sink.of_type("tick")) == before
        await hub.control("pause")
    asyncio.run(run())
    assert 14 <= len(sent) <= 16
    assert all(b - a >= 1 / 15 - 1e-9 for a, b in zip(sent, sent[1:]))
    assert any(f["data"]["kind"] == "test_observation" for f in sink.of_type("event"))
    assert sink.of_type("control")


def test_maps_change_versions_and_initial_reads_do_not_steal_a_broadcast(hub):
    sink = Sink()
    hub.screens.add(sink)
    hub.sim.tick_n = 5
    asyncio.run(hub.broadcast_tick(force_maps=True))
    first = sink.of_type("maps")[-1]["data"]
    asyncio.run(hub.broadcast_tick())
    assert len(sink.of_type("maps")) == 1
    hub.sim.post.map[0, 0] = (int(hub.sim.post.map[0, 0]) + 1) % 3
    newly_connected = hub.screen_maps()  # an initial reader must not consume the update for everyone
    asyncio.run(hub.broadcast_tick())
    second = sink.of_type("maps")[-1]["data"]
    assert second["version"] == newly_connected["version"] == first["version"] + 1
    assert second["versions"]["command"] == first["versions"]["command"] + 1
    assert second["versions"]["reality"] == first["versions"]["reality"]
    asyncio.run(hub.broadcast_tick(force_maps=True))
    assert len(sink.of_type("maps")) == 3
    assert sink.of_type("maps")[-1]["data"]["version"] == second["version"]
    asyncio.run(hub.reset())
    assert sink.of_type("maps")[-1]["data"]["version"] == 1


def test_lidar_thinning_is_wire_only_and_keeps_endpoints():
    source = {"reality": {"robots": [{"id": "R1", "lidar": [[i, i] for i in range(180)],
                                     "camera": {"hits": [{"id": "unchanged"}]}}]},
              "command": {"robots": []}, "stats": {"lidar_rays": 180}}
    original = deepcopy(source)
    wire = thin_tick(source)
    assert len(wire["reality"]["robots"][0]["lidar"]) == 24
    assert wire["reality"]["robots"][0]["lidar"][0] == [0, 0]
    assert wire["reality"]["robots"][0]["lidar"][-1] == [179, 179]
    assert source == original
    assert wire["stats"] == source["stats"]
    assert wire["reality"]["robots"][0]["camera"] == source["reality"]["robots"][0]["camera"]


def test_optional_belief_grids_and_private_hello_fields_are_preserved():
    raw = bytes([0, 1, 2, 255]) * 100
    encoded = base64.b64encode(raw).decode()
    message = {"t": "maps", "seq": 1, "time": 0, "data": {
        "w": 20, "h": 20, "cell": .25, "reality": encoded, "command": encoded,
        "belief": encoded, "belief_command": encoded, "missing": {"reality": 2.0, "command": 3.0}}}
    result = json.loads(compact_message(json.dumps(message)))
    for key in ("reality", "command", "belief", "belief_command"):
        assert unpack(result["data"][key]) == raw
    assert result["data"]["missing"] == message["data"]["missing"]
    hello = {"t": "hello", "data": {"controller_token": "test-only-private-token"}}
    assert json.loads(compact_message(json.dumps(hello)))["data"]["controller_token"] == "test-only-private-token"
    state = StreamState(True)
    first = state.maps(message["data"])
    message["data"]["missing"]["command"] = 2.5
    second = state.maps(message["data"])
    assert second["version"] == first["version"] + 1
    assert second["versions"] == first["versions"]


def test_compact_planner_still_sends_and_receives_normal_plan_json(hub):
    with TestClient(api.app) as client, client.websocket_connect("/ws/phone?compact=1&client=compact") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"t": "plan_edit", "data": {"plan_id": "P-stream", "zones": [
            {"id": "Z1", "robot": "R1", "poly": [[3, 14], [6, 14], [6, 16], [3, 16]]}]}})
        saved = ws.receive_json()
        assert saved["t"] == "plan_state" and saved["data"]["plan_id"] == "P-stream"
        assert saved["data"]["author"] == "compact"


def test_phone_stale_age_updates_even_when_periodic_maps_do_not_change(hub):
    hub.sim.tick_n = 5
    with TestClient(api.app) as client, client.websocket_connect("/ws/phone?compact=1") as ws:
        ws.receive_json()
        first = ws.receive_json()["data"]
        hub.sim.time += 5
        client.portal.call(hub.broadcast_tick)
        later = ws.receive_json()["data"]
        assert later["robots"][0]["stale_s"] == first["robots"][0]["stale_s"] + 5
        assert unpack(later["map"]) == unpack(first["map"])


def test_compact_phone_reset_keeps_encoding_and_discards_old_incident(hub):
    with TestClient(api.app) as client, client.websocket_connect("/ws/phone?compact=1") as ws:
        first = ws.receive_json()["data"]
        ws.receive_json()
        assert client.post("/api/control", json={"action": "reset"}).status_code == 200
        reset, view = ws.receive_json(), ws.receive_json()
        assert reset["t"] == "hello" and reset["data"]["plan_epoch"] != first["plan_epoch"]
        assert reset["data"]["stream"]["map_encoding"] == "zlib-base64"
        assert view["t"] == "cmd_view" and view["data"]["map_encoding"] == "zlib-base64"
        assert unpack(view["data"]["map"]) == hub.sim.post.map.tobytes()


def test_network_traffic_and_queued_hidden_payload_do_not_leak_to_phone(hub):
    bundle = make_bundle("R1", "CMD", "survivor", {"id": "SECRET_NOT_DELIVERED"}, hub.sim.time, 2000)
    hub.sim.network.queues["R1"].append(bundle)
    hub.sim.links = LinkGraph()
    hub.sim._move_bundles(.1)
    with TestClient(api.app) as client, client.websocket_connect("/ws/phone?compact=1") as ws:
        ws.receive_json()
        initial = ws.receive_json()
        assert "SECRET_NOT_DELIVERED" not in json.dumps(initial)
        assert "queues" not in initial["data"]
        for _ in range(2):
            client.portal.call(hub.broadcast_tick, True)
            message = ws.receive_json()
            assert message["t"] == "cmd_view"  # no hop/held event left queued between updates
            assert "SECRET_NOT_DELIVERED" not in json.dumps(message)
            assert unpack(message["data"]["map"]) == hub.sim.post.map.tobytes()
