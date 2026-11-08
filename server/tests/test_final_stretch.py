"""Final-stretch backend controls: actual mutations, reset ordering and knowledge boundaries."""
import asyncio
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Mount

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deadzone.ai_lab import AILabAssets
from deadzone.command.reports import CommandTools
from deadzone.floorplan import FloorPlan
from deadzone.network.dtn import DTNNetwork, make_bundle
from deadzone.network.propagation import LinkGraph
from deadzone.sim import Sim
from deadzone import scenarios

api = importlib.import_module("deadzone.app")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def hub(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setenv("DZ_ROBOTS", "3")
    monkeypatch.setenv("DZ_FLOORPLAN", "")
    monkeypatch.setenv("DZ_CONTROL_LEASES", "0")
    monkeypatch.setenv("DZ_VOICE", "0")
    monkeypatch.setenv("DZ_SCENARIO_TIMELINE", "1")
    monkeypatch.setenv("DZ_AFTERSHOCK", "1")
    instance = api.Hub()
    monkeypatch.setattr(api, "hub", instance)
    return instance


def fixture_map(tmp_path, monkeypatch, events=None):
    data = json.loads((ROOT / "data/floorplans/collapse_01.json").read_text())
    data.update(id="test_scene", name="Test scenario", timeline=events or [])
    path = tmp_path / "test_scene.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(scenarios, "FLOORPLAN_DIR", tmp_path)
    return path, data


def test_strong_earthquake_changes_three_areas_at_two_times_and_loses_only_two_relays():
    sim = Sim(n_robots=3)
    relays = [sim.add_relay((x, 15)) for x in (8, 12, 16)]
    before = sim.post.view(sim.time)
    maps = {rid: r.map.grid.copy() for rid, r in sim.robots.items()}
    result = sim.earthquake("strong")
    assert result["secondary_at"] == 10
    assert len(sim.fp.data["dynamic_walls"]) == 2
    assert sum(bool(r.get("destroyed")) for r in sim.relays.values()) == 2
    assert sim.post.view(sim.time) == before
    for rid, grid in maps.items():
        np.testing.assert_array_equal(sim.robots[rid].map.grid, grid)
    sim.time = 9.8
    sim.tick()
    assert len(sim.fp.data["dynamic_walls"]) == 2
    sim.tick()
    assert len(sim.fp.data["dynamic_walls"]) == 3
    assert len(sim.pending_aftershocks) == 0
    assert not sim.relays[relays[2]].get("destroyed")
    assert sim.counters["aftershock_areas"] == 3
    assert "aftershock" not in json.dumps(CommandTools(sim.post, sim.time).events)
    sim.reset()
    assert not sim.pending_aftershocks and sim.geometry_revision == 0
    assert sim.counters["aftershock_areas"] == 0


@pytest.mark.parametrize("count", [0, 1, 2])
def test_strong_earthquake_handles_available_relay_count_without_inventing_losses(count):
    sim = Sim()
    for x in range(count):
        sim.add_relay((8 + x*4, 15))
    sim.earthquake("strong")
    assert len(sim.network.disabled) == count
    assert sim.snapshot()["stats"]["relays_destroyed"] == count


def test_bad_or_repeated_strong_request_is_atomic(hub):
    with TestClient(api.app) as client:
        for value in ({"do":"aftershock", "strength":"huge"},
                      {"do":"aftershock", "strength":"strong", "at":[-1, 15]},
                      {"do":"aftershock", "strength":"strong", "relay":"missing"}):
            assert client.post("/api/control", json={"action":"director", "value":value}).status_code == 422
            assert "dynamic_walls" not in hub.sim.fp.data
        good = {"action":"director", "value":{"do":"aftershock", "strength":"strong"}}
        assert client.post("/api/control", json=good).status_code == 200
        before = deepcopy(hub.sim.fp.data)
        assert client.post("/api/control", json=good).status_code == 422
        assert hub.sim.fp.data == before


def test_reset_into_generated_map_is_paused_and_clears_incident_and_lease_state(hub):
    hub.sim.add_relay((8, 15))
    token = hub.leases.register("presenter")
    hub.leases.claim("R1", token, "Presenter")
    hub.running = True
    with TestClient(api.app) as client:
        response = client.post("/api/control", json={"action":"reset", "value":{"floorplan":"generated/gen_1"}})
        assert response.status_code == 200
        assert hub.scenario_id == "generated/gen_1" and hub.sim.fp.data["id"] == "gen_1"
        assert hub.sim.tick_n == 1 and not hub.running
        assert not hub.sim.relays and not hub.leases.leases and hub.plans.current() is None
        assert token in hub.leases.controllers
        client.post("/api/control", json={"action":"reset"}).raise_for_status()
        assert hub.scenario_id == "generated/gen_1"
        assert "timeline" not in client.get("/api/floorplan").json()
        catalog = client.get("/api/scenarios").json()
        assert catalog["selected"] == "generated/gen_1"
        assert all(set(row) == {"id", "name"} for row in catalog["floorplans"])


@pytest.mark.parametrize("selection", [
    {"floorplan":"../../server/.env"}, {"floorplan":"C:/other/file.json"},
    {"floorplan":"missing"}, {"floorplan":"collapse_01", "timeline":"yes"}, {"evil":True},
])
def test_bad_reset_leaves_the_existing_incident_untouched(hub, selection):
    before = hub.sim
    hub.running = True
    with TestClient(api.app) as client:
        response = client.post("/api/control", json={"action":"reset", "value":selection})
        assert response.status_code in (404, 422)
        assert hub.sim is before and hub.running


def test_timeline_is_validated_before_reset_runs_once_in_sim_time_and_clears_on_reset(hub, tmp_path, monkeypatch):
    events = [{"t":.2, "do":"rubble", "at":[10, 15], "label":"hidden future collapse"},
              {"t":.3, "do":"overcurrent", "robot":"R2", "duration_s":1},
              {"t":.4, "do":"aftershock", "at":[20, 15]}]
    fixture_map(tmp_path, monkeypatch, events)
    with TestClient(api.app) as client:
        client.post("/api/control", json={"action":"reset", "value":{"floorplan":"test_scene", "timeline":True}}).raise_for_status()
        player = hub.sim.timeline
        assert player.next == 0  # paused at .1; wall time never advances script events
        for _ in range(4):
            hub.sim.tick()
        assert player.next == 3 and hub.sim.counters["aftershock_areas"] == 1
        assert hub.sim.overcurrent_until["R2"] > hub.sim.time
        count = len(hub.sim.fp.data["rubble"])
        hub.sim.tick()
        assert len(hub.sim.fp.data["rubble"]) == count
        assert "timeline" not in hub.phone_hello("test", "planner")["floorplan"]
        assert "hidden future collapse" not in json.dumps(hub.phone_view())
        client.post("/api/control", json={"action":"reset"}).raise_for_status()
        assert hub.sim.timeline.next == 0
        client.post("/api/control", json={"action":"reset", "value":{"timeline":False}}).raise_for_status()
        assert hub.sim.timeline is None


@pytest.mark.parametrize("event", [
    {"t":-1, "do":"rubble", "at":[8,15]}, {"t":1, "do":"resume", "robot":"R1"},
    {"t":1, "do":"overcurrent", "robot":"R9"}, {"t":1, "do":"rubble", "at":[999,15]},
    {"t":1, "do":"aftershock", "relay":"future-relay"},
])
def test_invalid_script_never_replaces_live_world(hub, tmp_path, monkeypatch, event):
    fixture_map(tmp_path, monkeypatch, [event])
    before = hub.sim
    with TestClient(api.app) as client:
        response = client.post("/api/control", json={"action":"reset", "value":{"floorplan":"test_scene", "timeline":True}})
        assert response.status_code == 422 and hub.sim is before


def test_timeline_feature_gates_and_startup_floorplan_selection(hub, monkeypatch):
    with TestClient(api.app) as client:
        request = {"action":"reset", "value":{"floorplan":"generated/gen_1", "timeline":True}}
        monkeypatch.setenv("DZ_SCENARIO_TIMELINE", "0")
        assert client.post("/api/control", json=request).status_code == 409
        monkeypatch.setenv("DZ_SCENARIO_TIMELINE", "1")
        monkeypatch.setenv("DZ_AFTERSHOCK", "0")
        assert client.post("/api/control", json=request).status_code == 409
    monkeypatch.setenv("DZ_FLOORPLAN", "data/floorplans/generated/gen_2.json")
    startup = api.Hub()
    assert startup.scenario_id == "generated/gen_2" and startup.sim.timeline is None


def test_timeline_failure_after_manual_collapse_does_not_kill_or_retry_loop(hub, tmp_path, monkeypatch):
    fixture_map(tmp_path, monkeypatch, [{"t":.2, "do":"aftershock", "strength":"strong"},
                                      {"t":.3, "do":"overcurrent", "robot":"R2"}])
    asyncio.run(hub.reset({"floorplan":"test_scene", "timeline":True}))
    hub.sim.earthquake("strong")
    for _ in range(4):
        hub.sim.tick()
    stats = hub.sim.snapshot()["stats"]
    assert stats["timeline_events_played"] == 1 and stats["timeline_events_failed"] == 1
    failed = [e for e in hub.sim.events if e["kind"] == "timeline_event_failed"]
    assert len(failed) == 1 and failed[0]["action"] == "aftershock"


def test_sensor_and_transport_counters_are_actual_work_not_snapshot_calls(hub):
    sim = hub.sim
    sim.ios["R1"].lidar()
    sim.ios["R1"].thermal()
    stats = sim.snapshot()["stats"]
    assert stats["lidar_scans"] > 0 and stats["lidar_rays"] > stats["lidar_scans"]
    assert stats["thermal_scans"] > 0 and stats["hop_transfers"] > 0
    assert stats["bytes_transmitted"] > 0 and stats["transport_delivered"] >= stats["delivered"]
    assert stats["command_delivery_hops"] >= stats["delivered"]
    assert stats["hops_per_delivery"] == round(stats["command_delivery_hops"] / stats["delivered"], 3)
    assert sim.snapshot()["stats"] == stats
    assert "stats" not in hub.phone_view()
    assert "bytes_transmitted" not in json.dumps(CommandTools(sim.post, sim.time).call("get_network", {}))


def test_transport_counts_multihop_expiry_and_destruction_once():
    net, links = DTNNetwork(), LinkGraph()
    for node in ("R1", "RL1", "CMD"):
        net.register(node)
    for edge in (("R1", "RL1"), ("CMD", "RL1")):
        links.up[edge], links.rssi[edge] = True, -60
    bundle = make_bundle("R1", "CMD", "telemetry", {}, 0, 100)
    net.queues["R1"].append(bundle)
    assert not net.step(links, .1, .1)
    assert len(net.step(links, .1, .2)) == 1
    assert net.counters["bundles_created"] == 1 and net.counters["hop_transfers"] == 2
    assert net.counters["bytes_transmitted"] == 200 and net.counters["transport_delivered"] == 1
    net.queues["R1"].append(make_bundle("R1", "CMD", "telemetry", {}, 0, 100, ttl=.1))
    net.step(links, .1, .3)
    assert net.counters["bundles_expired"] == 1
    net.queues["RL1"].append(make_bundle("RL1", "CMD", "telemetry", {}, .3, 100))
    net.destroy("RL1")
    assert net.counters["bundles_destroyed"] == 1
    net.destroy("RL1")
    assert net.counters["bundles_destroyed"] == 1


def test_robot_owned_diagnostics_only_aggregate_complete_actual_counters(hub, monkeypatch):
    # Robots report cumulative counters in telemetry (AUDIT #38, rayan.md 03:50): totals are their sums.
    robots = list(hub.sim.robots.values())
    stats = hub.sim.snapshot()["stats"]
    assert stats["detector_calls"] == sum(r.counters["detector_calls"] for r in robots)
    assert stats["scheduler_deadlines_met"] == sum(r.counters["scheduler_deadlines_met"] for r in robots)
    originals = [r.telemetry for r in robots]

    def without_counters(original):
        return lambda link: {k: v for k, v in original(link).items() if k != "counters"}
    for robot, original in zip(robots, originals):
        monkeypatch.setattr(robot, "telemetry", without_counters(original))
    assert "detector_calls" not in hub.sim.snapshot()["stats"], "never invent zeroes"
    for index, (robot, original) in enumerate(zip(robots, originals)):
        monkeypatch.setattr(robot, "telemetry", lambda link, original=original, index=index:
            without_counters(original)(link) | {"counters":{"detector_calls":index+1, "scheduler_deadlines_met":10}})
        stats = hub.sim.snapshot()["stats"]
        if index < 2:
            assert "detector_calls" not in stats
    assert stats["detector_calls"] == 6 and stats["scheduler_deadlines_met"] == 30
    assert "detector_rejections" not in stats


def test_judge_pool_nested_assets_arrive_after_mount_and_are_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DZ_AI_LAB", "1")
    app = Starlette(routes=[Mount("/ai-lab/results", AILabAssets(directory=tmp_path))])
    with TestClient(app) as client:
        assert client.get("/ai-lab/results/judge_pool/manifest.json").status_code == 404
        pool = tmp_path / "judge_pool"
        pool.mkdir()
        (pool / "manifest.json").write_text('{"examples":[]}')
        (pool / "crop.png").write_bytes(b"fixture-image")
        (pool / "model.pt").write_bytes(b"private")
        (pool / ".hidden.json").write_text('{}')
        assert client.get("/ai-lab/results/judge_pool/manifest.json").json() == {"examples":[]}
        assert client.get("/ai-lab/results/judge_pool/crop.png").content == b"fixture-image"
        assert client.head("/ai-lab/results/judge_pool/crop.png").headers["content-length"] == "13"
        for path in ("model.pt", ".hidden.json", "%2e%2e%2f%2e%2e%2foutside.json"):
            assert client.get("/ai-lab/results/judge_pool/" + path).status_code == 404
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert client.request(method, "/ai-lab/results/judge_pool/crop.png").status_code == 405
        monkeypatch.setenv("DZ_AI_LAB", "0")
        assert client.get("/ai-lab/results/judge_pool/manifest.json").status_code == 404


def test_fec_lifetime_counters_survive_empty_ticks_without_double_counting():
    net, links = DTNNetwork(fec_enabled=True, seed=7), LinkGraph()
    for node in ("R1", "CMD"):
        net.register(node)
    links.up[("CMD", "R1")], links.rssi[("CMD", "R1")] = True, -85
    bundle = make_bundle("R1", "CMD", "telemetry", {"data":"x"*500}, 0, 600)
    net.queues["R1"].append(bundle)
    assert len(net.step(links, 1, 1)) == 1
    totals = deepcopy(net.counters)
    assert totals["bytes_transmitted"] > bundle["size"]  # parity uses actual bandwidth
    assert totals["corrupted_bytes"] > 0 and totals["corrected_bytes"] == totals["corrupted_bytes"]
    assert totals["fec_failed_blocks"] == 0
    net.step(links, 1, 2)
    assert net.link_stats == {} and net.counters == totals


def test_hub_loop_publishes_secondary_collapse_geometry_before_tick(hub):
    async def run():
        frames, ready = [], asyncio.Event()
        class Screen:
            async def send_text(self, raw):
                frame = json.loads(raw)
                frames.append(frame)
                if frame["t"] == "tick":
                    ready.set()
        hub.screens.add(Screen())
        hub.sim.earthquake("strong")
        hub.sim.time = 10
        hub.running = True
        task = asyncio.create_task(hub.loop())
        try:
            await asyncio.wait_for(ready.wait(), 2)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        assert frames[0]["t"] == "hello"
        assert len(frames[0]["data"]["floorplan"]["dynamic_walls"]) == 3
        assert next(f for f in frames if f["t"] == "tick")["data"]["stats"]["aftershock_areas"] == 3
    asyncio.run(run())
