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


def test_no_go_only_and_cleared_drafts_sync_to_screen_and_both_phones(session):
    client, hub = session
    data = draft() | {"zones": [], "no_go": [{"id": "NG1", "poly": [[8, 8], [9, 8], [9, 9], [8, 9]],
                                              "reason": "Responder no-go area"}]}
    with client.websocket_connect("/ws/screen") as screen, \
            client.websocket_connect("/ws/phone?client=phone-a") as a, \
            client.websocket_connect("/ws/phone?client=phone-b") as b:
        for _ in range(4):
            screen.receive_json()
        hello, _ = initial(a)
        initial(b)
        data["plan_epoch"] = hello["plan_epoch"]
        for regions in (data["no_go"], []):
            data["no_go"] = regions
            assert client.post("/api/plan?check=false", json=data).json()["saved"]
            for viewer in (screen, a, b):
                message = viewer.receive_json()
                assert message["t"] == "plan_state"
                assert message["data"]["no_go"] == regions
                assert message["data"]["zones"] == []
                assert "plan_epoch" not in message["data"]
        # A plan without zones (no-go only, or cleared) is accepted and reaches every robot, which
        # keeps its current zone assignment (Rayan's P0, 2026-11-08; plan.py edited with authorization).
        for path in ("/api/plan/check", "/api/dispatch"):
            response = client.post(path, json={"plan_id": "P-1", "plan_epoch": hello["plan_epoch"]})
            assert response.status_code == 200, response.json()
            assert response.json()["ok"]
        assert {b["dst"] for b in hub.sim.network.queues["CMD"]} == set(hub.sim.robot_specs)


def test_dispatch_notifies_all_phones_and_reconnect_retains_immutability(session):
    client, hub = session
    assert client.post("/api/plan?check=false", json=draft()).json()["saved"]
    with client.websocket_connect("/ws/phone?client=phone-a") as a, \
            client.websocket_connect("/ws/phone?client=phone-b") as b:
        hello, _ = initial(a)
        initial(b)
        ref = {"plan_id": "P-1", "plan_epoch": hello["plan_epoch"]}
        result = client.post("/api/plan/check", json=ref)
        assert result.json()["ok"]
        for phone in (a, b):
            assert phone.receive_json()["t"] == "safety"
        assert client.post("/api/dispatch", json=ref).json()["ok"]
        for phone in (a, b):
            assert phone.receive_json()["t"] == "plan_state"
            assert phone.receive_json()["data"] == {"kind": "plan_dispatched", "plan_id": "P-1"}
    with client.websocket_connect("/ws/phone?client=phone-b") as phone:
        restored, _ = initial(phone)
        assert restored["dispatched_plan_ids"] == ["P-1"]
        assert restored["plan_epoch"] == hello["plan_epoch"]


def test_stale_phone_requests_cannot_write_check_or_dispatch_into_reset(session):
    client, hub = session
    with client.websocket_connect("/ws/phone?client=phone-a") as phone:
        old, _ = initial(phone)
        assert client.post("/api/control", json={"action": "reset"}).status_code == 200
        new, _ = initial(phone)
        assert new["plan_epoch"] != old["plan_epoch"]
        assert not new["dispatched_plan_ids"]
    assert client.post("/api/plan?check=false", json=draft()).json()["saved"]
    stale = {"plan_epoch": old["plan_epoch"]}
    for path, body in (("/api/plan?check=false", draft() | stale),
                       ("/api/plan/check", {"plan_id": "P-1"} | stale),
                       ("/api/dispatch", {"plan_id": "P-1"} | stale)):
        response = client.post(path, json=body)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "plan_reset"
    assert not hub.sim.network.queues["CMD"]


def test_relay_join_controls_and_disconnect_update_paused_screen_without_time_step(session):
    client, hub = session
    with client.websocket_connect("/ws/screen") as screen:
        for _ in range(4):
            screen.receive_json()
        tick = hub.sim.tick_n
        with client.websocket_connect("/ws/phone?client=relay-a&role=relay") as phone:
            initial(phone)
            relay = phone.receive_json()["data"]
            joined = screen.receive_json()
            assert joined["t"] == "tick"
            assert joined["data"]["reality"]["relays"][0]["id"] == relay["id"]
            for message, field, value in (
                ({"t": "relay_power", "data": {"on": False}}, "on", False),
                ({"t": "relay_place", "data": {"pos": [8, 15]}}, "pos", [8, 15]),
                ({"t": "relay_power", "data": {"on": True}}, "on", True),
            ):
                phone.send_json(message)
                assert phone.receive_json()["t"] == "relay_state"
                update = screen.receive_json()
                assert update["data"]["reality"]["relays"][0][field] == value
                assert hub.sim.tick_n == tick and not hub.running
        gone = screen.receive_json()
        assert not gone["data"]["reality"]["relays"][0]["on"]
        assert hub.sim.tick_n == tick


def test_dispatch_uses_latest_delivered_battery_not_old_approval(session):
    client, hub = session
    assert client.post("/api/plan", json=draft()).json()["ok"]
    hub.sim.post.robots["R1"]["battery_pct"] = 1
    response = client.post("/api/dispatch", json={"plan_id": "P-1"})
    assert response.status_code == 200 and not response.json()["ok"]
    assert response.json()["violations"][0]["rule"] == "battery_reserve"
    assert not hub.sim.network.queues["CMD"]


def test_quiet_preload_sends_only_plan_state_then_explicit_check_and_dispatch_reject(session):
    client, hub = session
    # A deliberately unsafe draft must save quietly without granting approval.
    hub.sim.post.robots["R1"]["battery_pct"] = 1
    hub.sim.drain_events()  # startup link/delivery events are unrelated to preload
    with client.websocket_connect("/ws/screen") as screen:
        assert [screen.receive_json()["t"] for _ in range(4)] == ["hello", "maps", "tick", "plan_state"]
        with client.websocket_connect("/ws/phone?client=phone-a") as phone:
            initial(phone)
            response = client.post("/api/plan?check=false", json=draft())
            assert response.json() == {"saved": True, "plan_id": "P-1", "checked": False}
            assert screen.receive_json()["t"] == phone.receive_json()["t"] == "plan_state"
            # Following sentinel frames prove no safety/event frames were queued.
            client.portal.call(hub.broadcast_tick, True)
            assert screen.receive_json()["t"] == "tick"
            assert screen.receive_json()["t"] == "maps"
            assert phone.receive_json()["t"] == "cmd_view"
            phone.send_json({"t": "plan_submit", "data": {"plan_id": "P-1"}})
            result = phone.receive_json()
            assert result["t"] == "safety" and not result["data"]["ok"]
            assert screen.receive_json()["data"]["kind"] == "safety_reject"
    assert not client.post("/api/dispatch", json={"plan_id": "P-1"}).json()["ok"]
    assert not hub.sim.network.queues["CMD"]


def test_quiet_save_still_validates_geometry_and_dispatched_id(session):
    client, hub = session
    data = draft()
    data["zones"][0]["poly"][0][0] = -1
    assert client.post("/api/plan?check=false", json=data).status_code == 422
    assert hub.plans.current() is None
    assert client.post("/api/plan?check=false", json=draft()).json()["saved"]
    assert client.post("/api/dispatch", json={"plan_id": "P-1"}).json()["ok"]
    data = draft() | {"lost_link_budget_s": 90}
    assert client.post("/api/plan?check=false", json=data).status_code == 409


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
    for path in ("/ws/screen", "/ws/phone?role=spectator"):
        with client.websocket_connect(path) as ws:
            hello = ws.receive_json()["data"]
            assert hello["public_url"] == "https://deadzone.example"
            assert hello["phone_url"] == client.get("/api/join").json()["url"]
    monkeypatch.delenv("DZ_PUBLIC_URL")
    assert client.get("/api/join", headers={"Host": "192.168.1.8:5173"}).json() == {
        "url": "http://192.168.1.8:5173/phone"}
    monkeypatch.setattr(api, "lan_ipv4", lambda *args: "192.168.1.9")
    assert client.get("/api/join", headers={"Host": "localhost:5173"}).json() == {
        "url": "http://192.168.1.9:5173/phone"}


def test_hello_does_not_advertise_unset_or_invalid_public_origin(session, monkeypatch):
    _, hub = session
    assert "phone_url" not in json.loads(hub.hello())["data"]
    for invalid in ("ftp://wrong", "https://person:password@example.com", "https://example.com/path"):
        monkeypatch.setenv("DZ_PUBLIC_URL", invalid)
        assert "phone_url" not in json.loads(hub.hello())["data"]
        assert "public_url" not in hub.phone_hello("viewer", "spectator")


def test_join_without_lan_address_returns_actionable_error(session, monkeypatch):
    client, _ = session
    monkeypatch.setattr(api, "lan_ipv4", lambda *args: None)
    assert client.get("/api/join", headers={"Host": "localhost:5173"}).status_code == 503
    for url in ("ftp://wrong", "http://localhost:bad", "http://[broken", "https://example.com/prefix"):
        monkeypatch.setenv("DZ_PUBLIC_URL", url)
        assert client.get("/api/join").status_code == 503


@pytest.mark.parametrize("host", ["localhost", "127.0.0.2", "0.0.0.0", "[::1]", "laptop.local"])
def test_join_replaces_local_hosts_even_when_configured(session, monkeypatch, host):
    client, _ = session
    monkeypatch.setenv("DZ_PUBLIC_URL", f"http://{host}:8000")
    monkeypatch.setattr(api, "lan_ipv4", lambda *args: "10.84.29.47")
    assert client.get("/api/join").json() == {"url": "http://10.84.29.47:8000/phone"}


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
