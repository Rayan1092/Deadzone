"""Measure actual /ws/screen JSON bytes/messages for 60 wall seconds at speed 2.

Run with the project Python; --compact enables only DZ_COMPACT_STREAM.
Owns a hidden localhost server and stops it on exit. No external APIs are called.
"""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]


def measure(args):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    for key in ("DZ_ROBOT_COLLISIONS", "DZ_OBSTACLES", "DZ_CAMERA_TELEMETRY", "DZ_NETWORK_TRAFFIC",
                "DZ_STREAM_OPTIMIZE", "DZ_COMPACT_STREAM", "DZ_SEARCH_BAYES", "DZ_GLOBAL_NO_GO",
                "DZ_FEC", "DZ_EXPLORATION_V2", "DZ_SENSOR_VIEW", "DZ_AFTERSHOCK",
                "DZ_SCENARIO_TIMELINE", "DZ_CRDT", "DZ_VOICE", "DZ_CONTROL_LEASES",
                "DZ_GEMINI", "DZ_AI_LAB", "DZ_MIC_CHECK", "DZ_AUTOSTART"):
        env[key] = "0"
    env.update(DZ_COMPACT_STREAM="1" if args.compact else "0", DZ_ROBOTS="3", DZ_SEED="7",
               DZ_SPEED="2", DZ_FLOORPLAN="", DZ_MODE="deadzone", DETECTOR="model", DZ_PUBLIC_URL=origin)

    def request(path, data=None):
        req = urllib.request.Request(origin + path,
            data=None if data is None else json.dumps(data).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.load(res)

    log_path = ROOT / ".demo" / ("compact-screen-live.log" if args.compact else "screen-baseline-live.log")
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "deadzone.app:app", "--host",
            "127.0.0.1", "--port", str(port)], cwd=ROOT / "server", env=env, stdout=log,
            stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError(f"Trial server exited; see {log_path}")
                try:
                    if request("/api/health")["ok"]:
                        break
                except OSError:
                    pass
                time.sleep(.2)
            else:
                raise RuntimeError("Trial startup timed out")
            plan = {"plan_id": "P-1", "author": "stream-benchmark", "zones": [
                {"id": "ZW", "robot": "R1", "comms": "relay", "poly": [[0,17],[20,17],[20,30],[0,30]]},
                {"id": "ZNE", "robot": "R2", "comms": "lost_link_ok", "poly": [[32,17],[40,17],[40,30],[32,30]]},
                {"id": "ZB", "robot": "R3", "comms": "relay", "poly": [[20,17],[32,17],[32,30],[20,30]]}],
                "lost_link_budget_s": 60}
            assert request("/api/plan", plan)["ok"]
            assert request("/api/dispatch", {"plan_id": "P-1"})["ok"]
            with connect(origin.replace("http:", "ws:") + "/ws/screen?map_deltas=1", proxy=None,
                         max_size=8_000_000, open_timeout=10) as ws:
                initial = [ws.recv(timeout=10) for _ in range(4)]
                if args.compact:
                    assert json.loads(initial[0])["data"].get("compact_stream"), "Delta negotiation failed"
                capture = args.capture.open("w", encoding="utf-8") if args.capture else None
                counts, sizes = Counter(), Counter()
                last_sim_time = 0
                try:
                    if capture:
                        capture.write("\n".join(initial) + "\n")
                    start = time.monotonic()
                    request("/api/control", {"action": "start"})
                    while True:
                        remaining = args.seconds - (time.monotonic() - start)
                        if remaining <= 0:
                            break
                        try:
                            raw = ws.recv(timeout=remaining)
                        except TimeoutError:
                            break
                        if time.monotonic() - start > args.seconds:
                            break
                        frame = json.loads(raw)
                        counts[frame["t"]] += 1
                        sizes[frame["t"]] += len(raw.encode("utf-8"))
                        last_sim_time = frame["time"]
                        if capture:
                            capture.write(raw + "\n")
                    elapsed = time.monotonic() - start
                    request("/api/control", {"action": "pause"})
                finally:
                    if capture:
                        capture.close()
                result = {"compact": args.compact, "seed": 7, "robots": 3, "speed": 2,
                    "requested_wall_s": args.seconds, "wall_s": round(elapsed, 6), "last_sim_s": last_sim_time,
                    "counts": "UTF-8 JSON application bytes, excludes initial 4 frames and WS/TLS overhead",
                    "messages": sum(counts.values()), "bytes": sum(sizes.values()),
                    "messages_per_s": round(sum(counts.values()) / elapsed, 3),
                    "bytes_per_s": round(sum(sizes.values()) / elapsed, 3),
                    "by_type": {key: {"messages": counts[key], "bytes": sizes[key],
                        "messages_per_s": round(counts[key] / elapsed, 3),
                        "bytes_per_s": round(sizes[key] / elapsed, 3)} for key in counts}}
                text = json.dumps(result, indent=2)
                if args.output:
                    args.output.write_text(text + "\n", encoding="utf-8")
                print(text, flush=True)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--capture", type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("seconds must be positive")
    measure(args)
