"""Loss, congestion and knowledge-boundary scenarios for Person 2's network."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.network.dtn import DTNNetwork, make_bundle  # noqa: E402
from deadzone.network.propagation import LinkGraph  # noqa: E402
from deadzone.sim import DT, Sim  # noqa: E402


def graph(*edges, rssi=-60.0):
    links = LinkGraph()
    for a, b in edges:
        key = tuple(sorted((a, b)))
        links.up[key] = True
        links.rssi[key] = rssi
    return links


def network(*nodes, relay_capacity=2_000_000):
    net = DTNNetwork()
    for node in nodes:
        net.register(node, capacity_bytes=relay_capacity if node.startswith("RL") else None)
    return net


def bundle(src="R1", dst="CMD", kind="telemetry", size=400, created=0.0, ttl=900.0, payload=None):
    return make_bundle(src, dst, kind, {} if payload is None else payload, created, size, ttl)


def test_chain_moves_one_hop_per_tick_and_records_custody():
    net = network("R1", "RL1", "RL2", "CMD")
    links = graph(("R1", "RL1"), ("RL1", "RL2"), ("RL2", "CMD"))
    original = bundle()
    net.queues["R1"].append(original)
    for tick, holder in enumerate(("RL1", "RL2"), 1):
        assert net.step(links, DT, tick * DT) == []
        held = [(node, b) for node, queue in net.queues.items() for b in queue]
        assert len(held) == 1
        assert held[0][0] == held[0][1]["custodian"] == holder
    received = net.step(links, DT, 3 * DT)
    assert len(received) == 1
    assert received[0]["hops"] == ["R1", "RL1", "RL2", "CMD"]
    assert received[0]["custodian"] == "CMD"
    assert not any(net.queues.values())
    assert original["hops"] == ["R1"]  # forwarding must not mutate the sender's record


def test_link_failure_mid_transfer_keeps_sender_copy_and_restarts():
    net = network("R1", "CMD")
    links = graph(("R1", "CMD"))  # 25,000 bytes per tick
    pending = bundle(size=60_000)
    net.queues["R1"].append(pending)
    assert net.step(links, DT, 0.1) == []
    assert net.queues["R1"][0] is pending
    assert pending["custodian"] == "R1"
    assert net.step(graph(), DT, 0.2) == []
    assert net.step(links, DT, 0.3) == []
    assert net.step(links, DT, 0.4) == []
    assert len(net.step(links, DT, 0.5)) == 1


def test_relay_keeps_custody_during_outage_then_forwards():
    net = network("R1", "RL1", "CMD")
    links = graph(("R1", "RL1"), ("RL1", "CMD"))
    net.queues["R1"].append(bundle())
    assert net.step(links, DT, 0.1) == []
    assert net.step(graph(("R1", "RL1")), DT, 0.2) == []
    assert len(net.queues["RL1"]) == 1
    assert net.queues["R1"] == []
    assert len(net.step(links, DT, 0.3)) == 1


def test_100_bundles_arrive_exactly_once_with_middle_link_toggling():
    net = network("R1", "RL1", "RL2", "CMD")
    outgoing = [bundle(size=1000) for _ in range(100)]
    expected = {b["bid"] for b in outgoing}
    net.queues["R1"].extend(outgoing)
    received = []
    held_during_outage = False
    for tick in range(1, 301):
        edges = [("R1", "RL1"), ("RL2", "CMD")]
        if (tick // 30) % 2:
            edges.append(("RL1", "RL2"))
        elif net.queues["RL1"]:
            held_during_outage = True
        received.extend(net.step(graph(*edges, rssi=-88), DT, tick * DT))
    ids = [b["bid"] for b in received]
    assert len(ids) == len(set(ids)) == 100
    assert set(ids) == expected
    assert held_during_outage
    assert not any(net.queues.values())


def test_duplicate_bundle_and_replayed_delivery_are_acked_once():
    net = network("R1", "CMD")
    links = graph(("R1", "CMD"))
    original = bundle()
    net.queues["R1"].extend([original, dict(original)])
    assert len(net.step(links, DT, 0.1)) == 1
    net.queues["R1"].append(dict(original))
    assert net.step(links, DT, 0.2) == []
    assert net.queues["R1"] == []


@pytest.mark.parametrize("at_relay", [False, True])
def test_ttl_expires_even_without_a_path(at_relay):
    net = network("R1", "RL1", "CMD")
    net.queues["R1"].append(bundle(ttl=0.15))
    if at_relay:
        net.step(graph(("R1", "RL1"), ("RL1", "CMD")), DT, 0.1)
        assert net.queues["RL1"]
    assert net.step(graph(), DT, 0.2) == []
    assert not any(net.queues.values())
    assert not any(net._seen.values())


def test_priority_then_age_orders_shared_link():
    net = network("R1", "CMD")
    old = bundle(created=0.0, size=1000)
    new = bundle(created=0.1, size=1000)
    survivor = bundle(kind="survivor", created=0.2, size=1000)
    net.queues["R1"].extend([new, old, survivor])
    received = net.step(graph(("R1", "CMD"), rssi=-88), DT, 0.3)
    assert [b["bid"] for b in received] == [survivor["bid"], old["bid"]]
    assert [b["bid"] for b in net.queues["R1"]] == [new["bid"]]


def test_two_directions_share_one_physical_link_budget():
    net = network("R1", "R2")
    net.queues["R1"].append(bundle(dst="R2", size=2000))
    net.queues["R2"].append(bundle(src="R2", dst="R1", size=2000))
    links = graph(("R1", "R2"), rssi=-88)
    first = net.step(links, DT, 0.1)
    second = net.step(links, DT, 0.2)
    assert len(first) == len(second) == 1
    assert first[0]["src"] == "R1"
    assert second[0]["src"] == "R2"


def test_full_relay_refuses_custody_without_deleting_sender():
    net = network("R1", "RL1", "CMD", relay_capacity=1000)
    held = bundle(src="RL1", dst="OFFLINE", kind="survivor", size=1000)
    incoming = bundle(kind="map_patch", size=1000)
    net.queues["RL1"].append(held)
    net.queues["R1"].append(incoming)
    assert net.step(graph(("R1", "RL1"), ("RL1", "CMD")), DT, 0.1) == []
    assert net.queues["R1"][0] is incoming
    assert net.queues["RL1"][0] is held


def test_relay_evicts_map_patch_to_accept_survivor():
    net = network("R1", "RL1", "CMD", relay_capacity=1000)
    held = bundle(src="RL1", dst="OFFLINE", kind="map_patch", size=1000)
    incoming = bundle(kind="survivor", size=1000)
    net.queues["RL1"].append(held)
    net.queues["R1"].append(incoming)
    assert net.step(graph(("R1", "RL1"), ("RL1", "CMD")), DT, 0.1) == []
    assert net.queues["R1"] == []
    assert [b["bid"] for b in net.queues["RL1"]] == [incoming["bid"]]


def test_oversize_bundle_does_not_evict_data_without_accepting_custody():
    net = network("R1", "RL1", "CMD", relay_capacity=1000)
    held = bundle(src="RL1", dst="OFFLINE", kind="map_patch", size=1000)
    incoming = bundle(kind="survivor", size=1500)
    net.queues["RL1"].append(held)
    net.queues["R1"].append(incoming)
    net.step(graph(("R1", "RL1"), ("RL1", "CMD")), DT, 0.1)
    assert net.queues["RL1"][0] is held
    assert net.queues["R1"][0] is incoming


def test_route_changes_do_not_loop_into_previous_custodian():
    net = network("R1", "RL1", "RL2", "RL3", "CMD")
    net.queues["R1"].append(bundle())
    links = graph(("R1", "RL1"), ("RL1", "RL2"), ("RL2", "CMD"))
    net.step(links, DT, 0.1)
    net.step(links, DT, 0.2)
    # RL2's old path dies; RL1 is now a tempting shortcut but already held the bid.
    links = graph(("RL2", "RL1"), ("RL1", "CMD"), ("RL2", "RL3"), ("RL3", "CMD"))
    assert net.step(links, DT, 0.3) == []
    assert net.queues["RL3"]
    received = net.step(links, DT, 0.4)
    assert received[0]["hops"] == ["R1", "RL1", "RL2", "RL3", "CMD"]


def test_non_forwarding_robot_can_receive_but_cannot_bridge_a_route():
    net = DTNNetwork()
    net.register("R1", can_forward=False)
    net.register("R2", can_forward=False)
    net.register("RL1")
    net.register("CMD")
    net.queues["R1"].append(bundle())
    bridge = graph(("R1", "R2"), ("R2", "CMD"))
    assert net.step(bridge, DT, 0.1) == []
    assert net.queues["R1"] and not net.queues["R2"]
    # A real relay route still works, even when the robot shortcut is cheaper.
    routed = graph(("R1", "R2"), ("R2", "CMD"), ("R1", "RL1"), ("RL1", "CMD"))
    assert net.step(routed, DT, 0.2) == []
    arrived = net.step(routed, DT, 0.3)
    assert arrived[0]["hops"] == ["R1", "RL1", "CMD"]
    net.queues["CMD"].append(bundle(src="CMD", dst="R2", kind="command"))
    assert net.step(routed, DT, 0.4)[0]["dst"] == "R2"


def test_robot_radio_and_screen_agree_that_robot_bridges_are_not_routes():
    sim = Sim(n_robots=2)
    sim.links = graph(("R1", "R2"), ("R2", "CMD"))
    assert not sim.ios["R1"].radio.cmd_reachable()
    assert sim.ios["R2"].radio.cmd_reachable()
    shown = {r["id"]: r for r in sim.snapshot()["reality"]["robots"]}
    assert not shown["R1"]["link"]["up"]
    assert shown["R2"]["link"]["up"]


def test_command_knows_survivor_and_map_only_after_last_hop():
    sim = Sim()
    relay = sim.add_relay((8, 15), owner="R1")
    sim.links = graph(("R1", relay), (relay, "CMD"))
    survivor = {"id": "S1", "pos": [37.5, 26], "by": "R1", "t": 0.0, "conf": 0.99}
    sim.robots["R1"].outbox.extend([
        bundle(kind="survivor", payload=survivor),
        bundle(kind="map_patch", payload={"ix": np.array([4]), "iy": np.array([5]), "v": np.array([1])}),
    ])
    assert sim.post.view(0)["relays"] == []
    sim.time = 0.1
    sim._move_bundles(DT)
    assert sim.post.survivors == {}
    assert not sim.post.map.any()
    assert sim.post.view(sim.time)["relays"] == [{"id": relay, "pos": [8.0, 15.0]}]
    assert sim.snapshot()["stats"]["in_flight"] == 2
    sim.links = graph(("R1", relay))
    sim.time = 0.2
    sim._move_bundles(DT)
    assert sim.post.survivors == {}
    sim.links = graph(("R1", relay), (relay, "CMD"))
    sim.time = 0.3
    sim._move_bundles(DT)
    assert sim.post.survivors["S1"]["reported_t"] == 0.3
    assert sim.post.map[5, 4] == 1
    assert sim.snapshot()["stats"]["in_flight"] == 0


def test_command_rejects_duplicate_expired_or_undelivered_bundles():
    sim = Sim()
    b = bundle(payload={"id": "R1", "pose": [2, 15, 0], "state": "EXPLORING", "battery_pct": 90})
    assert not sim.post.receive(b, 0.1)
    assert not sim.post.robots
    arrived = dict(b, custodian="CMD", hops=["R1", "CMD"])
    assert sim.post.receive(arrived, 0.1)
    assert not sim.post.receive(arrived, 0.2)
    assert not sim.post.receive(dict(arrived, bid="expired", ttl=0.1), 0.2)
    assert sim.post.delivered == 1


def test_delayed_map_patch_cannot_overwrite_newer_observation():
    sim = Sim()
    def patch(created, value):
        return dict(bundle(kind="map_patch", created=created,
                           payload={"ix": np.array([4]), "iy": np.array([5]), "v": np.array([value])}),
                    custodian="CMD")
    sim.post.receive(patch(2.0, 2), 3.0)
    sim.post.receive(patch(1.0, 1), 4.0)
    assert sim.post.map[5, 4] == 2


def test_robot_commands_take_the_same_network_path():
    sim = Sim()
    relay = sim.add_relay((8, 15))
    for queue in sim.network.queues.values():
        queue.clear()
    sim.links = graph(("CMD", relay), (relay, "R1"))
    sim.network.queues["CMD"].append(bundle(src="CMD", dst="R1", kind="command"))
    sim.time = 0.1
    sim._move_bundles(DT)
    assert sim.inboxes["R1"] == []
    sim.time = 0.2
    sim._move_bundles(DT)
    assert sim.inboxes["R1"][0]["hops"] == ["CMD", relay, "R1"]
    assert sim.post.delivered == 0


def test_power_cycle_retains_relay_queue_and_reset_clears_network():
    sim = Sim()
    relay = sim.add_relay((8, 15), owner="R1")
    count = len(sim.network.queues[relay])
    sim.set_relay_power(relay, False)
    assert not sim.links.neighbors(relay)
    assert len(sim.network.queues[relay]) == count
    assert not sim.snapshot()["reality"]["relays"][0]["on"]
    sim.set_relay_power(relay, True)
    assert sim.links.neighbors(relay)
    sim.reset()
    assert sim.relays == {}
    assert set(sim.network.queues) == {"CMD", "R1"}
    assert not any(sim.network.queues.values())
    assert not sim.post.relays


def test_real_radio_model_routes_a_dark_robot_through_a_relay():
    sim = Sim()
    sim.bodies["R1"].update(x=37.5, y=19.0)   # just south of the steel cage (S1 is inside it)
    sim._update_links()
    assert sim.links.path("R1", "CMD") is None
    relay = sim.add_relay((33, 15), owner="R1")
    assert sim.links.path("R1", "CMD") == ["R1", relay, "CMD"]
    rec = {"id": "S1", "pos": [37.5, 26], "by": "R1", "t": 0.0, "conf": 0.99}
    sim.robots["R1"].outbox.append(bundle(kind="survivor", payload=rec))
    sim.time = 0.1
    sim._move_bundles(DT)
    assert not sim.post.survivors
    sim.time = 0.2
    sim._move_bundles(DT)
    assert sim.post.survivors["S1"]["reported_t"] == 0.2


def test_robot_io_drop_hook_places_relay_at_odometry_position():
    sim = Sim()
    io = sim.ios["R1"]
    rid = io.drop_relay()
    assert sim.relays[rid]["pos"] == list(io.odometry()["pose"][:2])
    assert sim.relays[rid]["owner"] == "R1"
    assert sim.post.view(sim.time)["relays"] == []


def test_seeded_three_robot_state_repeats_after_reset():
    sim = Sim(n_robots=3, seed=7)
    def run():
        sim.add_relay((8, 15), owner="R1")
        for _ in range(100):
            sim.tick()
        return sim.snapshot(), sim.maps(), sim.drain_events()
    first = run()
    sim.reset()
    assert run() == first


@pytest.mark.parametrize("pos", [(-1, 15), (100, 15), (18, 6), (0, 0), (float("nan"), 15)])
def test_relays_cannot_be_placed_outside_safe_floor_space(pos):
    sim = Sim()
    with pytest.raises(ValueError):
        sim.add_relay(pos)
    assert sim.relays == {}
