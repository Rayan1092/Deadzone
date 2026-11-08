"""Phone robot buttons (hold, resume, return home) must work whenever control leases are on: they
are built and safety-checked locally and never use the voice services. They used to also need
DZ_VOICE=1, so with leases on and voice off the phone showed the buttons and every press except
resume was refused (feature_disabled). Spoken input still needs DZ_VOICE."""
import importlib
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    api = importlib.import_module("deadzone.app")
    monkeypatch.setenv("DZ_ROBOTS", "1")
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_CONTROL_LEASES", "1")
    monkeypatch.setenv("DZ_VOICE", "0")
    monkeypatch.setenv("DETECTOR", "sim")
    monkeypatch.setattr(api, "hub", api.Hub())
    with TestClient(api.app) as c:
        yield c, api.hub


@contextmanager
def phone(client):
    with client.websocket_connect("/ws/phone?client=unit1&role=planner") as ws:
        hello = ws.receive_json()["data"]
        yield hello["controller_token"]


@pytest.mark.parametrize("action", ["hold", "resume", "return_home"])
def test_phone_buttons_work_with_leases_and_no_voice(client, action):
    c, hub = client
    with phone(c) as token:
        h = {"X-Controller-Token": token}
        assert c.post("/api/leases/claim", headers=h, json={"robot": "R1", "name": "Field unit 1"}).status_code == 200
        res = c.post("/api/robot-command", headers=h, json={"robot": "R1", "action": action, "request_id": f"t-{action}"})
        assert res.status_code == 200, res.json()
        assert res.json()["intent_source"] == "manual"
        assert any(b["kind"] == "command" and b["payload"]["source"] == "phone" for b in hub.sim.network.queues["CMD"])


def test_spoken_input_still_needs_voice(client):
    c, _ = client
    with phone(c) as token:
        h = {"X-Controller-Token": token}
        assert c.post("/api/leases/claim", headers=h, json={"robot": "R1", "name": "Field unit 1"}).status_code == 200
        res = c.post("/api/voice", headers=h, json={"robot": "R1", "text": "hold"})
        assert res.status_code == 409 and res.json()["detail"]["code"] == "feature_disabled"
