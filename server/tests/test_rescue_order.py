import importlib
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.command.rescue_order import rescue_order
from deadzone.network.dtn import make_bundle
from deadzone.sim import Sim

api = importlib.import_module("deadzone.app")


def deliver(sim, kind, payload, now=10):
    bundle = make_bundle("R1", "CMD", kind, payload, 0, 200)
    bundle["custodian"] = "CMD"
    assert sim.post.receive(bundle, now)


def survivor(sim, sid):
    deliver(sim, "survivor", {"id": sid, "by": "R1", "pos": [4,15], "t": 0, "conf": .9})


def route(sim, sid, length=10, clearance=.7, path=None):
    deliver(sim, "rescue_route", {"survivor": sid, "by": "R1", "path": path or [[3,15],[6,15]],
                                 "length_m": length, "clearance_m": clearance, "beacon": None, "t": 0})


def test_only_delivered_survivors_with_delivered_routes_appear():
    sim = Sim()
    survivor(sim, "no-route")
    route(sim, "no-survivor")
    sim.robots["R1"].found["truth-only"] = {"id": "truth-only"}
    assert rescue_order(sim.post, 10, sim.prior)["survivors"] == []
    survivor(sim, "known")
    route(sim, "known")
    before = deepcopy(sim.post.view(10))
    rows = rescue_order(sim.post, 10, sim.prior)["survivors"]
    assert len(rows) == 1 and rows[0]["survivor"] == "known"
    assert rows[0]["risk"] == "low" and not rows[0]["reasons"]
    assert sim.post.view(10) == before


def test_sort_by_risk_length_and_id_and_report_age():
    sim = Sim()
    for sid, length, clearance in (("long-low",20,.7), ("short-medium",1,.4),
                                   ("A",5,.7), ("B",5,.7), ("unknown",1,None), ("high",1,.2)):
        survivor(sim, sid)
        route(sim, sid, length, clearance)
    rows = rescue_order(sim.post, 10, sim.prior)["survivors"]
    assert [s["survivor"] for s in rows] == ["A","B","long-low","short-medium","unknown","high"]
    aged = rescue_order(sim.post, 61, sim.prior)["survivors"]
    assert all("route_older_than_60s" in s["reasons"] for s in aged)


def test_truth_rubble_does_not_change_risk_but_delivered_occupied_cell_does():
    sim = Sim()
    survivor(sim, "S1")
    route(sim, "S1")
    sim.drop_rubble((4.5,15), 1)
    assert rescue_order(sim.post, 10, sim.prior)["survivors"][0]["risk"] == "low"
    ix, iy = sim.prior.to_cell(4.5,15)
    import numpy as np
    deliver(sim, "map_patch", {"ix": np.array([ix]), "iy": np.array([iy]), "v": np.array([2])})
    row = rescue_order(sim.post, 10, sim.prior)["survivors"][0]
    assert row["risk"] == "high" and "reported_route_obstructed" in row["reasons"]


def test_public_hazard_grid_is_reported_without_reading_truth_occupancy():
    sim = Sim()
    survivor(sim, "S1")
    route(sim, "S1", path=[[13,5],[22,5]])
    row = rescue_order(sim.post, 10, sim.prior)["survivors"][0]
    assert row["risk"] == "high" and "known_hazard_on_route" in row["reasons"]


def test_endpoint_gate_and_empty_command_response(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.delenv("DZ_RESCUE_ORDER", raising=False)
    monkeypatch.setattr(api, "hub", api.Hub())
    with TestClient(api.app) as client:
        assert client.get("/api/rescue-order").status_code == 409
        monkeypatch.setenv("DZ_RESCUE_ORDER", "1")
        body = client.get("/api/rescue-order").json()
        assert body == {"generated_at": .1, "source": "command", "survivors": []}
