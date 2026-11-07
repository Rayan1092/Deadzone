"""Command routes, detector status in hello and the /crops static route (frontend asks)."""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.network.dtn import PRIO, make_bundle  # noqa: E402
from deadzone.sim import Sim  # noqa: E402

api = importlib.import_module("deadzone.app")


def route_bundle(t, length=12.0, survivor="S1", beacon=None):
    payload = {"survivor": survivor, "by": "R1", "path": [[1.0, 15.0], [5.0, 15.0], [5.0, 20.0]],
               "length_m": length, "clearance_m": 0.25, "beacon": beacon, "t": t}
    b = make_bundle("R1", "CMD", "rescue_route", payload, t, 120)
    b["custodian"] = "CMD"
    return b


def test_rescue_route_is_priority_one():
    assert PRIO["rescue_route"] == 1
    assert make_bundle("R1", "CMD", "rescue_route", {}, 0.0, 10)["prio"] == 1


def test_command_learns_a_route_only_from_a_delivered_bundle():
    sim = Sim()
    assert sim.post.view(0)["routes"] == []
    undelivered = dict(route_bundle(1.0), custodian="R1")
    assert not sim.post.receive(undelivered, 2.0)
    assert sim.post.view(2.0)["routes"] == []
    assert sim.post.receive(route_bundle(1.0, beacon="RL2"), 3.5)
    [route] = sim.post.view(3.5)["routes"]
    assert route == {"survivor": "S1", "by": "R1", "path": [[1.0, 15.0], [5.0, 15.0], [5.0, 20.0]],
                     "length_m": 12.0, "clearance_m": 0.25, "beacon": "RL2", "reported_t": 3.5}
    [event] = [e for e in sim.post.events if e["kind"] == "rescue_route_reported"]
    assert event == {"kind": "rescue_route_reported", "survivor": "S1", "by": "R1", "length_m": 12.0, "delay_s": 2.5}


def test_newest_route_per_survivor_wins_and_a_delayed_older_one_does_not_roll_back():
    sim = Sim()
    sim.post.receive(route_bundle(5.0, length=20.0), 6.0)
    sim.post.receive(route_bundle(2.0, length=30.0), 7.0)  # older route arriving late
    assert [r["length_m"] for r in sim.post.view(7.0)["routes"]] == [20.0]
    sim.post.receive(route_bundle(4.0, length=9.0, survivor="S2"), 8.0)
    assert sorted(r["survivor"] for r in sim.post.view(8.0)["routes"]) == ["S1", "S2"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_ROBOTS", "1")
    monkeypatch.setattr(api, "hub", api.Hub())
    with TestClient(api.app) as c:
        yield c


def test_screen_and_phone_hello_carry_detector_status(client):
    mode = api.get_detector().mode
    with client.websocket_connect("/ws/screen") as ws:
        hello = ws.receive_json()
        assert hello["t"] == "hello" and hello["data"]["detector"] == mode
        assert (hello["data"]["detector_reason"] is None) == (mode == "model")
    with client.websocket_connect("/ws/phone?client=phone-a") as ws:
        hello = ws.receive_json()
        assert hello["t"] == "hello" and hello["data"]["detector"] == mode


@pytest.mark.skipif(not api.CROPS_DIR.exists(), reason="runtime crops not checked out")
def test_runtime_crops_are_served_as_static_images(client):
    response = client.get("/crops/pos_0001.png")
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert client.get("/crops/missing.png").status_code == 404
