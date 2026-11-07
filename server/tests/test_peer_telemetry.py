"""Peer coordination must obey the same DTN transport as Command reports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.network.dtn import make_bundle  # noqa: E402
from deadzone.network.propagation import LinkGraph  # noqa: E402
from deadzone.robot.robot import PEER_FRESH_S  # noqa: E402
from deadzone.sim import DT, Sim  # noqa: E402


def links(*edges, rssi=-60):
    graph = LinkGraph()
    for a, b in edges:
        edge = tuple(sorted((a, b)))
        graph.up[edge], graph.rssi[edge] = True, rssi
    return graph


def report(sim, size=400):
    payload = {"id": "R1", "pose": [2, 15, 0], "state": "EXPLORING", "battery_pct": 90,
               "target": [8, 15], "relays": [[4, 15]]}
    b = make_bundle("R1", "CMD", "telemetry", payload, sim.time, size)
    sim.robots["R1"].outbox.append(b)
    sim._queue_peer_telemetry({"R1": [b]})
    return b


def advance(sim, graph, now):
    sim.links, sim.time = graph, now
    sim._move_bundles(DT)


def test_fanout_has_unique_bids_frozen_payloads_and_no_self_or_cmd_copy():
    sim = Sim(n_robots=3)
    original = report(sim)
    sim.network.fanout_telemetry(original, ["CMD", "R1", "R2", "R2", "R3"], ttl=PEER_FRESH_S)
    queue = sim.robots["R1"].outbox
    assert len(queue) == 3
    assert {b["dst"] for b in queue} == {"CMD", "R2", "R3"}
    assert len({b["bid"] for b in queue}) == 3
    original["payload"]["target"][0] = 99
    for b in queue[1:]:
        assert b["payload"]["target"] == [8, 15]
        assert b["hops"] == ["R1"] and b["custodian"] == "R1"
        assert b["ttl"] == PEER_FRESH_S
    assert original["ttl"] == 900


def test_each_peer_receives_once_and_no_command_knowledge_is_invented():
    sim = Sim(n_robots=3)
    original = report(sim)
    graph = links(("R1", "R2"), ("R1", "R3"))
    assert not sim.robots["R2"].inbox and not sim.robots["R3"].inbox
    advance(sim, graph, 0.1)
    for rid in ("R2", "R3"):
        assert len(sim.robots[rid].inbox) == 1
        b = sim.robots[rid].inbox[0]
        assert b["dst"] == b["custodian"] == rid
        assert b["hops"] == ["R1", rid]
    assert sim.post.delivered == 0
    sim._queue_peer_telemetry({"R1": [original]})
    advance(sim, graph, 0.2)
    assert len(sim.robots["R2"].inbox) == len(sim.robots["R3"].inbox) == 1


def test_disconnected_peer_gets_nothing_until_reconnection_and_updates_policy():
    sim = Sim(n_robots=2)
    report(sim)
    advance(sim, links(), 0.1)
    assert not sim.robots["R2"].inbox
    assert not sim.robots["R2"].peers
    assert len(sim.robots["R1"].outbox) == 2
    advance(sim, links(("R1", "R2")), 0.2)
    assert not sim.robots["R2"].peers  # onboard policy reads on its next tick
    robot = sim.robots["R2"]
    robot.t = sim.time
    robot._read_inbox()
    assert robot.peers["R1"]["target"] == [8, 15]
    assert robot.peers["R1"]["relays"] == [[4, 15]]
    assert robot._claimed_targets() == [[8, 15]]


def test_relay_takes_custody_and_holds_peer_report_through_outage():
    sim = Sim(n_robots=2)
    relay = sim.add_relay((8, 15))
    sim.network.queues[relay].clear()
    report(sim)
    graph = links(("R1", relay), (relay, "R2"))
    advance(sim, graph, 0.1)
    assert not sim.robots["R2"].inbox
    held = sim.network.queues[relay]
    assert len(held) == 1 and held[0]["custodian"] == relay
    advance(sim, links(("R1", relay)), 0.2)
    assert sim.network.queues[relay] and not sim.robots["R2"].inbox
    advance(sim, graph, 0.3)
    assert sim.robots["R2"].inbox[0]["hops"] == ["R1", relay, "R2"]
    assert not sim.network.queues[relay]
    assert sim.post.delivered == 0


def test_another_robot_cannot_bridge_a_peer_report():
    sim = Sim(n_robots=3)
    report(sim)
    graph = links(("R1", "R3"), ("R3", "R2"))
    for now in (0.1, 0.2, 0.3):
        advance(sim, graph, now)
    assert len(sim.robots["R3"].inbox) == 1  # R3's own destination copy
    assert not sim.robots["R2"].inbox
    assert any(b["dst"] == "R2" for b in sim.robots["R1"].outbox)


def test_offline_peer_claim_expires_but_command_report_survives():
    sim = Sim(n_robots=2)
    original = report(sim)
    advance(sim, links(), PEER_FRESH_S + 0.1)
    assert [b["bid"] for b in sim.robots["R1"].outbox] == [original["bid"]]
    advance(sim, links(("R1", "R2")), PEER_FRESH_S + 0.2)
    assert not sim.robots["R2"].inbox


def test_peer_claim_also_expires_while_held_at_relay():
    sim = Sim(n_robots=2)
    relay = sim.add_relay((8, 15))
    sim.network.queues[relay].clear()
    report(sim)
    graph = links(("R1", relay), (relay, "R2"))
    advance(sim, graph, 0.1)
    assert sim.network.queues[relay]
    advance(sim, links(), PEER_FRESH_S + 0.1)
    assert not sim.network.queues[relay]
    advance(sim, graph, PEER_FRESH_S + 0.2)
    assert not sim.robots["R2"].inbox


def test_survivor_has_priority_and_peer_copy_uses_shared_cmd_link_budget():
    sim = Sim(n_robots=2)
    original = report(sim, size=1000)
    payload = {"id": "S1", "pos": [36, 27], "by": "R1", "t": 0, "conf": 0.99}
    sim.robots["R1"].outbox.append(make_bundle("R1", "CMD", "survivor", payload, 0, 2000))
    graph = links(("R1", "CMD"), ("CMD", "R2"), rssi=-88)  # 2,000 bytes per edge/tick
    advance(sim, graph, 0.1)
    assert sim.post.delivered == 1 and "S1" in sim.post.survivors
    assert len(sim.robots["R1"].outbox) == 2
    advance(sim, graph, 0.2)
    assert sim.post.delivered == 2
    assert sim.network.queues["CMD"][0]["bid"] == original["bid"] + "/R2"
    assert not sim.robots["R2"].inbox
    advance(sim, graph, 0.3)
    assert sim.robots["R2"].inbox[0]["hops"] == ["R1", "CMD", "R2"]
    assert sim.post.delivered == 2  # a transit peer report is not a CMD delivery


def test_link_break_during_large_peer_transfer_keeps_custody_and_retries():
    sim = Sim(n_robots=2)
    report(sim, size=60_000)
    graph = links(("R1", "R2"))  # 25,000 bytes per tick
    advance(sim, graph, 0.1)
    assert not sim.robots["R2"].inbox
    assert any(b["dst"] == "R2" for b in sim.robots["R1"].outbox)
    advance(sim, links(), 0.2)
    advance(sim, graph, 0.3)
    advance(sim, graph, 0.4)
    assert not sim.robots["R2"].inbox
    advance(sim, graph, 0.5)
    assert len(sim.robots["R2"].inbox) == 1


def test_io_receive_combines_plan_and_peer_buffers_without_losing_or_repeating_messages():
    sim = Sim(n_robots=2)
    report(sim)
    plan = make_bundle("CMD", "R2", "plan", {"plan_id": "P1"}, 0, 400)
    sim.network.queues["CMD"].append(plan)
    advance(sim, links(("R1", "R2"), ("CMD", "R2")), 0.1)
    assert len(sim.robots["R2"].inbox) == 1
    assert sim.robots["R2"].inbox[0]["kind"] == "telemetry"
    received = sim.ios["R2"].radio.receive()
    assert [b["kind"] for b in received] == ["plan", "telemetry"]
    assert received[0] == dict(plan, custodian="R2", hops=["CMD", "R2"])
    assert received[1]["src"] == "R1"
    assert sim.ios["R2"].radio.receive() == []
    sim.robots["R2"]._read_inbox()
    assert not sim.robots["R2"].inbox


def test_transport_supports_removal_of_robot_legacy_peer_inbox():
    sim = Sim(n_robots=2)
    del sim.robots["R2"].inbox  # Rayan's future IO-only reader need not keep this attribute
    report(sim)
    advance(sim, links(("R1", "R2")), 0.1)
    received = sim.ios["R2"].radio.receive()
    assert len(received) == 1 and received[0]["kind"] == "telemetry"
    assert received[0]["payload"]["target"] == [8, 15]
    assert sim.ios["R2"].radio.receive() == []


def test_report_size_accounts_for_payload_and_peer_ttl_does_not_extend_source_ttl():
    sim = Sim(n_robots=2)
    b = make_bundle("R1", "CMD", "telemetry", {"id": "R1", "padding": "x" * 2000}, 0, 120, ttl=5)
    sim.robots["R1"].outbox.append(b)
    sim._queue_peer_telemetry({"R1": [b]})
    peer = sim.robots["R1"].outbox[1]
    assert b["size"] == peer["size"] > 2000
    assert b["ttl"] == peer["ttl"] == 5
