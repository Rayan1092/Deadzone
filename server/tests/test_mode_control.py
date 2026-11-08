"""The board's comparison control delegates to Rayan's robot-owned mode hook."""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
api = importlib.import_module("deadzone.app")


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_ROBOTS", "3")
    monkeypatch.delenv("DZ_MODE", raising=False)
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    with TestClient(api.app) as client:
        yield client, hub


@pytest.mark.parametrize("field", ["value", "mode"])
def test_mode_control_switches_all_robots_and_reset_restores_default(session, field):
    client, hub = session
    tick = hub.sim.tick_n
    result = client.post("/api/control", json={"action":"mode", field:"baseline"}).json()
    assert result["mode"] == "baseline" and not result["running"]
    assert {r.mode for r in hub.sim.robots.values()} == {"baseline"}
    assert hub.sim.tick_n == tick and not hub.sim.network.queues["CMD"]
    assert client.post("/api/control", json={"action":"reset"}).json()["mode"] == "deadzone"
    assert {r.mode for r in hub.sim.robots.values()} == {"deadzone"}


@pytest.mark.parametrize("field", ["value", "mode"])
def test_screen_control_echo_and_reconnect_hello_include_mode(session, field):
    client, hub = session
    with client.websocket_connect("/ws/screen") as screen:
        frames = [screen.receive_json() for _ in range(4)]
        assert frames[0]["data"]["mode"] == "deadzone"
        screen.send_json({"t":"control", "data":{"action":"mode", field:"baseline"}})
        message = screen.receive_json()
        assert message["t"] == "control" and message["data"]["mode"] == "baseline"
    with client.websocket_connect("/ws/screen") as screen:
        assert screen.receive_json()["data"]["mode"] == "baseline"
    assert {r.mode for r in hub.sim.robots.values()} == {"baseline"}


@pytest.mark.parametrize("value", [None, "teleop", 1, [], {}])
@pytest.mark.parametrize("field", ["value", "mode"])
def test_invalid_mode_never_partially_changes_robots(session, value, field):
    client, hub = session
    response = client.post("/api/control", json={"action":"mode", field:value})
    assert response.status_code == 422 and response.json()["detail"]["code"] == "invalid_mode"
    assert {r.mode for r in hub.sim.robots.values()} == {"deadzone"}


def test_mode_alias_conflicts_rejected_over_rest_and_screen_then_matching_aliases_work(session):
    client, hub = session
    with client.websocket_connect("/ws/screen") as screen:
        for _ in range(4):
            screen.receive_json()
        payload = {"action":"mode", "mode":"baseline", "value":"deadzone"}
        response = client.post("/api/control", json=payload)
        assert response.status_code == 422 and response.json()["detail"]["code"] == "invalid_mode"
        screen.send_json({"t":"control", "data":payload})
        error = screen.receive_json()
        assert error["t"] == "error" and error["data"]["code"] == "invalid_mode"
        assert {r.mode for r in hub.sim.robots.values()} == {"deadzone"}
        payload["value"] = "baseline"
        assert client.post("/api/control", json=payload).json()["mode"] == "baseline"
        assert screen.receive_json()["data"]["mode"] == "baseline"
        assert {r.mode for r in hub.sim.robots.values()} == {"baseline"}
