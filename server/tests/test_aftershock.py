"""Opt-in physical collapse: truth changes, Command learns only by delivery."""
import importlib
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.command.reports import CommandTools
from deadzone.network.dtn import DTNNetwork, make_bundle
from deadzone.network.propagation import LinkGraph
from deadzone.sim import Sim

api = importlib.import_module("deadzone.app")


def test_collapse_changes_truth_and_radio_but_not_command_prior_or_robot_maps():
    sim = Sim(n_robots=3)
    sim.tick()
    relay = sim.add_relay((8, 15))
    sim.tick()
    prior = deepcopy(sim.prior.data)
    cmd = deepcopy(sim.post.view(sim.time))
    command_map = sim.post.map.copy()
    robot_maps = {rid: r.map.grid.copy() for rid, r in sim.robots.items()}
    segs = len(sim.fp.segs)
    event = sim.aftershock(relay=relay)
    assert event["destroyed_relay"] == relay
    assert sim.relays[relay]["destroyed"] and not sim.relays[relay]["on"]
    assert sim.network.queues[relay] == [] and relay in sim.network.disabled
    assert len(sim.fp.segs) == segs + 5  # four rubble edges plus new concrete wall
    ix, iy = sim.fp.to_cell(8, 15)
    assert sim.fp.occ[iy, ix]
    assert sim.prior.data == prior and sim.post.view(sim.time) == cmd
    np.testing.assert_array_equal(sim.post.map, command_map)
    for rid in sim.robots:
        np.testing.assert_array_equal(sim.robots[rid].map.grid, robot_maps[rid])
    assert not sim.links.neighbors(relay)
    assert "dynamic_walls" in sim.hello()["floorplan"]
    assert "dynamic_walls" not in sim.fp.planning_data()
    assert all(not wall.get("dynamic") for wall in sim.hello()["floorplan"]["walls"])
    assert not any(e["kind"] == "aftershock" for e in CommandTools(sim.post, sim.time).events)


@pytest.mark.parametrize("at,relay", [((-1, 15), None), ((float("nan"), 15), None),
                                      ((8, 15), "missing")])
def test_invalid_collapse_is_atomic(at, relay):
    sim = Sim()
    before = deepcopy(sim.fp.data)
    with pytest.raises(ValueError):
        sim.aftershock(at, relay)
    assert sim.fp.data == before and not sim.network.disabled


def test_destroyed_relay_cannot_return_and_reset_restores_initial_world():
    sim = Sim()
    rid = sim.add_relay((8, 15))
    sim.aftershock(relay=rid)
    with pytest.raises(ValueError):
        sim.set_relay_power(rid, True)
    with pytest.raises(ValueError):
        sim.move_relay(rid, (9, 15))
    sim.set_relay_power(rid, False)
    with pytest.raises(ValueError):
        sim.aftershock(relay=rid)
    sim.reset()
    assert not sim.relays and not sim.network.disabled
    assert "dynamic_walls" not in sim.fp.data


def test_destruction_loses_only_destroyed_custody_and_reroutes_other_bundles():
    network, links = DTNNetwork(), LinkGraph()
    for node in ("R1", "RL1", "RL2", "CMD"):
        network.register(node)
    for a, b in (("R1", "RL1"), ("RL1", "CMD"), ("R1", "RL2"), ("RL2", "CMD")):
        edge = tuple(sorted((a, b)))
        links.up[edge], links.rssi[edge] = True, -60
    held = make_bundle("R1", "CMD", "survivor", {"id": "S1"}, 0, 400)
    lost = make_bundle("RL1", "CMD", "telemetry", {}, 0, 100)
    network.queues["R1"].append(held)
    network.queues["RL1"].append(lost)
    network._progress[("R1", "RL1", held["bid"])] = 200
    assert network.destroy("RL1") == 1
    # Even a stale graph cannot route through the physically destroyed node.
    assert not network.step(links, .1, .1)
    delivered = network.step(links, .1, .2)
    assert len(delivered) == 1 and delivered[0]["payload"] == {"id": "S1"}
    assert delivered[0]["hops"] == ["R1", "RL2", "CMD"]
    assert not network.queues["RL1"] and not network._progress


def test_director_gate_and_phone_command_boundary(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.delenv("DZ_AFTERSHOCK", raising=False)
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    with TestClient(api.app) as client:
        request = {"action": "director", "value": {"do": "aftershock"}}
        assert client.post("/api/control", json=request).status_code == 409
        assert "dynamic_walls" not in hub.sim.fp.data
        monkeypatch.setenv("DZ_AFTERSHOCK", "1")
        with client.websocket_connect("/ws/phone?client=judge") as phone:
            phone.receive_json()
            phone.receive_json()
            assert client.post("/api/control", json=request).json()["ok"]
            msg = phone.receive_json()
            assert msg["t"] == "cmd_view" and "aftershock" not in str(msg)
            assert "dynamic_walls" not in client.get("/api/floorplan").json()
        bad = {"action": "director", "value": {"do": "aftershock", "relay": "missing"}}
        before = len(hub.sim.fp.data["dynamic_walls"])
        assert client.post("/api/control", json=bad).status_code == 422
        assert len(hub.sim.fp.data["dynamic_walls"]) == before
