"""RSSI is a Command prediction, never a projection of the live radio graph."""
import base64
from copy import deepcopy
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.command.post import CommandPost  # noqa: E402
from deadzone.floorplan import FloorPlan  # noqa: E402
from deadzone.network.dtn import make_bundle  # noqa: E402
from deadzone.network.map_delta import MapDeltaState  # noqa: E402
from deadzone.network.propagation import rssi, rssi_grid  # noqa: E402
from deadzone.network.stream import compact_message  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


@pytest.fixture
def data():
    return {"id": "coverage-test", "name": "Coverage test", "size": [8, 4], "cell": .5,
            "materials": {"brick": 10, "metal": 22, "rubble": 8},
            "walls": [{"a": [4, 0], "b": [4, 4], "material": "brick"}],
            "doors": [], "rooms": [], "hazards": [], "survivors": [], "rubble": [],
            "entry": [1, 2], "command_post": {"pos": [0, 2], "tx_dbm": 23}}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("DZ_COVERAGE_GRID", "1")


def unpack(coverage):
    raw = zlib.decompress(base64.b64decode(coverage["data"], validate=True))
    assert len(raw) == coverage["w"] * coverage["h"]
    return np.frombuffer(raw, dtype=np.int8).reshape(coverage["h"], coverage["w"])


def relay_report(post, *, rid="RL1", pos=(6, 2), created=1, revision=1, on=True, **overrides):
    b = make_bundle(rid, "CMD", "telemetry",
                    {"id": rid, "node_type": "relay", "pos": list(pos), "on": on,
                     "revision": revision}, created, 160)
    b.update(custodian="CMD", hops=[rid, "CMD"])
    b.update(overrides)
    return b


@pytest.mark.parametrize("walls", [False, True])
@pytest.mark.parametrize("source", [(0, 2), (4, 2), (4.25, .25)])
def test_batched_grid_matches_scalar_propagation_at_every_cell(data, walls, source):
    if not walls:
        data["walls"] = []
    else:
        data["walls"] += [{"a": [1, 0], "b": [6, 4], "material": "metal"},
                          {"a": [2, 2], "b": [2, 2], "material": "brick"}]
    # Nonintegral dimensions still use exactly the map's rounded w/h cells.
    data["size"] = [8.2, 4.1]
    fp = FloorPlan(data)
    got = rssi_grid(fp, source, 17)
    expected = [[rssi(fp, source, fp.to_world(ix, iy), 17)
                 for ix in range(fp.w)] for iy in range(fp.h)]
    np.testing.assert_allclose(got, expected, rtol=0, atol=1e-12)


@pytest.mark.parametrize("flag", [None, "0", "true"])
def test_default_off_adds_no_fields_or_propagation_work(data, monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("DZ_COVERAGE_GRID", raising=False)
    else:
        monkeypatch.setenv("DZ_COVERAGE_GRID", flag)
    module = importlib.import_module("deadzone.command.post")
    def unexpected(*args):
        pytest.fail("flag-off constructed a coverage grid")
    monkeypatch.setattr(module, "CoverageGrid", unexpected)
    post = CommandPost(FloorPlan(data))
    assert post.coverage() == {} and post.coverage_grid is None
    assert set(post.view(0)) == {"robots", "relays", "survivors", "faults", "routes"}


def test_compact_shape_rounding_clipping_and_known_wall_loss(data, enabled):
    post = CommandPost(FloorPlan(data))
    field = post.coverage()["coverage"]
    assert field | {"data": ""} == {
        "w": 16, "h": 8, "cell": .5, "encoding": "zlib-base64", "dtype": "int8",
        "unit": "dBm", "predicted": True, "sources": ["CMD"], "data": ""}
    expected = rssi_grid(post.coverage_grid.prior, (0, 2), 23)
    np.testing.assert_array_equal(unpack(field), np.clip(np.rint(expected), -128, 127))
    no_wall = FloorPlan(data | {"walls": []})
    np.testing.assert_allclose(rssi_grid(no_wall, (0, 2), 23)[:, 8:] - expected[:, 8:], 10)
    for tx, value in [(-500, -128), (500, 127)]:
        extreme = CommandPost(FloorPlan(data | {"command_post": {"pos": [0, 2], "tx_dbm": tx}}))
        assert np.all(unpack(extreme.coverage()["coverage"]) == value)


def test_prior_snapshot_excludes_hidden_geometry_and_ignores_later_truth(data, enabled):
    truth_data = deepcopy(data)
    truth_data.update(
        dynamic_walls=[{"a": [2, 0], "b": [2, 4], "material": "metal"}],
        rubble=[{"poly": [[1, 0], [3, 0], [3, 4], [1, 4]]}],
        survivors=[{"id": "secret", "pos": [7, 3]}])
    truth = FloorPlan(truth_data)
    post = CommandPost(truth)  # defensive boundary even for a truth caller
    expected = CommandPost(FloorPlan(data)).coverage()
    assert post.coverage() == expected
    assert not np.allclose(rssi_grid(truth, (0, 2), 23),
                           rssi_grid(post.coverage_grid.prior, (0, 2), 23))
    truth.segs[:] = 0
    truth.seg_loss[:] = 999
    truth.data["walls"].clear()
    post.map[:] = 2  # occupied observations have no reported material/loss
    assert post.coverage() == expected
    assert not {"survivors", "rubble", "dynamic_walls"} & post.coverage_grid.prior.data.keys()


def test_known_furniture_uses_shared_prior_loss_when_enabled(data, enabled, monkeypatch):
    monkeypatch.setenv("DZ_OBSTACLES", "1")
    data["obstacles"] = [{"poly": [[1, 0], [2, 0], [2, 4], [1, 4]],
                          "material": "metal", "loss_db": 3}]
    post = CommandPost(FloorPlan(data))
    known = post.coverage_grid.prior
    assert known.data["obstacles"] == data["obstacles"]
    expected = rssi_grid(known, (0, 2), 23)
    no_furniture = rssi_grid(FloorPlan(data | {"obstacles": []}), (0, 2), 23)
    np.testing.assert_allclose(no_furniture[:, 4:] - expected[:, 4:], 3)
    np.testing.assert_array_equal(unpack(post.coverage()["coverage"]), np.rint(expected))


def test_delivered_relays_strongest_signal_order_power_and_bounded_cache(data, enabled, monkeypatch):
    module = importlib.import_module("deadzone.command.coverage")
    original = module.rssi_grid
    calls = []
    def measured(*args):
        calls.append(args[1:])
        return original(*args)
    monkeypatch.setattr(module, "rssi_grid", measured)
    post = CommandPost(FloorPlan(data))
    baseline = post.coverage()["coverage"]
    assert len(calls) == 1
    b = relay_report(post)
    assert post.receive(b, 1)
    field = post.coverage()["coverage"]
    expected = np.maximum(original(post.coverage_grid.prior, (0, 2), 23),
                          original(post.coverage_grid.prior, (6, 2), 20))
    np.testing.assert_array_equal(unpack(field), np.rint(expected))
    assert field["sources"] == ["CMD", "RL1"] and np.any(unpack(field) > unpack(baseline))
    assert len(calls) == 2
    assert not post.receive(b, 2)  # duplicate
    assert post.receive(relay_report(post, created=0, pos=(1, 1)), 2)  # older report
    assert post.receive(relay_report(post, created=1, revision=0, on=False), 2)
    assert post.receive(relay_report(post, created=2), 2)  # same stationary source
    assert post.coverage()["coverage"] == field and len(calls) == 2
    field["sources"].clear()  # callers cannot mutate the cached payload
    assert post.coverage()["coverage"]["sources"] == ["CMD", "RL1"]
    assert post.receive(relay_report(post, created=2, revision=2, pos=(7, 2)), 2)
    assert post.coverage()["coverage"] != field and len(calls) == 3
    assert len(post.coverage_grid._grids) == 2
    assert post.receive(relay_report(post, created=3, on=False), 3)
    assert post.coverage()["coverage"] == baseline
    assert set(post.coverage_grid._grids) == {"CMD"}


@pytest.mark.parametrize("overrides, now", [({"custodian": "RL1"}, 1),
    ({"dst": "R1"}, 1), ({"ttl": .1}, 2)])
def test_undelivered_misdirected_or_expired_reports_do_not_change_prediction(data, enabled, overrides, now):
    post = CommandPost(FloorPlan(data))
    before = post.coverage()
    assert not post.receive(relay_report(post, **overrides), now)
    assert post.coverage() == before


def test_real_dtn_delivery_and_reset_never_read_live_relays_or_links(data, enabled, tmp_path):
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data))
    sim = Sim(plan_path=path, n_robots=1, seed=7)
    before = sim.maps()["coverage"]
    rid = sim.add_relay([2, 2])
    assert sim.maps()["coverage"] == before and rid not in sim.post.relays
    sim.tick()
    assert rid in sim.post.relays  # accepted through real custody transfer
    delivered = sim.maps()["coverage"]
    assert delivered["sources"] == ["CMD", rid]
    sim.set_relay_power(rid, False)
    sim.relays[rid]["pos"] = [7, 3]
    sim.relays[rid]["destroyed"] = True
    sim.fp.seg_loss[:] = 500
    sim.links.rssi.clear()
    sim.links.up.clear()
    assert sim.maps()["coverage"] == delivered
    sim.reset()
    assert sim.maps()["coverage"] == before


def test_screen_and_phone_messages_and_both_compression_protocols(data, enabled, tmp_path, monkeypatch):
    api = importlib.import_module("deadzone.app")
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr("deadzone.scenarios.registered_floorplans", lambda: {"coverage": path})
    monkeypatch.setenv("DZ_FLOORPLAN", "coverage")
    monkeypatch.setenv("DZ_ROBOTS", "1")
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_STREAM_OPTIMIZE", "0")
    monkeypatch.setenv("DZ_COMPACT_STREAM", "1")
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    with TestClient(api.app) as client, client.websocket_connect("/ws/screen?map_deltas=1") as screen, \
            client.websocket_connect("/ws/phone?role=spectator") as phone:
        hello, maps = screen.receive_json(), screen.receive_json()
        phone_hello, cmd_view = phone.receive_json(), phone.receive_json()
        assert hello["t"] == phone_hello["t"] == "hello"
        assert maps["t"] == "maps" and cmd_view["t"] == "cmd_view"
        coverage = maps["data"]["coverage"]
        assert coverage == cmd_view["data"]["coverage"] == hub.sim.post.coverage()["coverage"]
        assert "reality" not in cmd_view["data"]
        assert "coverage" not in hub.sim.snapshot()["command"]  # no per-tick/AI grid bulk
    delta = MapDeltaState("test")
    _, full = delta.maps(hub.sim.maps())
    assert full["coverage"] == coverage and delta.maps(hub.sim.maps()) is None
    hub.sim.post.receive(relay_report(hub.sim.post), 1)
    kind, patch = delta.maps(hub.sim.maps())
    assert kind == "map_patch" and patch["grids"] == {}  # coverage-only metadata update
    assert patch["coverage"]["sources"] == ["CMD", "RL1"]
    for kind, body in [("maps", hub.sim.maps()), ("cmd_view", hub.phone_view())]:
        frame = {"t": kind, "seq": 1, "time": 1, "data": body}
        packed = json.loads(compact_message(json.dumps(frame)))
        assert packed["data"]["coverage"] == hub.sim.post.coverage()["coverage"]


def test_flag_off_screen_and_phone_shapes(data, monkeypatch, tmp_path):
    monkeypatch.delenv("DZ_COVERAGE_GRID", raising=False)
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data))
    sim = Sim(plan_path=path, n_robots=1)
    api = importlib.import_module("deadzone.app")
    assert set(sim.maps()) == {"w", "h", "cell", "reality", "command"}
    assert "coverage" not in api.Hub.phone_view(SimpleNamespace(
        sim=sim, phone_frames=SimpleNamespace(enabled=False)))
