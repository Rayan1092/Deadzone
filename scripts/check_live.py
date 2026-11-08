"""Real HTTP/WS checks against a disposable local server; resets its simulation."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import httpx
from websockets.sync.client import connect


def receive(ws, kind, predicate=lambda frame: True):
    for _ in range(2000):
        frame = json.loads(ws.recv(timeout=15))
        if frame["t"] == kind and predicate(frame):
            return frame
    raise AssertionError(f"Did not receive {kind}")


def phone_initial(ws):
    hello, view = json.loads(ws.recv(timeout=15)), json.loads(ws.recv(timeout=15))
    assert [hello["t"],view["t"]] == ["hello","cmd_view"]
    assert not {"survivors","decoys","rubble","dynamic_walls"}.intersection(hello["data"]["floorplan"])
    assert "reality" not in view["data"]
    return hello["data"], view["data"]


def run(url, ai_lab=False):
    ws_url = url.replace("http://", "ws://", 1)
    checks = []
    with httpx.Client(base_url=url, timeout=20, trust_env=False) as http, ExitStack() as stack:
        def request(method, path, **kwargs):
            response = http.request(method,path,**kwargs)
            response.raise_for_status()
            return response

        def post(path, body):
            return request("POST",path,json=body).json()

        def socket(path):
            return stack.enter_context(connect(ws_url+path,proxy=None,max_size=8_000_000,max_queue=256))

        post("/api/control",{"action":"reset"})
        health = request("GET","/api/health").json()
        assert not health["running"] and health["tick"] == 1
        for path in ("/","/phone"):
            page = request("GET",path)
            assert "text/html" in page.headers["content-type"]
            for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"',page.text):
                assert request("GET",asset).content
        checks.append("built screen/phone HTML and referenced assets served")
        if ai_lab:
            root = Path(__file__).resolve().parents[1]
            for group, directory, asset in (
                ("results", "ml/results", "metrics.json"),
                ("results", "ml/results", "confusion_matrix.png"),
                ("slides", "docs/assets", "pipeline.png"),
            ):
                url_path = f"/ai-lab/{group}/{asset}"
                response = request("GET", url_path)
                assert response.content == (root / directory / asset).read_bytes()
                assert request("HEAD", url_path).headers["content-length"] == response.headers["content-length"]
                assert http.post(url_path, content=b"overwrite").status_code == 405
            assert http.get("/ai-lab/results/missing.png").status_code == 404
            checks.append("AI Lab GET/HEAD matches exported bytes; mutations/missing assets rejected")
        screen = socket("/ws/screen")
        frames = [json.loads(screen.recv(timeout=15)) for _ in range(4)]
        assert [f["t"] for f in frames] == ["hello","maps","tick","plan_state"]
        assert frames[0]["data"]["detector"] == "model"
        a,b = socket("/ws/phone?client=live-a"),socket("/ws/phone?client=live-b")
        phone_initial(a); phone_initial(b)
        checks.append("trained detector and independent Command-only phone handshakes")

        draft = {"plan_id":"LIVE-CO","author":"live-a","zones":[
            {"id":"Z1","robot":"R1","poly":[[3,14],[6,14],[6,16],[3,16]]}]}
        state = request("PUT","/api/plan-sync",json=draft).json()
        assert state["valid"]
        epoch = state["epoch"]
        a.close(); b.close()  # emulate disconnected clients retaining local operations
        def offline_edit(client, value):
            body = {"epoch":epoch,"plan_id":"LIVE-CO","ops":[{
                "client":client,"counter":1,"target":"plan","field":"lost_link_budget_s","value":value}]}
            return post("/api/plan-sync",body)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda pair: offline_edit(*pair),[("live-a",90),("live-b",120)]))
        assert all(result["valid"] for result in results)
        state = request("GET","/api/plan-sync",params={"plan_id":"LIVE-CO"}).json()
        assert state["plan"]["lost_link_budget_s"] == 120 and len(state["ops"]) == 1
        a,b = socket("/ws/phone?client=live-a"),socket("/ws/phone?client=live-b")
        for phone in (a,b):
            hello,_ = phone_initial(phone)
            assert hello["plan"]["lost_link_budget_s"] == 120
        checks.append("concurrent queued offline operations converge and survive two reconnects")

        demo = {"plan_id":"LIVE-P1","author":"live-a","lost_link_budget_s":60,"no_go":[],"zones":[
            {"id":"ZW","robot":"R1","poly":[[0,17],[20,17],[20,30],[0,30]],"comms":"relay"},
            {"id":"ZNE","robot":"R2","poly":[[32,17],[40,17],[40,30],[32,30]],"comms":"relay"},
            {"id":"ZB","robot":"R3","poly":[[20,17],[32,17],[32,30],[20,30]],"comms":"relay"}]}
        saved = post("/api/plan?check=false",demo)
        assert saved["saved"] and not saved["checked"]
        for phone in (a,b):
            assert json.loads(phone.recv(timeout=15))["t"] == "plan_state"
        a.send(json.dumps({"t":"plan_submit","data":{"plan_id":"LIVE-P1"}}))
        rejected = receive(a,"safety")["data"]
        assert not rejected["ok"] and any(v["rule"] == "comms_plan" for v in rejected["violations"])
        demo["zones"][1]["comms"] = "lost_link_ok"
        post("/api/plan?check=false",demo)
        assert post("/api/dispatch",{"plan_id":"LIVE-P1"})["ok"]
        checks.append("quiet preload, explicit safety rejection, fixed-plan dispatch")
        post("/api/control",{"action":"speed","value":10})
        post("/api/control",{"action":"start"})
        tick = receive(screen,"tick",lambda f:f["time"] >= 20)
        post("/api/control",{"action":"pause"})
        assert all(r["plan_id"] == "LIVE-P1" for r in tick["data"]["reality"]["robots"])
        view = receive(a,"cmd_view",lambda f:f["time"] >= 20)["data"]
        survivor = next(s for s in view["survivors"] if s["id"] == "S3")
        assert request("GET","/crops/"+survivor["crop"]).headers["content-type"].startswith("image/")
        assert request("GET","/crops/"+survivor["heatmap"]).headers["content-type"].startswith("image/")
        checks.append("real model S3 report, crop and Grad-CAM asset delivered through live simulation")

        assert post("/api/control",{"action":"mode","mode":"baseline"})["mode"] == "baseline"
        screen.send(json.dumps({"t":"control","data":{"action":"mode","mode":"deadzone"}}))
        receive(screen,"control",lambda f:f["data"]["mode"] == "deadzone")
        relay = socket("/ws/phone?client=live-relay&role=relay")
        relay_hello,_ = phone_initial(relay)
        receive(relay,"relay_state")
        rid = relay_hello["relay_id"]
        relay.send(json.dumps({"t":"relay_place","data":{"pos":[8,15]}}))
        receive(relay,"relay_state",lambda f:f["data"]["pos"] == [8,15])
        post("/api/control",{"action":"director","value":{"do":"aftershock","at":[8,15],"relay":rid}})
        receive(screen,"hello",lambda f:bool(f["data"]["floorplan"].get("dynamic_walls")))
        damaged = receive(screen,"tick",lambda f:any(r.get("destroyed") for r in f["data"]["reality"]["relays"]))
        assert any(r["id"] == rid and r["destroyed"] and not r["on"] for r in damaged["data"]["reality"]["relays"])
        relay.send(json.dumps({"t":"relay_power","data":{"on":True}}))
        assert receive(relay,"error")["data"]["code"] == "relay_destroyed"
        prior = request("GET","/api/floorplan").json()
        assert "dynamic_walls" not in prior and "rubble" not in prior
        checks.append("mode aliases, live relay placement, aftershock geometry/destruction and no revival")
        report,answer = request("GET","/api/report").json(),post("/api/ask",{"question":"where should team 2 go?"})
        assert report["source"] == answer["source"] == "local"
        ordered = request("GET","/api/rescue-order").json()
        assert ordered["source"] == "command" and any(s["survivor"] == "S3" for s in ordered["survivors"])
        checks.append("honest local G/Ask fallback and delivered rescue-order list (no Gemini API call)")
        post("/api/control",{"action":"reset"})
        for phone in (a,b):
            assert receive(phone,"hello")["data"]["plan"] is None
        stale = http.post("/api/plan-sync",json={"epoch":epoch,"plan_id":"LIVE-CO","ops":[{
            "client":"live-a","counter":2,"target":"plan","field":"lost_link_budget_s","value":30}]})
        assert stale.status_code == 409 and stale.json()["detail"]["code"] == "sync_epoch"
        checks.append("reset clears live clients/drafts and rejects stale offline epoch")
    return {"ok":True,"url":url,"detector":"model","gemini":"disabled; no key used",
            "logical_phone_clients":2,"demo_sim_s_observed":tick["time"],"checks":checks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url",default="http://127.0.0.1:8017")
    parser.add_argument("--allow-reset",action="store_true",help="explicitly allow resetting the disposable local sim")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--ai-lab",action="store_true",help="also check optional DZ_AI_LAB=1 exports")
    args = parser.parse_args()
    parts = urlsplit(args.url)
    if not args.allow_reset or parts.scheme != "http" or parts.hostname not in ("127.0.0.1","localhost","::1"):
        parser.error("Use a disposable loopback HTTP server and --allow-reset")
    result = run(args.url.rstrip("/"), ai_lab=args.ai_lab)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
