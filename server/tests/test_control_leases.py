"""Exclusive leases across real REST/WS command paths, including spoofed identities."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deadzone.command.leases import LeaseTable
from deadzone.command.plan import PlanError
api = importlib.import_module("deadzone.app")


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("DZ_CONTROL_LEASES", "1")
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_ROBOTS", "3")
    monkeypatch.setenv("DZ_VOICE", "1")
    monkeypatch.setenv("DZ_PRESENTER_TOKEN", "test-presenter-only")
    hub = api.Hub()
    now = [0.0]
    hub.leases.clock = lambda: now[0]
    monkeypatch.setattr(api, "hub", hub)
    with TestClient(api.app) as client:
        yield client, hub, now


@contextmanager
def phone(client, name="judge", role="planner"):
    with client.websocket_connect(f"/ws/phone?client={name}&role={role}") as ws:
        hello = ws.receive_json()["data"]
        assert ws.receive_json()["t"] == "cmd_view"
        yield ws, hello.get("controller_token")


def headers(token):
    return {"X-Controller-Token": token} if token else {}


def change(client, action, token, robot="R1", **kw):
    return client.post(f"/api/leases/{action}", headers=headers(token), json={"robot": robot, **kw})


def test_exclusive_claim_and_private_token_with_same_client_id(session):
    client, hub, _ = session
    with phone(client) as (a, ta), phone(client) as (b, tb):
        assert ta != tb
        first = change(client, "claim", ta, name="Alice")
        assert first.status_code == 200
        for ws in (a, b):
            frame = ws.receive_json()
            assert frame["t"] == "leases"
            assert ta not in json.dumps(frame) and tb not in json.dumps(frame)
            assert frame["data"]["robots"][0]["controller"]["name"] == "Alice"
        assert change(client, "claim", tb, name="Bob").status_code == 409
        assert change(client, "release", tb).status_code == 403
        assert change(client, "heartbeat", tb).status_code == 403
        assert change(client, "heartbeat", ta).status_code == 200
        assert change(client, "release", ta).status_code == 200
        assert change(client, "claim", tb, name="Bob").status_code == 200
        assert hub.leases.leases["R1"]["token"] == tb


def test_simultaneous_claim_has_exactly_one_winner(session):
    client, hub, _ = session
    with phone(client, "a") as (_, a), phone(client, "b") as (_, b):
        with ThreadPoolExecutor(2) as pool:
            replies = list(pool.map(lambda t: change(client, "claim", t, name="judge"), (a, b)))
        assert sorted(r.status_code for r in replies) == [200, 409]
        assert len(hub.leases.leases) == 1


def test_expiry_is_wall_clock_and_heartbeat_cannot_resurrect(session):
    client, hub, now = session
    with phone(client) as (_, token):
        change(client, "claim", token, name="Judge").raise_for_status()
        now[0] = 10
        change(client, "heartbeat", token).raise_for_status()
        now[0] = 24.9
        assert client.get("/api/leases").json()["robots"][0]["controller"]
        assert not hub.running
        now[0] = 25
        state = client.get("/api/leases").json()
        assert state["robots"][0]["controller"] is None
        assert change(client, "heartbeat", token).status_code == 403
        assert hub.sim.time == .1


def test_override_only_frees_without_disconnecting_or_transferring(session):
    client, hub, _ = session
    with phone(client) as (ws, token):
        change(client, "claim", token, name="Judge").raise_for_status()
        for wrong in ("wrong", "not-ascii-\u00e9"):
            assert client.post("/api/leases/override", json={"robot":"R1", "presenter_token":wrong}).status_code == 403
        assert hub.leases.leases
        response = client.post("/api/leases/override", json={"robot":"R1", "presenter_token":"test-presenter-only"})
        assert response.status_code == 200 and response.json()["robots"][0]["controller"] is None
        assert token in hub.leases.controllers  # still connected, explicit reclaim required
        assert change(client, "heartbeat", token).status_code == 403
        assert change(client, "claim", token, name="Judge").status_code == 200


def test_disconnect_releases_only_that_connection_and_reset_clears(session):
    client, hub, _ = session
    with phone(client, "same") as (_, a):
        with phone(client, "same") as (_, b):
            change(client, "claim", a, "R1", name="A").raise_for_status()
            change(client, "claim", b, "R2", name="B").raise_for_status()
        deadline = time.monotonic() + 2
        while client.get("/api/leases").json()["robots"][1]["controller"] is not None:
            assert time.monotonic() < deadline
        assert hub.leases.leases["R1"]["token"] == a
        revision = hub.leases.revision
        client.post("/api/control", json={"action":"reset"}).raise_for_status()
        assert not hub.leases.leases and hub.leases.revision > revision
        assert a in hub.leases.controllers
        assert change(client, "heartbeat", a).status_code == 403


def test_manual_and_voice_paths_require_holder_and_mode_is_atomic(session):
    client, hub, _ = session
    with phone(client, "a") as (_, a), phone(client, "b") as (_, b):
        change(client, "claim", a, name="A").raise_for_status()
        calls = [
            ("/api/robot-command", {"robot":"R1", "action":"resume"}),
            ("/api/control", {"action":"director", "value":{"do":"resume", "robot":"R1"}}),
            ("/api/voice", {"robot":"R1", "text":"resume"}),
        ]
        for token in (None, "forged", b):
            for path, body in calls:
                assert client.post(path, headers=headers(token), json=body).status_code == 403
        assert not hub.sim.network.queues["CMD"]
        assert client.post("/api/voice", headers=headers(a), json=calls[2][1]).status_code == 501
        assert not hub.sim.network.queues["CMD"]  # no invented voice response/command
        assert client.post(calls[0][0], headers=headers(a), json=calls[0][1]).status_code == 200
        assert len(hub.sim.network.queues["CMD"]) == 1
        assert client.post("/api/control", headers=headers(a), json={"action":"mode","mode":"baseline"}).status_code == 403
        assert {r.mode for r in hub.sim.robots.values()} == {"deadzone"}
        for robot in ("R2", "R3"):
            change(client, "claim", a, robot, name="A").raise_for_status()
        assert client.post("/api/control", headers=headers(a), json={"action":"mode","value":"baseline"}).status_code == 200


def test_shared_planning_unrestricted_but_spectators_cannot_claim(session):
    client, hub, _ = session
    with phone(client, role="spectator") as (_, token):
        assert token is None
        assert change(client, "claim", token, name="Spectator").status_code == 403
        plan = {"plan_id":"SHARED", "author":"a", "zones":[
            {"id":"Z1", "robot":"R1", "poly":[[3,14],[6,14],[6,16],[3,16]]}]}
        assert client.post("/api/plan?check=false", json=plan).status_code == 200
        assert client.post("/api/dispatch", json={"plan_id":"SHARED"}).status_code == 200


def test_screen_tokens_and_resume_bypass_rejected_and_override_auth(session):
    client, hub, _ = session
    with client.websocket_connect("/ws/screen") as screen:
        token = screen.receive_json()["data"]["controller_token"]
        for _ in range(3):
            screen.receive_json()
        screen.send_json({"t":"control", "data":{"action":"director", "value":{"do":"resume","robot":"R1"}}})
        assert screen.receive_json()["t"] == "error"
        change(client, "claim", token, name="Presenter").raise_for_status()
        assert screen.receive_json()["t"] == "leases"
        screen.send_json({"t":"control", "data":{"controller_token":token,"action":"director", "value":{"do":"resume","robot":"R1"}}})
        assert screen.receive_json()["t"] == "control"
        screen.send_json({"t":"lease_override", "data":{"robot":"R1","presenter_token":"test-presenter-only"}})
        assert screen.receive_json()["data"]["robots"][0]["controller"] is None
        assert token not in hub.hello() and "test-presenter-only" not in hub.hello()


def test_voice_flag_implies_enforcement_and_feature_off_legacy_unchanged(monkeypatch):
    monkeypatch.delenv("DZ_CONTROL_LEASES", raising=False)
    monkeypatch.setenv("DZ_VOICE", "1")
    hub = api.Hub()
    with pytest.raises(PlanError):
        asyncio.run(hub.control("director", {"do":"resume","robot":"R1"}))
    monkeypatch.setenv("DZ_VOICE", "0")
    asyncio.run(hub.control("director", {"do":"resume","robot":"R1"}))
    assert len(hub.sim.network.queues["CMD"]) == 1


def test_malformed_screen_credentials_and_mic_feature_gate(session, monkeypatch):
    client, _, _ = session
    assert client.get("/mic-check").status_code == 200
    with client.websocket_connect("/ws/screen") as screen:
        for _ in range(4):
            screen.receive_json()
        for token in (["forged"], {"forged":True}, 7):
            screen.send_json({"t":"control", "data":{"action":"director", "value":{"do":"resume","robot":"R1"}, "controller_token":token}})
            assert screen.receive_json()["data"]["code"] == "invalid_controller"
    monkeypatch.setenv("DZ_CONTROL_LEASES", "0")
    monkeypatch.setenv("DZ_VOICE", "0")
    assert client.get("/mic-check").status_code == 404
    assert change(client, "claim", None, name="off").status_code == 409
    assert client.post("/api/robot-command", json={"robot":"R1","action":"resume"}).status_code == 409


def test_reset_waits_for_lease_transaction_before_replacing_world(monkeypatch):
    monkeypatch.setenv("DZ_CONTROL_LEASES", "1")
    hub = api.Hub()
    before = hub.sim.post

    async def run():
        await hub.lease_lock.acquire()
        task = asyncio.create_task(hub.reset())
        await asyncio.sleep(0)
        unchanged = hub.sim.post is before
        hub.lease_lock.release()
        await asyncio.wait_for(task, 2)
        assert unchanged  # no new world while an old lease transaction is in flight
        assert hub.sim.post is not before

    asyncio.run(run())
