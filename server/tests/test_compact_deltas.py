"""The compact observer stream must reconstruct every map without changing sensing."""
import base64
from copy import deepcopy
import importlib
import json
import struct
import zlib

from fastapi.testclient import TestClient
import pytest

from deadzone.network.map_delta import MapDeltaState

api = importlib.import_module("deadzone.app")


def maps(w=4, h=3):
    raw = bytes(i % 4 for i in range(w * h))
    return {"w": w, "h": h, "cell": .25,
            **{key: base64.b64encode(raw).decode() for key in ("reality", "command")}}


def unpack(value):
    return zlib.decompress(base64.b64decode(value))


def test_delta_contains_only_changed_cells_and_no_unchanged_grid():
    state = MapDeltaState("incident-1")
    source = maps()
    kind, first = state.maps(source)
    assert kind == "maps" and first["version"] == 0
    assert unpack(first["command"]) == base64.b64decode(source["command"])
    assert state.maps(source) is None
    raw = bytearray(base64.b64decode(source["command"]))
    raw[5] = 3
    source["command"] = base64.b64encode(raw).decode()
    kind, patch = state.maps(source)
    assert kind == "map_patch" and patch["base"] == 0 and patch["version"] == 1
    assert patch["epoch"] == "incident-1" and set(patch["grids"]) == {"command"}
    assert list(struct.iter_unpack("<IB", unpack(patch["grids"]["command"]))) == [(5, 3)]


def test_optional_grids_and_metadata_round_trip_without_fabricating_them():
    state = MapDeltaState("one")
    data = maps()
    data["belief"] = data["command"]
    data["missing"] = {"reality": 2, "command": 3}
    _, first = state.maps(data)
    assert "belief_command" not in first
    assert unpack(first["belief"]) == base64.b64decode(data["belief"])
    data["missing"] = {"reality": 1, "command": 2}
    kind, patch = state.maps(data)
    assert kind == "map_patch" and patch["grids"] == {} and patch["missing"]["command"] == 2


def test_reset_and_geometry_changes_get_a_new_keyframe():
    state = MapDeltaState("old")
    state.maps(maps())
    state.reset("new")
    _, frame = state.maps(maps())
    assert frame["epoch"] == "new" and frame["version"] == 0
    kind, frame = state.maps(maps(5, 3))
    assert kind == "maps" and frame["w"] == 5
    assert len(unpack(frame["reality"])) == 15


def test_hello_for_geometry_does_not_discard_the_delta_baseline():
    state = MapDeltaState("same")
    source = maps()
    state.maps(source)
    hello = json.loads(state.transform(json.dumps({"t": "hello", "data": {"controller_token": "private"}})))
    assert hello["data"]["controller_token"] == "private"
    assert hello["data"]["compact_stream"]["epoch"] == "same"
    assert state.maps(source) is None


@pytest.fixture
def hub(monkeypatch):
    for name, value in {"DZ_COMPACT_STREAM": "1", "DZ_STREAM_OPTIMIZE": "0", "DZ_ROBOTS": "3",
                         "DZ_AUTOSTART": "0", "DZ_CONTROL_LEASES": "0", "DZ_VOICE": "0",
                         "DZ_SENSOR_VIEW": "0", "DZ_ROBOT_COLLISIONS": "0", "DETECTOR": "sim"}.items():
        monkeypatch.setenv(name, value)
    instance = api.Hub()
    instance.sim.drain_events()
    monkeypatch.setattr(api, "hub", instance)
    return instance


def test_negotiated_delta_and_ordinary_clients_coexist_and_late_join_is_independent(hub):
    with TestClient(api.app) as client, client.websocket_connect("/ws/screen?map_deltas=1") as delta, \
            client.websocket_connect("/ws/screen") as ordinary:
        first = [delta.receive_json() for _ in range(4)]
        normal = [ordinary.receive_json() for _ in range(4)]
        assert "compact_stream" in first[0]["data"] and "compact_stream" not in normal[0]["data"]
        assert unpack(first[1]["data"]["command"]) == base64.b64decode(normal[1]["data"]["command"])
        hub.sim.post.map[0, 0] = 1
        client.portal.call(hub.broadcast_tick, True)
        assert delta.receive_json()["t"] == "tick"
        patch = delta.receive_json()
        assert patch["t"] == "map_patch" and patch["data"]["base"] == 0
        assert ordinary.receive_json()["t"] == "tick"
        assert ordinary.receive_json()["t"] == "maps"
        with client.websocket_connect("/ws/screen?map_deltas=1") as late:
            frames = [late.receive_json() for _ in range(4)]
            assert frames[1]["t"] == "maps" and frames[1]["data"]["version"] == 0
            hub.sim.post.map[0, 1] = 2
            client.portal.call(hub.broadcast_tick, True)
            assert delta.receive_json()["t"] == "tick"
            assert delta.receive_json()["data"]["base"] == 1
            assert late.receive_json()["t"] == "tick"
            assert late.receive_json()["data"]["base"] == 0
    assert not hub.delta_screens


def test_gate_off_keeps_legacy_shapes_even_when_client_advertises_support(hub, monkeypatch):
    monkeypatch.setenv("DZ_COMPACT_STREAM", "0")
    legacy = api.Hub()
    monkeypatch.setattr(api, "hub", legacy)
    with TestClient(api.app) as client, client.websocket_connect("/ws/screen?map_deltas=1") as ws:
        hello, frame, tick = ws.receive_json(), ws.receive_json(), ws.receive_json()
        assert "compact_stream" not in hello["data"]
        assert frame["data"] == legacy.sim.maps()
        assert tick["data"] == legacy.sim.snapshot()
    assert not legacy.delta_screens


def test_reset_keeps_socket_but_replaces_epoch_and_full_baseline(hub):
    with TestClient(api.app) as client, client.websocket_connect("/ws/screen?map_deltas=1") as ws:
        old = [ws.receive_json() for _ in range(4)]
        assert client.post("/api/control", json={"action": "reset"}).status_code == 200
        hello, keyframe = ws.receive_json(), ws.receive_json()
        assert hello["t"] == "hello" and keyframe["t"] == "maps"
        assert keyframe["data"]["epoch"] != old[1]["data"]["epoch"]
        assert keyframe["data"]["version"] == 0
        assert unpack(keyframe["data"]["command"]) == hub.sim.post.map.tobytes()


def test_phone_is_never_registered_for_screen_deltas(hub):
    with TestClient(api.app) as client, client.websocket_connect("/ws/phone?role=spectator") as ws:
        hello, view = ws.receive_json(), ws.receive_json()
        assert "compact_stream" not in hello["data"] and "encoding" not in view["data"]
        assert "reality" not in view["data"] and "grids" not in view["data"]
        assert base64.b64decode(view["data"]["map"]) == hub.sim.post.map.tobytes()
    assert not hub.delta_screens


def test_current_lidar_fans_and_all_sensor_data_are_unchanged(hub):
    source = hub.sim.snapshot()
    original = deepcopy(source)
    wire = hub.screen_snapshot()
    assert wire == source == original
    assert all(len(robot["lidar"]) == 36 for robot in wire["reality"]["robots"])
    assert all(len(robot["lidar"][::2]) == 18 for robot in wire["reality"]["robots"])
    hub.sim.robots["R1"].lidar_pts = [[i, i] for i in range(180)]
    assert len(hub.screen_snapshot()["reality"]["robots"][0]["lidar"]) == 36
    assert len(hub.sim.robots["R1"].lidar_pts) == 180


def test_old_stream_profile_is_preserved_when_both_gates_are_enabled(hub, monkeypatch):
    monkeypatch.setenv("DZ_STREAM_OPTIMIZE", "1")
    both = api.Hub()
    snapshot = both.screen_snapshot()
    assert json.loads(both.hello())["data"]["stream"]["lidar_max_points"] == 24
    assert all(len(robot["lidar"]) == 24 for robot in snapshot["reality"]["robots"])
