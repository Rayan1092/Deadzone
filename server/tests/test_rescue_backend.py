"""Delivery-only rescue routes and dark-only beacon IO."""
import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deadzone.network.dtn import DTNNetwork, make_bundle  # noqa: E402
from deadzone.network.propagation import LinkGraph  # noqa: E402
from deadzone.sim import DT, Sim  # noqa: E402

api = importlib.import_module("deadzone.app")


def graph(*edges, rssi=-60):
    links = LinkGraph()
    for a, b in edges:
        key = tuple(sorted((a, b)))
        links.up[key], links.rssi[key] = True, rssi
    return links


def route(t=0.0, **changes):
    return {"survivor_id": "S1", "by": "R1", "t": t, "path": [[2, 15], [8, 15]],
            "length_m": 6.0, "beacon_id": None, **changes}


def arrived(payload, created=None):
    b = make_bundle("R1", "CMD", "rescue_route", payload, payload["t"] if created is None else created, 100)
    b["custodian"] = "CMD"
    return b


def test_route_waits_for_all_hops_and_reconnect_before_command_knows_it():
    sim = Sim()
    relay = sim.add_relay((8, 15))
    for queue in sim.network.queues.values():
        queue.clear()
    sim.events.clear()
    b = make_bundle("R1", "CMD", "rescue_route", route(beacon_id=relay), 0, 100)
    sim.robots["R1"].outbox.append(b)
    sim.links = graph(("R1", relay), (relay, "CMD"))
    sim.time = .1
    sim._move_bundles(DT)
    assert len(sim.network.queues[relay]) == 1
    assert sim.post.view(sim.time)["routes"] == [] and sim.post.events == []
    sim.links = graph(("R1", relay))
    sim.time = .5
    sim._move_bundles(DT)
    assert not sim.post.routes
    sim.links = graph(("R1", relay), (relay, "CMD"))
    sim.time = 1
    sim._move_bundles(DT)
    record = {"survivor": "S1", "by": "R1", "path": [[2.0, 15.0], [8.0, 15.0]],
              "length_m": 6.0, "beacon_id": relay, "t": 0.0, "reported_t": 1.0,
              "beacon": relay, "clearance_m": None}
    assert sim.post.view(1)["routes"] == [record]
    assert sim.post.events == [{"kind": "rescue_route_reported", **record, "delay_s": 1.0}]
    assert not sim.post.survivors  # route arrival does not invent a survivor delivery


def test_newest_generation_time_wins_and_duplicates_do_not_repeat_events():
    post = Sim().post
    newest = arrived(route(t=2, length_m=7))
    assert post.receive(newest, 3)
    assert not post.receive(newest, 3)
    post.events.clear()
    assert post.receive(arrived(route(t=1), created=4), 5)  # newly sent, older route
    assert post.receive(arrived(route(t=2, length_m=9), created=4), 5)  # same generation: first wins
    assert post.view(5)["routes"][0]["length_m"] == 7 and not post.events
    assert post.receive(arrived(route(t=6, beacon_id="RL2")), 7)
    assert post.view(7)["routes"][0]["beacon_id"] == "RL2" and len(post.events) == 1
    newest["payload"]["path"][0][0] = 99
    view = post.view(7)
    view["routes"][0]["path"][0][0] = 99
    assert post.view(7)["routes"][0]["path"][0][0] == 2


def test_pr25_wire_format_is_accepted_without_changing_canonical_view_fields():
    post = Sim().post
    old_payload = {"survivor": "S1", "by": "R1", "t": 0, "path": [[2, 15], [8, 15]],
                   "length_m": 6, "beacon": "RL2", "clearance_m": .25}
    assert post.receive(arrived(old_payload), 2)
    record = post.view(2)["routes"][0]
    assert record["survivor"] == "S1" and record["beacon_id"] == "RL2"
    assert record["beacon"] == record["beacon_id"] and record["clearance_m"] == .25
    assert post.events[0]["kind"] == "rescue_route_reported"
    assert post.events[0]["delay_s"] == 2


def test_legacy_dense_straights_are_compacted_but_turns_are_never_removed():
    post = Sim().post
    legacy = {"survivor": "S1", "by": "R1", "t": 0,
              "path": [[2 + i * .125, 15] for i in range(95)],
              "length_m": 11.75, "beacon": None, "clearance_m": .25}
    assert post.receive(arrived(legacy), 1)
    assert post.view(1)["routes"][0]["path"] == [[2, 15], [13.75, 15]]
    turns = {**legacy, "survivor": "S2", "path": [[2 + i * .125, 15 + i % 2] for i in range(95)]}
    assert not post.receive(arrived(turns), 1)  # cannot fit without changing the route geometry
    assert "S2" not in post.routes


@pytest.mark.parametrize("changes", [
    {"path": []}, {"path": [[2, 15]] * 61}, {"path": [[float("nan"), 15]]},
    {"path": [[-1, 15]]}, {"path": [[999, 15]]}, {"path": [[2, 15, 0]]},
    {"t": "2"}, {"t": -1}, {"length_m": -1}, {"length_m": float("inf")},
    {"by": "R2"}, {"beacon_id": 3}, {"extra": "not in contract"},
])
def test_malformed_routes_do_not_poison_command_state(changes):
    post = Sim().post
    assert not post.receive(arrived(route(**changes), created=0), 1)
    assert post.delivered == 0 and not post.routes and not post.events


def test_expired_route_never_reaches_command_and_route_has_priority_over_telemetry():
    net = DTNNetwork()
    net.register("R1")
    net.register("CMD")
    expired = make_bundle("R1", "CMD", "rescue_route", route(), 0, 100, ttl=.1)
    net.queues["R1"].append(expired)
    assert net.step(graph(("R1", "CMD")), DT, 1) == []
    assert net.queues["R1"] == []
    rescue = make_bundle("R1", "CMD", "rescue_route", route(), 1, 10)
    telemetry = make_bundle("R1", "CMD", "telemetry", {}, 1, 2000)
    survivor = make_bundle("R1", "CMD", "survivor", {}, 1, 400)
    net.queues["R1"].extend([telemetry, rescue, survivor])
    delivered = net.step(graph(("R1", "CMD"), rssi=-88), DT, 1)
    assert [b["kind"] for b in delivered] == ["survivor", "rescue_route"]
    assert rescue["size"] >= len(json.dumps(route(), separators=(",", ":")).encode()) + 64


def test_beacon_io_only_drops_while_dark_and_metadata_waits_for_delivery():
    sim = Sim()
    io = sim.ios["R1"]
    assert io.radio.cmd_reachable()
    assert io.drop_relay(beacon_for="S1") is None and not sim.relays
    sim.bodies["R1"].update(x=36, y=27)
    sim._update_links()
    assert not io.radio.cmd_reachable()
    rid = io.drop_relay(beacon_for="S1")
    event = next(e for e in sim.drain_events() if e["kind"] == "relay_dropped")
    assert event["id"] == rid and event["beacon_for"] == "S1"
    assert sim.relays[rid]["beacon_for"] == "S1"
    assert sim.post.view(0)["relays"] == []
    sim.links = graph((rid, "CMD"))
    sim._move_bundles(DT)
    assert sim.post.view(0)["relays"] == [{"id": rid, "pos": [36.0, 27.0], "beacon_for": "S1"}]
    # Existing ordinary relay drops remain valid while linked.
    sim.bodies["R1"].update(x=2, y=15)
    sim._update_links()
    ordinary = io.drop_relay()
    assert sim.relays[ordinary]["beacon_for"] is None


def test_late_joiners_receive_routes_and_reset_clears_them(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setattr(api, "hub", api.Hub())
    assert api.hub.sim.post.receive(arrived(route()), api.hub.sim.time)
    with TestClient(api.app) as client:
        with client.websocket_connect("/ws/screen") as screen:
            messages = [screen.receive_json() for _ in range(4)]
            assert messages[2]["data"]["command"]["routes"][0]["survivor"] == "S1"
        with client.websocket_connect("/ws/phone?client=late") as phone:
            phone.receive_json()
            assert phone.receive_json()["data"]["routes"][0]["survivor"] == "S1"
        client.post("/api/control", json={"action": "reset"})
        assert api.hub.phone_view()["routes"] == []
