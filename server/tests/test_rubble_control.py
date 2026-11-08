"""The R key contract (Rayan, 2026-11-08): {t:"control", data:{action:"rubble", robot:"R2"}}; a missing
robot means R1. The rubble lands ahead of that robot (on its path with DZ_SMART_RUBBLE=1)."""
import importlib
import math
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
    monkeypatch.setenv("DETECTOR", "sim")
    monkeypatch.setenv("DZ_SMART_RUBBLE", "1")
    monkeypatch.setenv("DZ_COLLAPSE_AT", "0")
    monkeypatch.setattr(api, "hub", api.Hub())
    with TestClient(api.app) as client:
        hub = api.hub
        while hub.sim.time < 20.0:          # robots spread out with planned paths
            hub.sim.tick()
        hub.sim.drain_events()
        presses = []
        original = hub.sim.press_rubble

        def record(*args, **kwargs):
            placed = original(*args, **kwargs)
            presses.append(placed)
            return placed
        monkeypatch.setattr(hub.sim, "press_rubble", record)
        yield client, hub, presses


@pytest.mark.parametrize("robot", ["R3", "R2"])
def test_websocket_rubble_targets_the_named_robot(session, robot):
    client, hub, presses = session
    with client.websocket_connect("/ws/screen") as ws:
        ws.send_json({"t": "control", "data": {"action": "rubble", "robot": robot}})
        for _ in range(50):                  # the server always ends a control with its echo
            if ws.receive_json()["t"] == "control" and presses:
                break
    assert len(presses) == 1
    placed = presses[0]
    assert placed["robot"] == robot and placed["source"] == "key"
    assert math.dist(placed["at"], hub.sim.robots[robot].pose[:2]) <= 6.5, "dropped ahead of the named robot"
    rubble = [rb for rb in hub.sim.fp.data["rubble"] if rb.get("dynamic")]
    assert len(rubble) == 1


def test_rest_rubble_without_robot_means_r1_and_unknown_robot_is_404(session):
    client, hub, presses = session
    response = client.post("/api/control", json={"action": "rubble"})
    assert response.status_code == 200 and response.json()["ok"]
    assert presses[-1]["robot"] == "R1"
    response = client.post("/api/control", json={"action": "rubble", "robot": "R3"})
    assert response.status_code == 200 and presses[-1]["robot"] == "R3"
    response = client.post("/api/control", json={"action": "rubble", "robot": "R9"})
    assert response.status_code == 404
    assert len(presses) == 2
