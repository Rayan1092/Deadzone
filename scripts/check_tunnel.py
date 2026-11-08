"""Probe one HTTPS origin and WSS without changing the simulation or using keys."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import httpx
from websockets.sync.client import connect


def run(origin, check_leases=False):
    parts = urlsplit(origin)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError("Supply one HTTPS origin, without credentials/path/query")
    origin = origin.rstrip("/")
    checks = []
    with httpx.Client(base_url=origin, timeout=30, trust_env=False) as http, ExitStack() as stack:
        for page in ("/", "/phone", "/mic-check"):
            response = http.get(page)
            response.raise_for_status()
            assert "text/html" in response.headers["content-type"]
            for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', response.text):
                http.get(asset).raise_for_status()
        checks.append("screen/phone/microphone HTML and built assets over HTTPS")
        health = http.get("/api/health")
        health.raise_for_status()
        joined = http.get("/api/join")
        joined.raise_for_status()
        assert joined.json()["url"] == origin + "/phone"
        checks.append("API and QR join use the same HTTPS origin")
        def socket(path):
            return stack.enter_context(connect(origin.replace("https://", "wss://", 1)+path, proxy=None,
                                               max_size=8_000_000, open_timeout=30))
        screen = socket("/ws/screen")
        frames = [json.loads(screen.recv(timeout=30)) for _ in range(4)]
        assert [f["t"] for f in frames] == ["hello", "maps", "tick", "plan_state"]
        phones, tokens = [], []
        for name in ("tunnel-a", "tunnel-b"):
            phone = socket("/ws/phone?client="+name)
            first, view = json.loads(phone.recv(timeout=30)), json.loads(phone.recv(timeout=30))
            assert first["t"] == "hello" and view["t"] == "cmd_view"
            assert "reality" not in view["data"]
            assert not {"survivors", "rubble", "dynamic_walls", "decoys"}.intersection(first["data"]["floorplan"])
            phones.append(phone)
            tokens.append(first["data"].get("controller_token"))
        checks.append("screen + two Command-only phone handshakes over WSS")
        if check_leases:
            assert all(tokens) and tokens[0] != tokens[1]
            a,b = ({"X-Controller-Token": t} for t in tokens)
            claim = http.post("/api/leases/claim", headers=a, json={"robot":"R1","name":"Tunnel test"})
            claim.raise_for_status()  # never override someone else's existing lease
            try:
                assert http.post("/api/leases/claim", headers=b, json={"robot":"R1","name":"Other test"}).status_code == 409
                assert http.post("/api/leases/heartbeat", headers=a, json={"robot":"R1"}).status_code == 200
                command = {"action":"director","value":{"do":"resume","robot":"R1"}}
                assert http.post("/api/control", headers=b, json=command).status_code == 403
                assert http.post("/api/voice", headers=b, json={"robot":"R1","text":"resume"}).status_code == 403
                for phone in phones:
                    frame = json.loads(phone.recv(timeout=30))
                    assert frame["t"] == "leases" and frame["data"]["robots"][0]["controller"]["name"] == "Tunnel test"
                    assert all(token not in json.dumps(frame) for token in tokens)
                checks.append("exclusive lease/heartbeat/broadcast and non-holder manual+voice rejection through HTTPS")
            finally:
                http.post("/api/leases/release", headers=a, json={"robot":"R1"}).raise_for_status()
    return {"ok":True,"origin":origin,"checks":checks,"microphone":"requires manual phone /mic-check test",
            "venue_wifi":"not established by this probe"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--leases", action="store_true", help="claim/release a free R1 for the early dry run")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.url, args.leases)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
