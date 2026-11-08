"""Aftershock -> rescue route update. Robots only learn about new rubble through lidar; when it
blocks a rescue route the robot already sent, the robot recomputes it on its own map and resends
it as a priority-1 bundle with a newer t, so Command replaces the old route. If nothing gets
through any more, the robot says so once (rescue_route_blocked) and keeps the old route at CMD.

Driven through the real opt-in control path: DZ_AFTERSHOCK=1 and POST /api/control."""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.network.dtn import PRIO  # noqa: E402

api = importlib.import_module("deadzone.app")


def run_aftershock(monkeypatch, point_index, t_shock=19.0, until=60.0):
    """Seed 7, 3 robots, no plan. After S3's route is sent (~18 s), an aftershock lands on its
    point_index-th route point at t_shock. Returns the log, the original route, the hub and bundles."""
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_ROBOTS", "3")
    monkeypatch.setenv("DZ_SEED", "7")
    monkeypatch.setenv("DZ_AFTERSHOCK", "1")
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    sim = hub.sim
    sent = []
    for r in sim.robots.values():
        orig = r._bundle

        def spy(kind, payload, size, _orig=orig):
            b = _orig(kind, payload, size)
            sent.append(b)
            return b
        monkeypatch.setattr(r, "_bundle", spy)
    log, first = [], None
    with TestClient(api.app) as client:
        while sim.time < until:
            sim.tick()
            t = round(sim.time, 1)
            for e in sim.drain_events():
                log.append((t, e))
                if e["kind"] == "rescue_route" and e["survivor"] == "S3" and first is None:
                    first = e
            if t == t_shock:
                assert first is not None, "S3's route is sent before the aftershock"
                at = first["path"][point_index]
                res = client.post("/api/control", json={"action": "director",
                                                        "value": {"do": "aftershock", "at": at}})
                assert res.status_code == 200 and res.json()["ok"]
    # the hub broadcasts the aftershock event itself; the rubble it added is in the floor plan
    shock = next(({"rubble": [r]} for r in sim.fp.data.get("rubble", []) if r["id"].startswith("ASR")), None)
    return log, first, sim, sent, shock


def inside(pt, poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs) <= pt[0] <= max(xs) and min(ys) <= pt[1] <= max(ys)


def test_blocked_route_is_recomputed_and_replaces_the_old_one(monkeypatch):
    log, first, sim, sent, shock = run_aftershock(monkeypatch, point_index=4)
    assert shock is not None
    rubble = shock["rubble"][0]["poly"]
    assert any(inside(p, rubble) for p in first["path"]), "the aftershock lands on the route"
    resent = [(t, e) for t, e in log if e["kind"] == "rescue_route" and e["survivor"] == "S3"
              and e["reason"] == "blocked"]
    assert resent, "the finder saw the rubble on its route and recomputed it"
    t, new = resent[-1]
    assert 19.0 < resent[0][0] <= 25.0, "rerouted within a few seconds of seeing the rubble"
    assert new["robot"] == first["robot"] and new["path"] != first["path"]
    # the final route is clear in the real building: rubble, the new wall and every old wall
    pts = new["path"]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        for k in range(8):
            ix, iy = sim.fp.to_cell(ax + (bx - ax) * k / 8, ay + (by - ay) * k / 8)
            assert not sim.fp.occ[iy, ix], f"route crosses an obstacle near {(ax, ay)}"
    # priority 1, newer t, and Command replaced the route (one route per survivor)
    bundles = [b for b in sent if b["kind"] == "rescue_route" and b["payload"]["survivor"] == "S3"]
    assert all(b["prio"] == PRIO["rescue_route"] == 1 for b in bundles)
    assert bundles[-1]["payload"]["t"] > bundles[0]["payload"]["t"]
    reported = [e for _, e in log if e["kind"] == "rescue_route_reported" and e.get("survivor") == "S3"]
    assert len(reported) >= 2
    routes = [r for r in sim.post.view(sim.time)["routes"] if r["survivor"] == "S3"]
    assert len(routes) == 1 and routes[0]["path"] == bundles[-1]["payload"]["path"]
    assert not any(e["kind"] == "rescue_route_blocked" for _, e in log)


def test_sealed_corridor_reports_blocked_once_and_keeps_the_old_route(monkeypatch):
    log, first, sim, sent, shock = run_aftershock(monkeypatch, point_index=8)
    blocked = [(t, e) for t, e in log if e["kind"] == "rescue_route_blocked"]
    assert [e["survivor"] for _, e in blocked] == ["S3"] and 19.0 < blocked[0][0] <= 25.0
    assert blocked[0][1]["robot"] == first["robot"]
    assert not any(e["kind"] == "rescue_route" and e["reason"] == "blocked" for _, e in log)
    routes = [r for r in sim.post.view(sim.time)["routes"] if r["survivor"] == "S3"]
    assert len(routes) == 1 and routes[0]["path"] == first["path"]


def test_aftershock_stays_opt_in(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.delenv("DZ_AFTERSHOCK", raising=False)
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    with TestClient(api.app) as client:
        res = client.post("/api/control", json={"action": "director", "value": {"do": "aftershock"}})
        assert res.status_code == 409
    assert not any(r.routes for r in hub.sim.robots.values())
