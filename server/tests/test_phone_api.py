"""REST and WebSocket contract for Person 3's phone frontend."""
import base64
import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

api = importlib.import_module("deadzone.app")


def draft():
    return {"plan_id": "P-1", "author": "phone-a", "zones": [
        {"id": "Z1", "robot": "R1", "poly": [[3, 14], [6, 14], [6, 16], [3, 16]]}]}


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_ROBOTS", "1")
    monkeypatch.delenv("DZ_PUBLIC_URL", raising=False)
    monkeypatch.setattr(api, "hub", api.Hub())
    with TestClient(api.app) as client:
        yield client, api.hub


def initial(ws):
    hello, view = ws.receive_json(), ws.receive_json()
    assert hello["t"] == "hello" and view["t"] == "cmd_view"
    return hello["data"], view["data"]


def test_phone_hello_and_rest_floorplan_never_reveal_hidden_survivors_or_rubble(session):
    client, hub = session
    hub.sim.robots["R1"].map.grid[100, 100] = 1
    assert hub.sim.post.map[100, 100] == 0
    with client.websocket_connect("/ws/phone?client=phone-a&role=planner") as ws:
        hello, view = initial(ws)
        assert "survivors" not in hello["floorplan"]
        assert "rubble" not in hello["floorplan"]
        assert "reality" not in view
        assert view["survivors"] == []
        assert base64.b64decode(view["map"]) == hub.sim.post.map.tobytes()
        assert hello["client"] == "phone-a" and hello["plan"] is None
    data = client.get("/api/floorplan").json()
    assert "survivors" not in data and "rubble" not in data


def test_rest_save_check_dispatch_and_duplicate_dispatch(session):
    client, hub = session
    response = client.post("/api/plan", json=draft())
    assert response.status_code == 200 and response.json()["ok"]
    assert not hub.sim.network.queues["CMD"]
    assert client.post("/api/dispatch", json={"plan_id": "P-1"}).json()["ok"]
    assert client.post("/api/dispatch", json={"plan_id": "P-1"}).json()["ok"]
    assert len(hub.sim.network.queues["CMD"]) == 1
    changed = draft()
    changed["lost_link_budget_s"] = 90
    assert client.post("/api/plan", json=changed).status_code == 409
    assert client.post("/api/dispatch", json={"plan_id": "missing"}).status_code == 404


def test_dispatch_uses_latest_delivered_battery_not_old_approval(session):
    client, hub = session
    assert client.post("/api/plan", json=draft()).json()["ok"]
    hub.sim.post.robots["R1"]["battery_pct"] = 1
    response = client.post("/api/dispatch", json={"plan_id": "P-1"})
    assert response.status_code == 200 and not response.json()["ok"]
    assert response.json()["violations"][0]["rule"] == "battery_reserve"
    assert not hub.sim.network.queues["CMD"]


def test_two_planner_phones_share_draft_and_receive_safety_result(session):
    client, hub = session
    with client.websocket_connect("/ws/phone?client=phone-a") as a:
        initial(a)
        with client.websocket_connect("/ws/phone?client=phone-b") as b:
            initial(b)
            data = draft()
            data["author"] = "spoofed"
            a.send_json({"t": "plan_edit", "data": data})
            for ws in (a, b):
                message = ws.receive_json()
                assert message["t"] == "plan_state"
                assert message["data"]["author"] == "phone-a"
            a.send_json({"t": "plan_submit", "data": {"plan_id": "P-1"}})
            for ws in (a, b):
                message = ws.receive_json()
                assert message["t"] == "safety" and message["data"]["ok"]
        assert len(hub.phones) == 1
    assert not hub.phones and not hub.phone_sessions


def test_reconnect_gets_current_draft_and_reset_clears_plans_and_dispatch(session):
    client, hub = session
    assert client.post("/api/plan", json=draft()).json()["ok"]
    assert client.post("/api/dispatch", json={"plan_id": "P-1"}).json()["ok"]
    with client.websocket_connect("/ws/phone?client=phone-a") as ws:
        hello, _ = initial(ws)
        assert hello["plan"]["plan_id"] == "P-1"
        assert client.post("/api/control", json={"action": "reset"}).status_code == 200
        hello, view = initial(ws)
        assert hello["plan"] is None and [r["id"] for r in view["robots"]] == ["R1"]
        assert hub.sim.tick_n == 1 and not hub.running
        assert not hub.sim.network.queues["CMD"]
        assert not hub.plans.dispatched


def test_invalid_websocket_messages_return_errors_without_closing_session(session):
    client, _ = session
    with client.websocket_connect("/ws/phone") as ws:
        hello, _ = initial(ws)
        assert hello["client"].startswith("phone-")
        for raw in ["{", "[]", '{"t":"plan_edit","data":{}}',
                    '{"t":"plan_submit","data":{"plan_id":"missing"}}',
                    '{"t":"unsupported","data":{}}']:
            ws.send_text(raw)
            assert ws.receive_json()["t"] == "error"
        ws.send_json({"t": "plan_edit", "data": draft()})
        assert ws.receive_json()["t"] == "plan_state"


def test_relay_role_cannot_edit_planner_state(session):
    client, hub = session
    with client.websocket_connect("/ws/phone?role=relay") as ws:
        hello, _ = initial(ws)
        assert hello["relay_id"] in hub.sim.relays
        assert ws.receive_json()["t"] == "relay_state"
        ws.send_json({"t": "plan_edit", "data": draft()})
        assert ws.receive_json()["data"]["code"] == "read_only_role"
        assert hub.plans.current() is None


def test_invalid_and_nonfinite_rest_geometry_is_422_not_server_error(session):
    client, hub = session
    data = draft()
    data["zones"][0]["poly"][0][0] = float("nan")
    response = client.post("/api/plan", content=json.dumps(data), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "NaN" not in response.text
    data = draft()
    data["zones"][0]["poly"][0][0] = -1
    assert client.post("/api/plan", json=data).status_code == 422
    assert hub.plans.current() is None


def test_join_url_uses_configured_public_frontend_or_request_lan_host(session, monkeypatch):
    client, _ = session
    monkeypatch.setenv("DZ_PUBLIC_URL", "https://deadzone.example/")
    assert client.get("/api/join").json() == {"url": "https://deadzone.example/phone"}
    monkeypatch.delenv("DZ_PUBLIC_URL")
    assert client.get("/api/join", headers={"Host": "192.168.1.8:5173"}).json() == {
        "url": "http://192.168.1.8:5173/phone"}
    monkeypatch.setattr(api.socket, "gethostbyname_ex", lambda _: ("laptop", [], ["192.168.1.9"]))
    assert client.get("/api/join", headers={"Host": "localhost:5173"}).json() == {
        "url": "http://192.168.1.9:5173/phone"}


def test_join_without_lan_address_returns_actionable_error(session, monkeypatch):
    client, _ = session
    monkeypatch.setattr(api.socket, "gethostbyname_ex", lambda _: ("laptop", [], ["127.0.0.1"]))
    assert client.get("/api/join", headers={"Host": "localhost:5173"}).status_code == 503
    for url in ("ftp://wrong", "http://localhost:bad", "http://[broken", "https://example.com/prefix"):
        monkeypatch.setenv("DZ_PUBLIC_URL", url)
        assert client.get("/api/join").status_code == 503


@pytest.mark.parametrize("query", ["role=admin", "client=bad%20name", "client="])
def test_invalid_phone_identity_or_role_does_not_register_a_session(session, query):
    client, hub = session
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/phone?" + query):
            pass
    assert not hub.phones


def test_periodic_phone_view_contains_command_map_and_no_unreported_findings(session):
    client, hub = session
    with client.websocket_connect("/ws/phone") as ws:
        initial(ws)
        hub.sim.robots["R1"].found["S1"] = {"id": "S1", "pos": [37.5, 26], "by": "R1", "t": 0.1}
        for _ in range(4):
            hub.sim.tick()
        client.portal.call(hub.broadcast_tick)
        message = ws.receive_json()
        assert message["t"] == "cmd_view"
        assert message["data"]["survivors"] == []
        assert base64.b64decode(message["data"]["map"]) == hub.sim.post.map.tobytes()
        assert "reality" not in message["data"]


def test_phone_route_serves_built_spa_entry(session, monkeypatch, tmp_path):
    client, _ = session
    monkeypatch.setattr(api, "WEB_DIST", tmp_path)
    assert client.get("/phone").status_code == 503
    (tmp_path / "index.html").write_text("<html>Phone frontend</html>", encoding="utf-8")
    for path in ("/phone", "/phone/"):
        response = client.get(path)
        assert response.status_code == 200 and "Phone frontend" in response.text
