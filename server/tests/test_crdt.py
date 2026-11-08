"""Offline authors replay in either order; invalid merged drafts never dispatch."""
import importlib
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
api = importlib.import_module("deadzone.app")


def plan():
    return {"plan_id": "CO-1", "author": "phone-a", "zones": [
        {"id": "Z1", "robot": "R1", "poly": [[3,14],[6,14],[6,16],[3,16]]},
        {"id": "Z2", "robot": "R1", "poly": [[7,14],[9,14],[9,16],[7,16]]}]}


def op(client, target, field, value, counter=1):
    return {"client": client, "counter": counter, "target": target, "field": field, "value": value}


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_CRDT", "1")
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    with TestClient(api.app) as client:
        yield client, hub


def seed(client):
    response = client.put("/api/plan-sync", json=plan())
    assert response.status_code == 200 and response.json()["valid"]
    return response.json()["epoch"]


def merge(client, epoch, ops):
    return client.post("/api/plan-sync", json={"epoch": epoch, "plan_id": "CO-1", "ops": ops})


def state(client):
    return client.get("/api/plan-sync", params={"plan_id": "CO-1"}).json()


def test_two_offline_authors_reconnect_in_both_orders_and_replay_duplicates(session):
    client, _ = session
    edits = [[op("phone-a", "zone:Z1", "priority", 2)],
             [op("phone-b", "plan", "lost_link_budget_s", 120), op("phone-b", "zone:Z2", "comms", "lost_link_ok")]]
    results = []
    for order in (edits, list(reversed(edits))):
        epoch = seed(client)
        for batch in order:
            assert merge(client, epoch, batch).json()["valid"]
        final = state(client)
        assert merge(client, epoch, order[0]).json() == final
        results.append((final["plan"], final["ops"]))
    assert results[0] == results[1]
    assert results[0][0]["lost_link_budget_s"] == 120
    assert results[0][0]["zones"][0]["priority"] == 2
    assert results[0][0]["zones"][1]["comms"] == "lost_link_ok"


def test_concurrent_same_field_tie_breaks_by_client_then_new_lamport_clock_wins(session):
    client, _ = session
    a, b = op("a", "zone:Z1", "priority", 2), op("b", "zone:Z1", "priority", 3)
    for order in ([a, b], [b, a]):
        epoch = seed(client)
        assert merge(client, epoch, order).json()["plan"]["zones"][0]["priority"] == 3
        assert merge(client, epoch, [op("a", "zone:Z1", "priority", 4, 2)]).json()["plan"]["zones"][0]["priority"] == 4


def test_tombstone_survives_concurrent_edit_and_explicit_undelete_preserves_edit(session):
    client, _ = session
    poly = [[7,13],[9,13],[9,16],[7,16]]
    delete = op("a", "zone:Z2", "deleted", True)
    edit = op("b", "zone:Z2", "poly", poly, 100)
    for order in ([delete, edit], [edit, delete]):
        epoch = seed(client)
        result = merge(client, epoch, order).json()
        assert result["valid"] and [z["id"] for z in result["plan"]["zones"]] == ["Z1"]
        result = merge(client, epoch, [op("a", "zone:Z2", "deleted", False, 2)]).json()
        assert result["plan"]["zones"][1]["poly"] == poly


def test_invalid_concurrent_candidate_converges_and_blocks_old_plan_dispatch(session):
    client, hub = session
    # Deleting every zone is a valid "clear" since no-go-only plans are accepted (Rayan's P0,
    # 2026-11-08), so the invalid candidate here is a zone moved outside the building.
    edits = [op("a", "zone:Z1", "deleted", True), op("b", "zone:Z2", "poly", [[50, 14], [60, 14], [60, 16], [50, 16]])]
    results = []
    for order in (edits, list(reversed(edits))):
        epoch = seed(client)
        for change in order:
            response = merge(client, epoch, [change])
            assert response.status_code == 200
        result = response.json()
        assert not result["valid"] and result["issues"] and [z["id"] for z in result["plan"]["zones"]] == ["Z2"]
        assert client.post("/api/dispatch", json={"plan_id": "CO-1"}).json()["detail"]["code"] == "plan_conflict"
        assert not hub.sim.network.queues["CMD"]
        results.append((result["plan"], result["ops"]))
    assert results[0] == results[1]
    fixed = merge(client, epoch, [op("a", "zone:Z2", "poly", [[7, 14], [9, 14], [9, 16], [7, 16]], 2)]).json()
    assert fixed["valid"] and len(fixed["plan"]["zones"]) == 1


def test_deleting_every_zone_is_a_valid_clear(session):
    """No zones left is a no-go-only (or empty) plan: valid, and dispatchable to every robot."""
    client, hub = session
    epoch = seed(client)
    result = merge(client, epoch, [op("a", "zone:Z1", "deleted", True), op("b", "zone:Z2", "deleted", True)]).json()
    assert result["valid"] and result["plan"]["zones"] == [] and not result["issues"]


def test_clock_reuse_different_value_is_atomic_error(session):
    client, _ = session
    epoch = seed(client)
    a = op("a", "zone:Z1", "priority", 2)
    assert merge(client, epoch, [a]).status_code == 200
    before = state(client)
    response = merge(client, epoch, [op("b", "plan", "lost_link_budget_s", 90), {**a, "value": 3}])
    assert response.status_code == 409 and response.json()["detail"]["code"] == "sync_clock"
    assert state(client) == before


def test_replace_reset_and_dispatch_protect_offline_epochs_and_immutable_ids(session):
    client, hub = session
    change = [op("a", "zone:Z1", "priority", 2)]
    epoch = seed(client)
    assert client.post("/api/plan?check=false", json=plan()).status_code == 200
    assert merge(client, epoch, change).json()["detail"]["code"] == "sync_epoch"
    epoch = seed(client)
    assert client.post("/api/dispatch", json={"plan_id": "CO-1"}).json()["ok"]
    assert merge(client, epoch, change).json()["detail"]["code"] == "plan_dispatched"
    assert client.put("/api/plan-sync", json=plan()).status_code == 409
    assert client.post("/api/control", json={"action": "reset"}).status_code == 200
    assert merge(client, epoch, change).json()["detail"]["code"] == "sync_epoch"
    assert not hub.plan_sync.docs


@pytest.mark.parametrize("change", [op("a","plan","truth",True), op("a","zone:Z1","priority",0),
                                    op("a","zone:Z1","deleted","yes"), op("a","zone:Z1","poly",[[0,0]]),
                                    op("a","plan","lost_link_budget_s",-1), op("a","zone:Z1","priority",2,0)])
def test_invalid_operation_rejected_without_mutating_registers(session, change):
    client, _ = session
    epoch = seed(client)
    before = state(client)
    assert merge(client, epoch, [op("b", "plan", "lost_link_budget_s", 90), change]).status_code == 422
    assert state(client) == before


def test_new_region_requires_complete_candidate_then_saves_only_when_valid(session):
    client, hub = session
    epoch = seed(client)
    result = merge(client, epoch, [op("a", "zone:Z3", "robot", "R1")]).json()
    assert not result["valid"] and len(hub.plans.current()["zones"]) == 2
    result = merge(client, epoch, [op("a", "zone:Z3", "poly", [[10,14],[12,14],[12,16],[10,16]], 2)]).json()
    assert result["valid"] and len(hub.plans.current()["zones"]) == 3


def test_gated_endpoints_and_outside_building_conflict(session, monkeypatch):
    client, _ = session
    epoch = seed(client)
    bad = op("a", "zone:Z1", "poly", [[-1,14],[6,14],[6,16],[-1,16]])
    result = merge(client, epoch, [bad]).json()
    assert not result["valid"] and "outside" in str(result["issues"]).lower()
    monkeypatch.delenv("DZ_CRDT")
    assert client.get("/api/plan-sync", params={"plan_id":"CO-1"}).status_code == 409
    assert merge(client, epoch, [bad]).status_code == 409


def test_both_online_phones_receive_merge_state_and_normal_valid_plan(session):
    client, _ = session
    with client.websocket_connect("/ws/phone?client=a") as a, client.websocket_connect("/ws/phone?client=b") as b:
        for phone in (a, b):
            assert [phone.receive_json()["t"] for _ in range(2)] == ["hello", "cmd_view"]
        epoch = seed(client)
        for phone in (a, b):
            assert [phone.receive_json()["t"] for _ in range(2)] == ["plan_sync", "plan_state"]
        result = merge(client, epoch, [op("a", "zone:Z1", "priority", 2)]).json()
        for phone in (a, b):
            message = phone.receive_json()
            assert message["t"] == "plan_sync" and message["data"] == result
            assert phone.receive_json()["t"] == "plan_state"
