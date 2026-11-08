"""Person 3's demo dependencies: paused safety, screen state, relays and director APIs."""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.network.dtn import make_bundle  # noqa: E402
from deadzone.network.propagation import LinkGraph  # noqa: E402
from deadzone.sim import DT, Sim  # noqa: E402

api = importlib.import_module("deadzone.app")


def draft():
    return {"plan_id": "P1", "author": "planner", "zones": [
        {"id": "Z1", "robot": "R1", "poly": [[3, 14], [6, 14], [6, 16], [3, 16]]}]}


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_ROBOTS", "3")
    monkeypatch.setattr(api, "hub", api.Hub())
    with TestClient(api.app) as client:
        yield client, api.hub


def screen_initial(ws):
    messages = [ws.receive_json() for _ in range(4)]
    assert [m["t"] for m in messages] == ["hello", "maps", "tick", "plan_state"]
    return messages


def relay_initial(ws):
    hello, view, state = [ws.receive_json() for _ in range(3)]
    assert [hello["t"], view["t"], state["t"]] == ["hello", "cmd_view", "relay_state"]
    assert hello["data"]["relay_id"] == state["data"]["id"]
    assert "rubble" not in hello["data"]["floorplan"]
    return state["data"]


def graph(*edges):
    links = LinkGraph()
    for a, b in edges:
        key = tuple(sorted((a, b)))
        links.up[key], links.rssi[key] = True, -60
    return links


def test_paused_demo_has_real_delivered_telemetry_for_all_robots(session):
    client, hub = session
    assert not hub.running and hub.sim.tick_n == 1
    assert set(hub.sim.post.robots) == {"R1", "R2", "R3"}
    assert hub.sim.post.delivered > 0
    data = draft()
    data["zones"] = [{**data["zones"][0], "id": f"Z{i}", "robot": f"R{i}"} for i in (1, 2, 3)]
    assert client.post("/api/plan", json=data).json()["ok"]
    assert not hub.running and hub.sim.tick_n == 1
    assert client.post("/api/control", json={"action": "reset"}).status_code == 200
    assert hub.sim.tick_n == 1 and set(hub.sim.post.robots) == {"R1", "R2", "R3"}
    assert client.post("/api/plan", json=data).json()["ok"]


def test_screen_gets_same_plan_state_as_phone_and_a_dispatch_event(session):
    client, hub = session
    with client.websocket_connect("/ws/screen") as screen:
        screen_initial(screen)
        with client.websocket_connect("/ws/phone?client=planner") as phone:
            assert phone.receive_json()["t"] == "hello"
            assert phone.receive_json()["t"] == "cmd_view"
            phone.send_json({"t": "plan_edit", "data": draft()})
            a, b = screen.receive_json(), phone.receive_json()
            assert a["t"] == b["t"] == "plan_state" and a["data"] == b["data"]
            assert client.post("/api/dispatch", json={"plan_id": "P1"}).json()["ok"]
            assert screen.receive_json()["t"] == "plan_state"
            assert phone.receive_json()["t"] == "plan_state"
            event = screen.receive_json()
            assert event["data"] == {"kind": "plan_dispatched", "plan_id": "P1"}
    with client.websocket_connect("/ws/screen") as screen:
        messages = screen_initial(screen)
        assert messages[-1]["data"]["plan_id"] == "P1"


def test_relay_place_power_disconnect_and_reconnect_preserve_identity_and_custody(session):
    client, hub = session
    with client.websocket_connect("/ws/phone?client=relay-a&role=relay") as ws:
        initial = relay_initial(ws)
        rid = initial["id"]
        assert initial["on"] and hub.sim.relays[rid]["phone"]
        held = make_bundle("R1", "CMD", "map_patch", {}, hub.sim.time, 100)
        hub.sim.network.queues[rid].append(held)
        ws.send_json({"t": "relay_place", "data": {"pos": [8, 15]}})
        moved = ws.receive_json()["data"]
        assert moved["id"] == rid and moved["pos"] == [8, 15]
        assert held in hub.sim.network.queues[rid]
        assert all(set(n) == {"id", "rssi"} for n in moved["neighbors"])
        ws.send_json({"t": "relay_power", "data": {"on": False}})
        off = ws.receive_json()["data"]
        assert not off["on"] and off["neighbors"] == []
        assert held in hub.sim.network.queues[rid]
    with client.websocket_connect("/ws/phone?client=relay-a&role=relay") as ws:
        assert relay_initial(ws)["id"] == rid
        assert not hub.sim.relays[rid]["on"]  # explicit off survives reconnect
        ws.send_json({"t": "relay_power", "data": {"on": True}})
        assert ws.receive_json()["data"]["on"]
    assert not hub.sim.relays[rid]["on"]  # last connection closed
    with client.websocket_connect("/ws/phone?client=relay-a&role=relay") as ws:
        state = relay_initial(ws)
        assert state["id"] == rid and state["on"]  # restore requested on


def test_two_connections_share_relay_and_one_disconnect_does_not_turn_it_off(session):
    client, hub = session
    with client.websocket_connect("/ws/phone?client=same&role=relay") as a:
        rid = relay_initial(a)["id"]
        with client.websocket_connect("/ws/phone?client=same&role=relay") as b:
            assert relay_initial(b)["id"] == rid
        assert hub.sim.relays[rid]["on"]
    assert not hub.sim.relays[rid]["on"]


@pytest.mark.parametrize("message", [
    {"t": "relay_power", "data": {"on": "false"}},
    {"t": "relay_power", "data": {"on": True, "id": "RL999"}},
    {"t": "relay_place", "data": {"pos": [-1, 15]}},
    {"t": "relay_place", "data": {"pos": [18, 6]}},
])
def test_invalid_relay_controls_are_rejected_without_changing_state(session, message):
    client, hub = session
    with client.websocket_connect("/ws/phone?client=relay-a&role=relay") as ws:
        initial = relay_initial(ws)
        ws.send_json(message)
        assert ws.receive_json()["t"] == "error"
        assert hub.sim.relays[initial["id"]]["pos"] == initial["pos"]
        assert hub.sim.relays[initial["id"]]["on"]


def test_relay_session_limit_returns_error_and_cleans_up(session, monkeypatch):
    client, hub = session
    monkeypatch.setattr(api, "MAX_PHONE_RELAYS", 0)
    with client.websocket_connect("/ws/phone?client=relay-a&role=relay") as ws:
        assert ws.receive_json()["data"]["code"] == "relay_limit"
    assert not hub.phone_sessions and not hub.relay_clients


def test_reset_recreates_connected_relay_at_entry_with_new_hello_and_state(session):
    client, hub = session
    with client.websocket_connect("/ws/phone?client=relay-a&role=relay") as ws:
        relay_initial(ws)
        ws.send_json({"t": "relay_place", "data": {"pos": [8, 15]}})
        ws.receive_json()
        assert client.post("/api/control", json={"action": "reset"}).status_code == 200
        state = relay_initial(ws)
        assert state["pos"] == list(hub.sim.prior.entry) and state["on"]
        assert len(hub.relay_clients) == 1 and hub.sim.tick_n == 1


def test_phone_power_toggle_breaks_and_restores_actual_dtn_path(session):
    client, hub = session
    sim = hub.sim
    sim.bodies["R1"].update(x=37.5, y=19)
    with client.websocket_connect("/ws/phone?client=relay-a&role=relay") as ws:
        rid = relay_initial(ws)["id"]
        ws.send_json({"t": "relay_place", "data": {"pos": [33, 15]}})
        ws.receive_json()
        assert sim.radio_path("R1", "CMD") == ["R1", rid, "CMD"]
        for queue in sim.network.queues.values():
            queue.clear()
        payload = {"id": "SX", "pos": [37.5, 19], "by": "R1", "t": sim.time, "conf": 0.9}
        sim.robots["R1"].outbox.append(make_bundle("R1", "CMD", "survivor", payload, sim.time, 400))
        sim._move_bundles(DT)
        assert any(b["kind"] == "survivor" for b in sim.network.queues[rid])
        assert "SX" not in sim.post.survivors
        ws.send_json({"t": "relay_power", "data": {"on": False}})
        ws.receive_json()
        sim._move_bundles(DT)
        assert "SX" not in sim.post.survivors
        ws.send_json({"t": "relay_power", "data": {"on": True}})
        ws.receive_json()
        sim._move_bundles(DT)
        assert "SX" in sim.post.survivors


def test_fault_api_and_director_inject_same_expiring_sensor_condition(session):
    client, hub = session
    io = hub.sim.ios["R1"]
    assert io.motor_current() < 6
    response = client.post("/api/fault", json={"type": "overcurrent", "robot": "R1"})
    assert response.status_code == 200 and response.json()["ok"]
    assert io.motor_current() == io.odometry()["wheel_current"] == 8
    assert "R1" not in hub.sim.post.faults  # injection is not a delivered fault report
    hub.sim.time = response.json()["until"]
    assert io.motor_current() < 6
    response = client.post("/api/control", json={"action": "director",
        "value": {"do": "overcurrent", "robot": "R1"}})
    assert response.status_code == 200 and io.motor_current() == 8
    client.post("/api/control", json={"action": "reset"})
    assert hub.sim.ios["R1"].motor_current() < 6 and not hub.sim.overcurrent_until


def test_screen_f_key_payload_and_malformed_controls_leave_socket_working(session):
    client, hub = session
    with client.websocket_connect("/ws/screen") as ws:
        screen_initial(ws)
        ws.send_json({"t": "control", "data": {"action": "director",
                     "value": {"do": "overcurrent", "robot": "missing"}}})
        assert ws.receive_json()["data"]["code"] == "robot_not_found"
        ws.send_json({"t": "control", "data": {"action": "director",
                     "value": {"do": "overcurrent", "robot": "R1"}}})
        messages = []
        while not messages or messages[-1]["t"] != "control":
            messages.append(ws.receive_json())
        assert any(m.get("data", {}).get("kind") == "fault_injected" for m in messages)
        assert hub.sim.ios["R1"].motor_current() == 8


@pytest.mark.parametrize("body,status", [
    ({"type": "overcurrent", "robot": "R99"}, 404),
    ({"type": "overcurrent", "robot": "R1", "duration_s": -1}, 422),
    ({"type": "rubble", "at": [-1, 15]}, 422),
    ({"type": "rubble", "at": [8, 15], "size": 100}, 422),
    ({"type": "unknown"}, 422),
])
def test_fault_requests_are_validated(session, body, status):
    client, _ = session
    assert client.post("/api/fault", json=body).status_code == status


def test_rubble_api_updates_reality_but_not_phone_prior_or_command_map(session):
    client, hub = session
    count = len(hub.sim.fp.data["rubble"])
    before = hub.sim.post.map.copy()
    response = client.post("/api/fault", json={"type": "rubble", "at": [8, 15]})
    assert response.status_code == 200 and len(hub.sim.fp.data["rubble"]) == count + 1
    assert (hub.sim.post.map == before).all()
    assert "rubble" not in client.get("/api/floorplan").json()


def test_report_contains_only_delivered_command_facts_and_is_broadcast(session, monkeypatch):
    monkeypatch.setenv("DZ_GEMINI", "0")  # never call a user's key from this fallback test
    client, hub = session
    hub.sim.robots["R1"].found["HIDDEN"] = {"id": "HIDDEN", "pos": [36, 27]}
    hub.sim.robots["R1"].fault = "UNREPORTED"
    with client.websocket_connect("/ws/screen") as ws:
        screen_initial(ws)
        response = client.get("/api/report")
        result = response.json()
        assert result["source"] == "local" and "Command briefing" in result["text"]
        assert "HIDDEN" not in result["text"] and "UNREPORTED" not in result["text"]
        assert ws.receive_json() == {"t": "report", "seq": hub.seq, "time": hub.sim.time, "data": result}
    payload = {"robot": "R1", "fault": "TRAPPED", "pos": [2, 15], "t": hub.sim.time}
    arrived = make_bundle("R1", "CMD", "fault", payload, hub.sim.time, 120)
    arrived["custodian"] = "CMD"
    hub.sim.post.receive(arrived, hub.sim.time)
    public_report = client.get("/api/report").json()["text"]
    assert "trapped" in public_report and "Scout 1" in public_report
    assert "TRAPPED" not in public_report and "R1" not in public_report
    assert hub.phone_view()["faults"][0]["fault"] == "TRAPPED"


def test_bundle_delivered_event_occurs_once_after_cmd_arrival_not_at_relay():
    sim = Sim()
    relay = sim.add_relay((8, 15))
    sim.events.clear()
    for queue in sim.network.queues.values():
        queue.clear()
    payload = {"id": "R1", "pose": [2, 15, 0], "state": "EXPLORING", "battery_pct": 90}
    b = make_bundle("R1", "CMD", "telemetry", payload, 0, 400)
    sim.robots["R1"].outbox.append(b)
    sim.links = graph(("R1", relay), (relay, "CMD"))
    sim.time = 0.1
    sim._move_bundles(DT)
    assert not sim.drain_events()
    sim.time = 0.2
    sim._move_bundles(DT)
    events = sim.drain_events()
    assert len(events) == 1 and events[0]["kind"] == "bundle_delivered"
    assert events[0]["hops"] == ["R1", relay, "CMD"]
    sim.robots["R1"].outbox.append(b)
    sim._move_bundles(DT)
    sim._move_bundles(DT)
    assert not sim.drain_events() and sim.post.delivered == 1


def test_relay_positions_at_same_sim_time_do_not_rewind_command_when_reordered():
    sim = Sim()
    rid = sim.add_relay((8, 15))
    old = sim.network.queues[rid][0]
    sim.move_relay(rid, (9, 15))
    latest = sim.network.queues[rid][0]
    assert len(sim.network.queues[rid]) == 1
    assert old["created"] == latest["created"]
    assert old["payload"]["pos"] == [8, 15]
    sim.post.receive(dict(latest, custodian="CMD"), 0)
    sim.post.receive(dict(old, custodian="CMD"), 0)
    assert sim.post.view(0)["relays"] == [{"id": rid, "pos": [9, 15], "beacon_for": None}]


def test_own_relay_updates_do_not_overfill_a_full_custody_queue():
    sim = Sim()
    rid = sim.add_relay((8, 15))
    held = make_bundle("R1", "CMD", "survivor", {}, 0, 2_000_000)
    sim.network.queues[rid].append(held)
    sim.move_relay(rid, (9, 15))
    assert sim.network.queues[rid] == [held]


def test_failed_relay_state_send_removes_ghost_powered_node(session):
    _, hub = session
    class Closed:
        async def send_text(self, text):
            raise RuntimeError("closed")
    ws = Closed()
    rid = hub.attach_relay("gone")
    hub.phone_sessions[ws] = ("gone", "relay")
    hub.phones.add(ws)
    import asyncio
    asyncio.run(hub.relay_states())
    assert ws not in hub.phone_sessions and ws not in hub.phones
    assert not hub.sim.relays[rid]["on"]


def test_periodic_relay_state_follows_command_view(session):
    client, hub = session
    with client.websocket_connect("/ws/phone?client=relay-a&role=relay") as ws:
        rid = relay_initial(ws)["id"]
        for _ in range(4):
            hub.sim.tick()
        client.portal.call(hub.broadcast_tick)
        assert ws.receive_json()["t"] == "cmd_view"
        state = ws.receive_json()
        assert state["t"] == "relay_state" and state["data"]["id"] == rid
        assert state["data"]["queue"] == len(hub.sim.network.queues[rid])


@pytest.mark.parametrize("control", [
    {"action": "speed", "value": "fast"},
    {"action": "director", "value": {"do": "rubble", "type": "overcurrent", "robot": "R1"}},
    {"action": "unknown"},
])
def test_malformed_director_controls_return_422(session, control):
    client, _ = session
    assert client.post("/api/control", json=control).status_code == 422


def test_backend_delegates_overcurrent_to_robot_owned_hook_when_available(session, monkeypatch):
    client, hub = session
    calls = []
    monkeypatch.setattr(hub.sim.robots["R1"], "inject_overcurrent", lambda seconds: calls.append(seconds), raising=False)
    response = client.post("/api/fault", json={"type": "overcurrent", "robot": "R1", "duration_s": 2})
    assert response.json()["ok"] and calls == [2]
    client.post("/api/fault", json={"type": "overcurrent", "robot": "R1", "duration_s": 1})
    assert calls == [2, 2]  # overlapping injections must not shorten the robot's spike


def test_real_fault_api_drives_robot_detection_reverse_and_replanning(session):
    client, hub = session
    for _ in range(30):
        hub.sim.tick()
    assert client.post("/api/fault", json={"type": "overcurrent", "robot": "R1"}).json()["ok"]
    states, faults = set(), set()
    for _ in range(80):
        hub.sim.tick()
        robot = hub.sim.robots["R1"]
        states.add(robot.state)
        faults.add(robot.fault)
    assert "OVERCURRENT" in faults
    assert {"FAULT", "REPLANNING"} <= states
    assert hub.sim.robots["R1"].state != "FAULT"
