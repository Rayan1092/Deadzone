"""Gemini protocol tests with an in-process HTTP transport; never a live key."""
import asyncio
import importlib
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.command import reports
from deadzone.network.dtn import make_bundle
from deadzone.sim import Sim

api = importlib.import_module("deadzone.app")


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("DZ_GEMINI", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)


def model_response(parts, finish="STOP"):
    return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": parts},
                                                   "finishReason": finish}]})


def tool_calls(names=reports.CORE_TOOLS):
    return [{"functionCall": {"name": name, "args": {}, "id": f"call-{i}"},
             "thoughtSignature": f"signature-{i}"} for i, name in enumerate(names)]


def deliver(post, kind, payload, now=1):
    bundle = make_bundle("R1", "CMD", kind, payload, 0, 200)
    bundle.update(custodian="CMD", hops=["R1", "RL1", "CMD"])
    assert post.receive(bundle, now)
    return bundle


def invoke(sim, handler):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await reports.command_report(sim.post, sim.time, client=client)
    return asyncio.run(run())


def test_parallel_tools_then_spoken_reply_preserve_signatures_ids_and_command_boundary():
    sim = Sim()
    sim.tick()
    sim.robots["R1"].found["HIDDEN_SURVIVOR"] = {"id": "HIDDEN_SURVIVOR"}
    sim.robots["R1"].fault = "HIDDEN_FAULT"
    sim.events.append({"kind": "secret_truth_event"})
    requests = []

    def handler(request):
        assert request.headers["x-goog-api-key"] == "test-not-a-real-key"
        assert "key=" not in str(request.url)
        assert reports.DEFAULT_MODEL in str(request.url)
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            initial = json.dumps(body)
            assert '"pose"' not in initial and "HIDDEN" not in initial
            assert body["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"
            assert {d["name"] for d in body["tools"][0]["functionDeclarations"]} == {*reports.CORE_TOOLS, "get_coverage"}
            # Change delivered state while the model waits: all tools stay at request time.
            sim.post.robots["R1"]["state"] = "CHANGED_AFTER_SNAPSHOT"
            return model_response(tool_calls())
        assert body["contents"][1]["parts"] == tool_calls()
        responses = body["contents"][2]["parts"]
        assert len(responses) == 6
        for i, part in enumerate(responses):
            assert part["functionResponse"]["id"] == f"call-{i}"
            assert part["functionResponse"]["response"]["source"] == "command"
        sent = json.dumps(body)
        assert all(secret not in sent for secret in ("HIDDEN_SURVIVOR", "HIDDEN_FAULT", "secret_truth_event", "CHANGED_AFTER_SNAPSHOT"))
        assert body["toolConfig"]["functionCallingConfig"]["mode"] == "AUTO"
        return model_response([{"text": "Private reasoning", "thought": True},
                               {"text": "Command has a recent report from Scout 1. No survivor reports have arrived."}])

    result = invoke(sim, handler)
    assert len(requests) == 2 and result["source"] == "gemini"
    assert "Private reasoning" not in result["text"]
    assert result["generated_at"] == .1


def test_tools_expose_delivered_routes_faults_network_and_events_only():
    sim = Sim()
    post = sim.post
    route = {"survivor": "S1", "by": "R1", "t": 0, "path": [[1, 15], [2, 15]],
             "length_m": 1, "beacon": None, "clearance_m": .5}
    bundle = deliver(post, "rescue_route", route)
    assert not post.receive(bundle, 2)  # dedupe also protects the journal
    deliver(post, "fault", {"robot": "R1", "fault": "STUCK", "t": 0})
    tools = reports.CommandTools(post, 2)
    assert tools.call("get_routes", {})["data"][0]["survivor"] == "S1"
    assert tools.call("get_faults", {})["data"][0]["fault"] == "STUCK"
    network = tools.call("get_network", {})["data"]
    assert network["recent_deliveries"][0]["hops"] == ["R1", "RL1", "CMD"]
    assert network["live_links_known"] is False and "links" not in network
    events = tools.call("get_events", {})["data"]
    assert [e["kind"] for e in events] == ["rescue_route_reported", "fault_reported"]
    assert tools.call("get_events", {"since": 1.5})["data"] == []
    assert tools.call("get_coverage", {})["data"]["known_cells"] == 0
    # Returned data cannot mutate the snapshot or Command.
    tools.call("get_routes", {})["data"][0]["path"][0][0] = 999
    assert tools.call("get_routes", {})["data"][0]["path"][0][0] == 1


@pytest.mark.parametrize("name,args", [("dispatch", {}), ("get_robots", {"truth": True}),
                                        ("get_events", {"since": float("nan")}),
                                        ("get_events", {"since": True})])
def test_tool_allowlist_has_no_mutation_path(name, args):
    with pytest.raises(ValueError):
        reports.CommandTools(Sim().post, 0).call(name, args)


@pytest.mark.parametrize("setting,value", [("DZ_GEMINI", "0"), ("GEMINI_API_KEY", ""),
                                            ("GEMINI_MODEL", "../unsafe")])
def test_disabled_missing_key_or_invalid_model_never_contacts_api(monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    def unexpected(request):
        pytest.fail("Fallback must make no HTTP request")
    assert invoke(Sim(), unexpected)["source"] == "local"


@pytest.mark.parametrize("failure", ["quota", "malformed", "ungrounded", "unknown_tool", "truncated", "empty", "loop"])
def test_api_failures_are_honest_local_fallbacks(failure):
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        if failure == "quota":
            return httpx.Response(429, json={"error": "quota"})
        if failure == "malformed":
            return httpx.Response(200, text="bad json")
        if failure == "unknown_tool":
            return model_response(tool_calls(["dispatch_robot"]))
        if failure == "loop" or (count == 1 and failure in ("truncated", "empty")):
            return model_response(tool_calls())
        return model_response([{"text": "" if failure == "empty" else "Unsupported claims"}],
                              "MAX_TOKENS" if failure == "truncated" else "STOP")
    result = invoke(Sim(), handler)
    assert result["source"] == "local" and "Command briefing" in result["text"]
    assert count <= reports.MAX_ROUNDS


def test_one_deadline_covers_entire_exchange_and_does_not_block_sim_loop(monkeypatch):
    assert reports.REPORT_TIMEOUT_S == 10
    monkeypatch.setattr(reports, "REPORT_TIMEOUT_S", .08)
    hub = api.Hub()
    hub.running, hub.speed = True, 10
    turns = 0
    async def handler(request):
        nonlocal turns
        turns += 1
        await asyncio.sleep(.05)
        return model_response(tool_calls() if turns == 1 else [{"text": "Late result"}])
    async def run():
        loop = asyncio.create_task(hub.loop())
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await reports.command_report(hub.sim.post, hub.sim.time, client=client)
        finally:
            loop.cancel()
            try:
                await loop
            except asyncio.CancelledError:
                pass
    assert asyncio.run(run())["source"] == "local"
    assert hub.sim.tick_n > 1 and turns == 2


def test_report_endpoint_broadcasts_gemini_shape_and_leaves_robots_uncommanded(monkeypatch):
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        return model_response(tool_calls() if count == 1 else [{"text": "No survivor report has arrived."}])
    async def generate(post, now):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await reports.command_report(post, now, client=client)
    monkeypatch.setattr(api, "command_report", generate)
    with TestClient(api.app) as client, client.websocket_connect("/ws/screen") as screen:
        for _ in range(4):
            screen.receive_json()
        result = client.get("/api/report").json()
        assert result["source"] == "gemini"
        message = screen.receive_json()
        assert message["t"] == "report" and message["data"] == result
    assert hub.sim.network.queues["CMD"] == []


def test_sequential_tools_cannot_skip_required_sources():
    requested = []
    def handler(request):
        body = json.loads(request.content)
        config = body["toolConfig"]["functionCallingConfig"]
        if config["mode"] == "ANY":
            name = config["allowedFunctionNames"][0]
            assert name not in requested
            requested.append(name)
            return model_response(tool_calls([name]))
        assert set(requested) == set(reports.CORE_TOOLS)
        return model_response([{"text": "All required Command sources were checked."}])
    assert invoke(Sim(), handler)["source"] == "gemini"


def test_reset_during_api_wait_does_not_broadcast_an_old_incident(monkeypatch):
    hub = api.Hub()
    monkeypatch.setattr(api, "hub", hub)
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    async def reset_in_flight(post, now):
        await hub.control("reset")
        return {"text": "Obsolete incident", "generated_at": now, "source": "gemini"}
    monkeypatch.setattr(api, "command_report", reset_in_flight)
    with TestClient(api.app) as client:
        response = client.get("/api/report")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "report_reset"
