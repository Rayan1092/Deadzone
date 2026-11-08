"""Moving packets and held-node cues must describe actual transport decisions."""
from copy import deepcopy
import json

from deadzone.network.dtn import DTNNetwork, make_bundle
from deadzone.network.propagation import LinkGraph
from deadzone.sim import Sim


def graph(*edges, rssi=-60):
    links = LinkGraph()
    for a, b in edges:
        edge = tuple(sorted((a, b)))
        links.up[edge], links.rssi[edge] = True, rssi
    return links


def network(trace=True):
    net = DTNNetwork(trace_enabled=trace)
    for node in ("R1", "RL1", "CMD"):
        net.register(node)
    return net


def packet(size=100):
    return make_bundle("R1", "CMD", "survivor", {"id": "S-hidden-until-delivered"}, 0, size)


def test_each_hop_fires_only_after_actual_custody_acceptance():
    net = network()
    bundle = packet()
    net.queues["R1"].append(bundle)
    links = graph(("R1", "RL1"), ("RL1", "CMD"))
    assert net.step(links, .1, .1) == []
    event, = net.drain_events()
    assert event["kind"] == "bundle_hop"
    assert (event["a"], event["b"]) == ("R1", "RL1")
    assert event["src"] == "R1" and event["dst"] == "CMD"
    assert event["hops"] == ["R1", "RL1"]
    assert event["bytes"] == event["wire_bytes"] == 100
    assert net.queue_view()["RL1"] == {"bundles": 1, "bytes": 100}
    arrived = net.step(links, .1, .2)
    assert len(arrived) == 1
    event, = net.drain_events()
    assert (event["a"], event["b"]) == ("RL1", "CMD")
    assert event["hops"] == ["R1", "RL1", "CMD"]
    assert all(v["bundles"] == 0 for v in net.queue_view().values())


def test_outage_hold_is_coalesced_then_actual_reconnect_emits_hop():
    net = network()
    net.queues["R1"].append(packet())
    assert not net.step(graph(), .1, .1)
    held, = net.drain_events()
    assert held["kind"] == "bundle_held" and held["reason"] == "no_route"
    assert held["node"] == "R1" and held["held_since"] == .1
    net.step(graph(), .1, .2)
    assert not net.drain_events()
    assert net.queue_view()["R1"]["bytes"] == 100
    assert len(net.step(graph(("R1", "CMD")), .1, .3)) == 1
    event, = net.drain_events()
    assert event["kind"] == "bundle_hop"


def test_custody_refusal_is_held_not_a_fake_hop_and_reason_changes_are_visible():
    net = network()
    net.limits["CMD"] = 0
    net.queues["R1"].append(packet())
    net.step(graph(("R1", "CMD")), .1, .1)
    event, = net.drain_events()
    assert event["reason"] == "custody_refused"
    net.step(graph(("R1", "CMD")), .1, .2)
    assert not net.drain_events()
    net.step(graph(), .1, .3)
    event, = net.drain_events()
    assert event["reason"] == "no_route" and event["held_since"] == .3
    assert net.queue_view()["R1"]["bundles"] == 1
    assert net.counters["hop_transfers"] == 0


def test_link_budget_and_disabled_nodes_report_the_actual_hold_reason():
    net = network()
    net.queues["R1"].extend([packet(size=100_000), packet(size=100_000)])
    net.step(graph(("R1", "CMD")), .1, .1)
    event, = net.drain_events()
    assert event["kind"] == "bundle_held" and event["reason"] == "link_busy"
    net.disabled.add("R1")
    net.step(graph(("R1", "CMD")), .1, .2)
    events = net.drain_events()
    assert len(events) == 2 and all(e["reason"] == "disabled" for e in events)
    assert not net.counters["hop_transfers"]


def test_partial_transfer_is_not_reported_as_a_completed_hop_or_held():
    net = network()
    net.queues["R1"].append(packet(size=100_000))
    links = graph(("R1", "CMD"))
    for now in (.1, .2, .3):
        assert not net.step(links, .1, now)
        assert not net.drain_events()
        assert net.queue_view()["R1"]["bytes"] == 100_000
    assert len(net.step(links, .1, .4)) == 1
    event, = net.drain_events()
    assert event["started_t"] == .1 and event["arrived_t"] == .4
    assert event["wire_bytes"] == 100_000


def test_fec_failure_retains_custody_without_emitting_a_hop():
    from deadzone.network.fec import DecodeFailure
    net = network()
    net.fec_enabled = True
    class BrokenCodec:
        def encode(self, payload): return b"wire", 100
        def corrupt(self, encoded, rssi, rng): return encoded, 1
        def decode(self, encoded): raise DecodeFailure()
    net.codec = BrokenCodec()
    net.queues["R1"].append(packet())
    assert not net.step(graph(("R1", "CMD"), rssi=-85), .1, .1)
    event, = net.drain_events()
    assert event["kind"] == "bundle_held" and event["reason"] == "fec_retry"
    assert net.queue_view()["R1"]["bundles"] == 1


def test_real_fec_hop_reports_encoded_wire_size_only_after_delivery():
    net = DTNNetwork(fec_enabled=True, trace_enabled=True, seed=7)
    for node in ("R1", "CMD"):
        net.register(node)
    net.queues["R1"].append(packet())
    events, arrived = [], []
    for tick in range(1, 21):
        arrived.extend(net.step(graph(("R1", "CMD"), rssi=-85), .1, tick / 10))
        events.extend(net.drain_events())
        if arrived:
            break
    assert len(arrived) == 1
    hops = [e for e in events if e["kind"] == "bundle_hop"]
    assert len(hops) == 1 and hops[0]["wire_bytes"] >= hops[0]["bytes"]


def test_diagnostic_buffer_is_bounded_without_dropping_transport():
    net = network()
    net.queues["R1"].extend(packet(size=1) for _ in range(600))
    assert len(net.step(graph(("R1", "CMD")), .1, .1)) == 600
    assert len(net.drain_events()) == 512
    assert net.counters["traffic_events_dropped"] == 88
    assert net.counters["transport_delivered"] == 600


def test_tracing_does_not_change_routes_custody_or_counters():
    off, on = network(False), network(True)
    bundle = packet(size=30_000)
    off.queues["R1"].append(deepcopy(bundle))
    on.queues["R1"].append(deepcopy(bundle))
    links = graph(("R1", "RL1"), ("RL1", "CMD"))
    for now in (.1, .2, .3, .4):
        assert off.step(links, .1, now) == on.step(links, .1, now)
        assert off.queues == on.queues
        assert off._progress == on._progress
    assert not off.drain_events()
    assert all(on.counters[k] == v for k, v in off.counters.items())
    assert "traffic_events_dropped" not in off.counters


def test_queue_inventory_is_reality_only_and_matches_custody(monkeypatch):
    monkeypatch.setenv("DZ_NETWORK_TRAFFIC", "1")
    sim = Sim(n_robots=3)
    sim.network.queues["R1"].append(packet())
    snapshot = sim.snapshot()
    queues = snapshot["reality"]["queues"]
    assert sum(v["bundles"] for v in queues.values()) == snapshot["stats"]["in_flight"]
    assert sum(v["bytes"] for v in queues.values()) == snapshot["stats"]["queued_bytes"]
    assert "queues" not in json.dumps(snapshot["command"])
    assert "S-hidden-until-delivered" not in json.dumps(snapshot)
    monkeypatch.delenv("DZ_NETWORK_TRAFFIC", raising=False)
    sim.reset()
    assert "queues" not in sim.snapshot()["reality"]


def test_screen_receives_real_traffic_while_phone_sees_only_delivered_state(monkeypatch):
    import asyncio
    from deadzone.app import Hub

    monkeypatch.setenv("DZ_NETWORK_TRAFFIC", "1")
    hub = Hub()
    hub.sim.drain_events()

    class Sink:
        def __init__(self):
            self.frames = []

        async def send_text(self, message):
            self.frames.append(json.loads(message))

    screen, phone = Sink(), Sink()
    hub.screens.add(screen)
    hub.phones.add(phone)
    bundle = packet()
    bundle["payload"].update(t=hub.sim.time, pos=[1.0, 15.0], by="R1", conf=.9)
    hub.sim.network.queues["R1"].append(bundle)
    hub.sim.links = graph()
    hub.sim._move_bundles(.1)
    asyncio.run(hub.broadcast_tick(force_maps=True))
    events = [frame["data"] for frame in screen.frames if frame["t"] == "event"]
    assert any(event["kind"] == "bundle_held" for event in events)
    assert all(frame["t"] == "cmd_view" for frame in phone.frames)
    assert "S-hidden-until-delivered" not in json.dumps(phone.frames)
    assert "queues" not in json.dumps(phone.frames)

    screen.frames.clear()
    phone.frames.clear()
    hub.sim.links = graph(("R1", "CMD"))
    hub.sim._move_bundles(.1)
    asyncio.run(hub.broadcast_tick(force_maps=True))
    hops = [frame["data"] for frame in screen.frames
            if frame["t"] == "event" and frame["data"]["kind"] == "bundle_hop"]
    assert len(hops) == 1 and (hops[0]["a"], hops[0]["b"]) == ("R1", "CMD")
    assert all(frame["t"] == "cmd_view" for frame in phone.frames)
