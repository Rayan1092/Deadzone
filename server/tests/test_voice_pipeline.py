"""Voice provider boundaries, command admission races and delivered-only speech."""
import asyncio
from contextlib import contextmanager
import importlib
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deadzone.command import voice as service
from deadzone.command.plan import PlanError
from deadzone.network.dtn import make_bundle
api = importlib.import_module("deadzone.app")


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("DZ_CONTROL_LEASES","1")
    monkeypatch.setenv("DZ_VOICE","1")
    monkeypatch.setenv("DZ_ROBOTS","3")
    monkeypatch.setenv("DZ_AUTOSTART","0")
    monkeypatch.delenv("GEMINI_API_KEY",raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY",raising=False)
    hub=api.Hub()
    monkeypatch.setattr(api,"hub",hub)
    with TestClient(api.app) as client:
        yield client,hub


@contextmanager
def controller(client, robot="R1"):
    with client.websocket_connect("/ws/phone?client=voice-test") as phone:
        hello=phone.receive_json()["data"]
        assert phone.receive_json()["t"]=="cmd_view"
        headers={"X-Controller-Token":hello["controller_token"]}
        client.post("/api/leases/claim",headers=headers,json={"robot":robot,"name":"Voice test"}).raise_for_status()
        assert phone.receive_json()["t"]=="leases"
        yield phone,headers


def ack_bundle(cmd_id="V-test", **changes):
    payload={"cmd_id":cmd_id,"robot":"R1","cmd":"resume","status":"accepted","eta_s":None,
             "reason":None,"say":"Resuming the search.","state":"EXPLORING","t":1.0,"issued_t":.1}
    payload.update(changes)
    bundle=make_bundle("R1","CMD","command_ack",payload,1.0,220)
    bundle["custodian"]="CMD"
    return bundle


def test_ack_delivery_validation_ordering_bounded_storage_and_copy(session):
    _,hub=session
    post=hub.sim.post
    b=ack_bundle(); b["custodian"]="R1"
    assert not post.receive(b,2) and not post.command_acks
    b["custodian"]="CMD"
    assert post.receive(b,2)
    assert post.command_acks["V-test"]["delay_s"]==1
    assert post.events[-1]["kind"]=="command_ack_reported"
    count=len(post.events)
    assert not post.receive(b,2)  # same network bundle
    assert post.receive(ack_bundle(),2) and len(post.events)==count  # repeat ack in new bundle
    assert post.receive(ack_bundle(status="completed",say="Search completed."),2)
    assert post.receive(ack_bundle(t=1.5),2)
    assert post.command_acks["V-test"]["status"]=="completed"
    for bad in (ack_bundle(robot="R2"),ack_bundle(t=99),ack_bundle(issued_t=5),ack_bundle(eta_s=float("nan"))):
        assert not post.receive(bad,2)
    assert post.receive(ack_bundle("V-refused",cmd="dance",status="refused",reason="bad_command"),2)
    for i in range(260):
        assert post.receive(ack_bundle("V-"+str(i)),2)
    assert len(post.command_acks)==256
    view=post.view(2); view["command_acks"][0]["say"]="edited"
    assert next(iter(post.command_acks.values()))["say"]!="edited"


def test_linked_manual_command_ack_reaches_phones_then_browser_speech(session):
    client,hub=session
    with controller(client) as (phone,headers):
        reply=client.post("/api/robot-command",headers=headers,json={"robot":"R1","action":"hold","request_id":"hold-1"})
        reply.raise_for_status(); result=reply.json(); cid=result["cmd_id"]
        assert result["status"]=="waiting_for_robot" and result["intent_source"]=="manual"
        assert not hub.sim.post.command_acks
        assert client.post("/api/voice/tts",json={"cmd_id":cid}).status_code==404
        for _ in range(8):
            hub.sim.tick()
        assert hub.sim.post.command_acks[cid]["status"]=="accepted"
        client.portal.call(hub.broadcast_tick)
        for _ in range(20):
            frame=phone.receive_json()
            if frame["t"]=="event" and frame["data"]["kind"]=="command_ack_reported":
                assert frame["data"]["cmd_id"]==cid
                break
        else:
            pytest.fail("No delivered ack broadcast")
        spoken=client.post("/api/voice/tts",json={"cmd_id":cid}).json()
        assert spoken["source"]=="browser" and spoken["text"]==hub.sim.post.command_acks[cid]["say"]
        assert "audio" not in spoken


def test_voice_and_manual_share_safety_and_prior_room_resolution(session,monkeypatch):
    client,hub=session
    async def intent(text,rooms):
        assert all(set(r)=={"id","name"} for r in rooms)
        return service.Intent(action="explore_zone",zone="Boiler Room")
    monkeypatch.setattr(service,"parse_intent",intent)
    with controller(client) as (_,headers):
        voiced=client.post("/api/voice",headers=headers,json={"robot":"R1","text":"explore boiler room"})
        manual=client.post("/api/robot-command",headers=headers,json={"robot":"R1","action":"explore_zone","zone":"S2"})
        assert voiced.status_code==manual.status_code==200
        for result in (voiced.json(),manual.json()):
            assert not result["queued"] and result["status"]=="refused"
            assert result["command"]["zone"]["id"]=="S2"
            assert any(v["rule"]=="no_go_overlap" for v in result["safety"]["violations"])
        assert voiced.json()["intent_source"]=="gemini" and manual.json()["intent_source"]=="manual"
        assert not hub.sim.network.queues["CMD"]
        assert client.post("/api/robot-command",headers=headers,json={"robot":"R1","action":"go_to","target":[41,5]}).status_code==422
        assert client.post("/api/robot-command",headers=headers,json={"robot":"R1","action":"explore_zone","zone":"unknown"}).status_code==422
        # Truth occupancy cannot influence admission: only prior + delivered map.
        hub.sim.fp.occ[:]=True
        accepted=client.post("/api/robot-command",headers=headers,json={"robot":"R1","action":"go_to","target":[3.5,15.5]})
        assert accepted.status_code==200 and accepted.json()["queued"]
        ix,iy=hub.sim.prior.to_cell(3.5,15.5); hub.sim.post.map[iy,ix]=2
        refused=client.post("/api/robot-command",headers=headers,json={"robot":"R1","action":"go_to","target":[3.5,15.5]})
        assert not refused.json()["queued"]


@pytest.mark.parametrize("change",["expire","reclaim","reset"])
def test_async_parse_never_queues_after_lease_or_epoch_changes(monkeypatch,change):
    monkeypatch.setenv("DZ_CONTROL_LEASES","1"); monkeypatch.setenv("DZ_VOICE","1")
    hub=api.Hub(); now=[0.0]; hub.leases.clock=lambda:now[0]
    token=hub.leases.register("test"); hub.leases.claim("R1",token,"Test")
    async def run():
        entered,release=asyncio.Event(),asyncio.Event()
        async def parse(*args):
            entered.set(); await release.wait(); return service.Intent(action="hold")
        monkeypatch.setattr(service,"parse_intent",parse)
        task=asyncio.create_task(hub.issue_command("R1",token,text="hold"))
        await entered.wait()
        if change=="expire": now[0]=16
        elif change=="reclaim":
            hub.leases.release("R1",token); hub.leases.claim("R1",token,"Test")
        else: await hub.reset()
        release.set()
        with pytest.raises(PlanError) as error: await task
        assert error.value.code in ("lease_required","lease_changed","voice_reset")
        assert not hub.sim.network.queues["CMD"] and not hub.command_requests
    asyncio.run(run())


def test_retries_are_idempotent_and_concurrent_requests_are_bounded(monkeypatch):
    monkeypatch.setenv("DZ_CONTROL_LEASES","1"); monkeypatch.setenv("DZ_VOICE","1")
    hub=api.Hub(); token=hub.leases.register("test"); hub.leases.claim("R1",token,"Test")
    async def run():
        entered,release=asyncio.Event(),asyncio.Event()
        async def parse(*args):
            entered.set(); await release.wait(); return service.Intent(action="hold")
        monkeypatch.setattr(service,"parse_intent",parse)
        task=asyncio.create_task(hub.issue_command("R1",token,text="hold",request_id="one"))
        await entered.wait()
        with pytest.raises(PlanError,match="processing"):
            await hub.issue_command("R1",token,text="hold",request_id="one")
        with pytest.raises(PlanError) as busy:
            await hub.issue_command("R1",token,text="hold",request_id="two")
        assert busy.value.status==429
        release.set(); result=await task
        assert await hub.issue_command("R1",token,text="hold",request_id="one")==result
        assert len(hub.sim.network.queues["CMD"])==1
        with pytest.raises(PlanError) as conflict:
            await hub.issue_command("R1",token,text="resume",request_id="one")
        assert conflict.value.code=="request_conflict"
    asyncio.run(run())


def test_audio_boundaries_and_real_stt_label(session,monkeypatch):
    client,hub=session
    calls=[]
    async def stt(audio,mime):
        calls.append((audio,mime)); return "hold position"
    async def parse(*args): return service.Intent(action="hold")
    monkeypatch.setattr(service,"transcribe",stt); monkeypatch.setattr(service,"parse_intent",parse)
    assert client.post("/api/voice/audio?robot=R1",content=b"x",headers={"Content-Type":"audio/webm"}).status_code==403
    with controller(client) as (_,headers):
        def post(data,mime="audio/webm"):
            return client.post("/api/voice/audio?robot=R1",content=data,headers={**headers,"Content-Type":mime})
        assert post(b"x","text/plain").status_code==415
        assert post(b"").status_code==422
        assert post(b"x"*(service.MAX_AUDIO+1)).status_code==413
        assert not calls
        response=post(b"fake-test-recording","audio/webm;codecs=opus")
        assert response.status_code==200 and response.json()["stt_source"]=="elevenlabs"
        assert calls==[(b"fake-test-recording","audio/webm")]
        assert len(hub.sim.network.queues["CMD"])==1


def test_provider_requests_are_bounded_and_typed(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY","fake-test-key"); monkeypatch.setenv("ELEVENLABS_API_KEY","fake-test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_R1","test-voice-one")
    seen=[]
    def handler(request):
        seen.append(request)
        if "googleapis" in request.url.host:
            body=json.loads(request.content)
            assert body["generationConfig"]["responseJsonSchema"] and "tools" not in body
            assert set(json.loads(body["contents"][0]["parts"][0]["text"]))=={"utterance","rooms"}
            return httpx.Response(200,json={"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":'{"action":"hold"}'}]}}]})
        if request.url.path=="/v1/speech-to-text":
            assert b"scribe_v2" in request.content and b"test-recording" in request.content
            return httpx.Response(200,json={"text":"hold position"})
        assert request.url.path.endswith("test-voice-one")
        assert json.loads(request.content)["text"]=="Resuming the search."
        return httpx.Response(200,content=b"test-mp3",headers={"Content-Type":"audio/mpeg"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            assert (await service.parse_intent("hold",[{"id":"N1","name":"Office A"}],client=c)).action=="hold"
            assert await service.transcribe(b"test-recording","audio/webm",client=c)=="hold position"
            result=await service.speech(ack_bundle()["payload"],client=c)
            assert result["source"]=="elevenlabs" and result["audio"]["data_base64"]=="dGVzdC1tcDM="
    asyncio.run(run()); assert len(seen)==3


def test_provider_failures_never_invent_an_intent_or_voice(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY","fake-test-key"); monkeypatch.setenv("ELEVENLABS_API_KEY","fake-test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_R1","test-voice-one")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(429))) as c:
            with pytest.raises(PlanError) as e: await service.parse_intent("hold",[],client=c)
            assert e.value.code=="intent_unavailable"
            with pytest.raises(PlanError) as e: await service.transcribe(b"test","audio/webm",client=c)
            assert e.value.code=="stt_unavailable"
            assert (await service.speech(ack_bundle()["payload"],client=c))["source"]=="browser"
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b"wrong-format",headers={"Content-Type":"audio/wav"}))) as c:
            assert (await service.speech(ack_bundle()["payload"],client=c))["source"]=="browser"
        response={"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":'{"action":"hold","robot":"R2"}'}]}}]}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=response))) as c:
            with pytest.raises(PlanError): await service.parse_intent("hold",[],client=c)
        monkeypatch.setattr(service,"PROVIDER_TIMEOUT",.01)
        async def slow(request): await asyncio.sleep(1); return httpx.Response(200)
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as c:
            with pytest.raises(PlanError): await service.parse_intent("hold",[],client=c)
    asyncio.run(run())


@pytest.mark.parametrize("reset",[False,True])
def test_speech_cache_coalesces_and_reset_never_returns_old_audio(monkeypatch,reset):
    monkeypatch.setenv("DZ_VOICE","1")
    hub=api.Hub(); hub.sim.post.receive(ack_bundle(),2)
    async def run():
        entered,release=asyncio.Event(),asyncio.Event(); calls=[]
        async def speak(ack):
            calls.append(ack["cmd_id"]); entered.set(); await release.wait()
            return {"source":"browser","text":ack["say"]}
        monkeypatch.setattr(service,"speech",speak)
        task=asyncio.create_task(hub.delivered_speech("V-test")); await entered.wait()
        if reset:
            await hub.reset(); release.set()
            with pytest.raises(PlanError) as e: await task
            assert e.value.code=="voice_reset" and not hub.speech_cache
        else:
            second=asyncio.create_task(hub.delivered_speech("V-test")); release.set()
            assert await task==await second
            assert await hub.delivered_speech("V-test")==await task
            assert calls==["V-test"]
    asyncio.run(run())
