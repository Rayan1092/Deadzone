"""Real corrupted bytes, actual RS repairs, CRC rejection and custody retry."""
import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.network.dtn import DTNNetwork, make_bundle
from deadzone.network.fec import DecodeFailure, PayloadCodec
from deadzone.network.propagation import LinkGraph
from deadzone.sim import Sim


def graph(rssi=-85):
    links = LinkGraph()
    links.up[("CMD", "R1")], links.rssi[("CMD", "R1")] = True, rssi
    return links


def network(payload, size=200):
    net = DTNNetwork(fec_enabled=True, seed=7)
    net.register("CMD")
    net.register("R1")
    net.queues["R1"].append(make_bundle("R1", "CMD", "telemetry", payload, 0, size))
    return net


def damage(wire, count):
    out = bytearray(wire)
    for i in range(count):
        out[i] ^= i + 1
    return bytes(out)


def test_real_rs_corrects_sixteen_unknown_byte_errors_and_preserves_numpy_payload():
    codec = PayloadCodec()
    payload = {"ix": np.arange(40, dtype=np.int16), "v": np.ones(40, dtype=np.uint8), "id": "R1"}
    encoded, raw_size = codec.encode(payload)
    assert len(encoded) > raw_size + 32
    decoded, corrected = codec.decode(damage(encoded, 16))
    assert corrected == 16 and decoded["id"] == "R1"
    for key in ("ix", "v"):
        np.testing.assert_array_equal(decoded[key], payload[key])
        assert decoded[key].dtype == payload[key].dtype


def test_uncorrectable_block_is_rejected_not_delivered():
    codec = PayloadCodec()
    encoded, _ = codec.encode({"message": "x" * 180})
    with pytest.raises(DecodeFailure):
        codec.decode(damage(encoded, 24))


def test_crc_catches_valid_codeword_with_wrong_payload_checksum():
    codec = PayloadCodec()
    wire, _ = codec.encode({"message": "known value"})
    packet, _, _ = codec.rs.decode(wire)
    packet[-3] ^= 1
    # Parity is valid but the payload CRC is wrong: this must still be refused.
    with pytest.raises(DecodeFailure):
        codec.decode(bytes(codec.rs.encode(packet)))


def test_failed_hop_retains_custody_then_retry_delivers_decoded_payload(monkeypatch):
    net = network({"message": "x" * 160})
    encoded_corrupt = net.codec.corrupt
    monkeypatch.setattr(net.codec, "corrupt", lambda wire, rssi, rng: (damage(wire, 24), 24))
    assert net.step(graph(), .1, .1) == []
    assert len(net.queues["R1"]) == 1 and not net.queues["CMD"]
    assert net.link_stats[("CMD", "R1")]["fec_failed_blocks"] >= 1
    monkeypatch.setattr(net.codec, "corrupt", encoded_corrupt)
    result = net.step(graph(), .1, .2)
    assert len(result) == 1 and result[0]["payload"] == {"message": "x" * 160}
    assert not net.queues["R1"]
    stats = net.link_stats[("CMD", "R1")]
    assert stats["corrupted_bytes"] > 0 and stats["corrected_bytes"] == stats["corrupted_bytes"]
    assert net.step(graph(), .1, .3) == [] and net.link_stats == {}


def test_partial_hop_charges_parity_and_uses_wire_snapshot_not_source_object(monkeypatch):
    net = network({"message": "original"}, size=500)
    monkeypatch.setattr(net.codec, "corrupt", lambda wire, rssi, rng: (wire, 0))
    assert net.step(graph(), .00001, .1) == []
    frame, padding = next(iter(net._wire.values()))
    assert len(frame) + padding > 500
    net.queues["R1"][0]["payload"]["message"] = "changed after transmission began"
    delivered = net.step(graph(), .1, .2)
    assert delivered[0]["payload"]["message"] == "original"


def test_noise_is_repeatable_without_changing_global_rng():
    codec = PayloadCodec()
    wire, _ = codec.encode({"message": "x" * 2000})
    random.seed(42)
    before = random.getstate()
    a = codec.corrupt(wire, -87, random.Random(7))
    b = codec.corrupt(wire, -87, random.Random(7))
    assert a == b and a[1] > 0 and random.getstate() == before


def test_interrupted_hop_discards_partial_wire_and_sender_keeps_custody():
    net = network({"message": "x" * 1000}, size=2000)
    assert net.step(graph(), .00001, .1) == [] and net._wire
    assert net.step(LinkGraph(), .1, .2) == []
    assert not net._wire and not net._progress and len(net.queues["R1"]) == 1
    assert net.step(graph(), .1, .3)[0]["payload"]["message"] == "x" * 1000


def test_strong_links_and_feature_off_use_legacy_transport_without_coding():
    net = network({"message": "unchanged"})
    assert net.step(graph(-60), .1, .1)[0]["payload"] == {"message": "unchanged"}
    assert not net.link_stats
    assert DTNNetwork().codec is None


def test_tick_stats_are_actual_per_link_and_not_exposed_in_command(monkeypatch):
    monkeypatch.setenv("DZ_FEC", "1")
    sim = Sim()
    sim.links = graph()
    monkeypatch.setattr(sim.network.codec, "corrupt", lambda wire, rssi, rng: (damage(wire, 4), 4))
    sim.network.queues["R1"].append(make_bundle("R1", "CMD", "telemetry", {
        "id": "R1", "pose": [1, 15, 0], "state": "EXPLORING", "battery_pct": 90}, 0, 400))
    sim._move_bundles(.1)
    snap = sim.snapshot()
    link = snap["reality"]["links"][0]
    assert link["fec"] and link["corrupted_bytes"] == link["corrected_bytes"] > 0
    assert sim.snapshot()["reality"]["links"] == snap["reality"]["links"]
    assert "corrected_bytes" not in str(snap["command"])
