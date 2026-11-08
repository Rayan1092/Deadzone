"""Presentation changes must never alter codes, IDs, decisions or stored data."""
from copy import deepcopy
import importlib
import json

from fastapi.testclient import TestClient
import pytest

from deadzone.public_text import ERRORS, FEATURES, PublicText


@pytest.fixture
def display():
    return PublicText({"R1": "Scout 1", "R10": "Scout 10"},
                      [{"id": "S2", "name": "Loading office"}],
                      {"P-test": {"zones": [{"id": "ZNE"}], "no_go": [{"id": "NG1"}]}})


@pytest.mark.parametrize("code", sorted(ERRORS))
def test_public_errors_preserve_machine_code_and_remove_implementation_details(display, code):
    data = {"code": code, "msg": "internal R1 judge-phone request_id"}
    result = display.payload(data)
    assert result["code"] == code
    assert result["msg"][0].isupper()
    assert not any(word in result["msg"] for word in ("DZ_", "request_id", "judge-phone", "R1", "WebSocket"))
    assert data["msg"] == "internal R1 judge-phone request_id"


@pytest.mark.parametrize("flag", sorted(FEATURES))
def test_disabled_features_explain_availability_without_setup_instructions(display, flag):
    message = display.payload({"code": "feature_disabled", "msg": f"Enable {flag}=1 for setup"})
    assert message["msg"] == FEATURES[flag]
    assert message["code"] == "feature_disabled"


@pytest.mark.parametrize("rule,value,limit", [("comms_plan", False, True), ("no_go_overlap", True, False),
    ("zone_unreachable", False, True), ("battery_reserve", None, 20), ("battery_reserve", 9.3, 20),
    ("capability", "stairs", False)])
def test_safety_only_changes_the_display_message(display, rule, value, limit):
    item = {"robot": "R1", "zone": "ZNE", "rule": rule, "value": value, "limit": limit,
            "msg": "R1 Zone ZNE lost_link_ok"}
    original = deepcopy(item)
    result = display.payload({"ok": False, "plan_id": "P-test", "violations": [item]})
    transformed = result["violations"][0]
    assert {k: v for k, v in transformed.items() if k != "msg"} == {k: v for k, v in original.items() if k != "msg"}
    assert "ZNE" not in transformed["msg"] and "lost_link_ok" not in transformed["msg"] and "R1" not in transformed["msg"]
    assert item == original and not result["ok"]


def test_rooms_survivors_and_robot_prefixes_are_unambiguous(display):
    assert display.message("Finished searching S2.") == "Finished searching Loading office."
    assert display.message("S2 was found by R10; R1 is holding.") == "Survivor 2 was found by Scout 10; Scout 1 is holding."
    assert display.message("heading to ZNE", plan_id="P-test") == "Heading to Search area 1"


def test_geometry_frames_codes_and_reason_enums_are_untouched(display):
    geometry = {"name": "Original", "rooms": [{"id": "S2"}]}
    frame = {"jpeg": "same-bytes", "t": 1}
    data = {"floorplan": geometry, "phone_frame": frame, "map": "same-base64", "path": [[0, 1], [2, 3]],
            "cmd_id": "V-R1-123", "reason": "no_route", "state": "WAITING", "plan_id": "P-test"}
    result = display.payload(data)
    assert result == data
    assert result["floorplan"] is geometry and result["phone_frame"] is frame and result["path"] is data["path"]


@pytest.fixture
def session(monkeypatch):
    api = importlib.import_module("deadzone.app")
    monkeypatch.setenv("DZ_ROBOTS", "1")
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_AFTERSHOCK", "0")
    monkeypatch.setenv("DZ_CONTROL_LEASES", "0")
    monkeypatch.setenv("DZ_VOICE", "0")
    monkeypatch.setattr(api, "hub", api.Hub())
    with TestClient(api.app) as client:
        yield client, api.hub


def test_rest_and_screen_error_have_identical_public_copy_and_codes(session):
    client, _ = session
    control = {"action": "director", "value": {"do": "aftershock"}}
    rest = client.post("/api/control", json=control).json()["detail"]
    with client.websocket_connect("/ws/screen") as ws:
        for _ in range(4): ws.receive_json()
        ws.send_json({"t": "control", "data": control})
        event = ws.receive_json()
    assert rest == event["data"] == {"code": "feature_disabled", "msg": FEATURES["DZ_AFTERSHOCK"]}
    assert set(event) == {"t", "seq", "time", "data"}


def test_real_safety_rest_and_phone_messages_match_without_changing_the_saved_plan(session):
    client, hub = session
    hub.sim.post.robots["R1"]["battery_pct"] = 1
    plan = {"plan_id": "P-test", "author": "phone-a", "zones": [{"id": "ZNE", "robot": "R1", "poly": [[3, 14], [6, 14], [6, 16], [3, 16]]}]}
    with client.websocket_connect("/ws/phone") as ws:
        ws.receive_json(); ws.receive_json()
        response = client.post("/api/plan", json=plan)
        assert response.status_code == 200
        result = response.json()
        assert ws.receive_json()["t"] == "plan_state"
        assert ws.receive_json()["data"] == result
    assert result["violations"]
    assert all("ZNE" not in v["msg"] and "lost_link_ok" not in v["msg"] for v in result["violations"])
    assert hub.plans.current()["zones"][0]["id"] == "ZNE"
    assert hub.plans.current()["zones"][0]["robot"] == "R1"


def test_rest_refusals_validation_join_and_acks_do_not_expose_internal_names(session, monkeypatch):
    client, hub = session
    monkeypatch.setenv("DZ_PUBLIC_URL", "ftp://invalid")
    assert "DZ_" not in client.get("/api/join").json()["detail"]
    error = client.post("/api/dispatch", json={"plan_id": "missing-secret-id"}).json()["detail"]
    assert error["code"] == "plan_not_found" and "missing-secret-id" not in error["msg"]
    invalid = client.post("/api/dispatch", json={}).json()["detail"]
    assert invalid["code"] == "invalid_request" and invalid["issues"][0]["loc"] == ["body", "plan_id"]
    ack = {"robot": "R1", "cmd_id": "V-internal", "reason": None, "say": "R1 finished searching S2."}
    public = json.loads(hub.envelope("cmd_view", {"command_acks": [ack]}))["data"]["command_acks"][0]
    assert public["say"] == "Scout 1 finished searching " + hub.public_text.rooms["S2"] + "."
    assert public["cmd_id"] == ack["cmd_id"] and ack["say"] == "R1 finished searching S2."
