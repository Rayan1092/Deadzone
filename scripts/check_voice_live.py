"""Real loopback voice/manual admission and late DTN ack, with provider keys blank."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

import httpx
from websockets.sync.client import connect


def run(origin):
    checks=[]
    with httpx.Client(base_url=origin,timeout=20,trust_env=False) as http, ExitStack() as stack:
        def post(path,body,headers=None):
            response=http.post(path,json=body,headers=headers)
            response.raise_for_status()
            return response.json()
        def control(action,value=None): return post("/api/control",{"action":action,"value":value})
        def socket(path):
            return stack.enter_context(connect(origin.replace("http://","ws://",1)+path,proxy=None,max_size=8_000_000,max_queue=1024))
        control("reset")
        screen=socket("/ws/screen")
        frames=[json.loads(screen.recv(timeout=15)) for _ in range(4)]
        assert frames[0]["data"]["voice"]["enabled"] and frames[0]["data"]["detector"]=="model"
        screen.close()  # do not leave an unread high-rate screen socket during the long run
        phone=socket("/ws/phone?client=voice-live")
        hello=json.loads(phone.recv(timeout=15))["data"]; phone.recv(timeout=15)
        headers={"X-Controller-Token":hello["controller_token"]}
        def claim(robot): post("/api/leases/claim",{"robot":robot,"name":"Live voice test"},headers)
        def command(robot,action,**extra):
            return post("/api/robot-command",{"robot":robot,"action":action,**extra},headers)
        def ack_for(cmd_id,robot):
            deadline=time.monotonic()+45
            heartbeat=time.monotonic()
            while time.monotonic()<deadline:
                frame=json.loads(phone.recv(timeout=15))
                if time.monotonic()-heartbeat>4:
                    post("/api/leases/heartbeat",{"robot":robot},headers); heartbeat=time.monotonic()
                if frame["t"]=="event" and frame["data"]["kind"]=="command_ack_reported" and frame["data"]["cmd_id"]==cmd_id:
                    return frame["data"]
            raise AssertionError("No delivered acknowledgement")
        claim("R1")
        first=command("R1","hold",request_id="hold-one")
        assert first["queued"] and first["status"]=="waiting_for_robot"
        assert command("R1","hold",request_id="hold-one")==first
        assert http.post("/api/voice/tts",json={"cmd_id":first["cmd_id"]}).status_code==404
        assert http.post("/api/voice",headers=headers,json={"robot":"R1","text":"resume"}).status_code==503
        assert http.post("/api/voice/audio?robot=R1",content=b"test",headers={**headers,"Content-Type":"audio/webm"}).status_code==503
        checks.append("idempotent HTTP command, no early speech, missing-provider errors without fabricated commands")
        control("speed",10); control("start")
        ack=ack_for(first["cmd_id"],"R1")
        assert ack["status"]=="accepted" and ack["state"]=="HOLDING"
        speech=post("/api/voice/tts",{"cmd_id":first["cmd_id"]})
        assert speech["source"]=="browser" and speech["text"]==ack["say"]
        checks.append("actual command radio delivery, robot decision, delivered ack to phone, honest browser TTS fallback")
        control("reset")
        plan={"plan_id":"VOICE-DEMO","author":"voice-live","lost_link_budget_s":60,"no_go":[],"zones":[
            {"id":"ZW","robot":"R1","comms":"relay","poly":[[0,17],[20,17],[20,30],[0,30]]},
            {"id":"ZNE","robot":"R2","comms":"lost_link_ok","poly":[[32,17],[40,17],[40,30],[32,30]]},
            {"id":"ZB","robot":"R3","comms":"relay","poly":[[20,17],[32,17],[32,30],[20,30]]}]}
        post("/api/plan?check=false",plan)
        assert post("/api/dispatch",{"plan_id":"VOICE-DEMO"})["ok"]
        control("start")
        deadline=time.monotonic()+120
        while http.get("/api/health").json()["time"]<125:
            assert time.monotonic()<deadline
            time.sleep(.1)
        control("pause")
        claim("R2")
        queued=command("R2","resume",request_id="dark-resume")
        assert http.post("/api/voice/tts",json={"cmd_id":queued["cmd_id"]}).status_code==404
        control("start")
        late=ack_for(queued["cmd_id"],"R2")
        control("pause")
        assert late["reported_t"]-queued["issued_t"]>10
        assert late["status"]=="accepted"
        checks.append("R2 command issued dark at 125 sim seconds; acknowledgement delivered more than 10 sim seconds later")
        result={"ok":True,"url":origin,"detector":"model","providers":"keys blank; no real Gemini/ElevenLabs calls",
                "checks":checks,"dark_issued_t":queued["issued_t"],"dark_ack_t":late["reported_t"],
                "ack_delay_from_issue_s":round(late["reported_t"]-queued["issued_t"],1)}
        control("reset")
        return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url",default="http://127.0.0.1:8021")
    parser.add_argument("--allow-reset",action="store_true")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args(); parts=urlsplit(args.url)
    if not args.allow_reset or parts.scheme!="http" or parts.hostname not in ("127.0.0.1","localhost","::1") or parts.username or parts.password:
        parser.error("Use a disposable loopback server and --allow-reset")
    result=run(args.url.rstrip("/"))
    if args.output: args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
