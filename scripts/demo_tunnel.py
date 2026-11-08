"""One-origin demo: built web + FastAPI + WebSockets through Cloudflare HTTPS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".demo"


def install_cloudflared():
    installed = shutil.which("cloudflared")
    if installed:
        return Path(installed)
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Install cloudflared using https://developers.cloudflare.com/tunnel/downloads/")
    binary = LOCAL / "bin" / "cloudflared.exe"
    metadata = LOCAL / "cloudflared-release.json"
    if binary.exists() and metadata.exists():
        saved = json.loads(metadata.read_text())
        if hashlib.sha256(binary.read_bytes()).hexdigest() == saved["sha256"]:
            return binary
        raise RuntimeError("Cached cloudflared failed checksum verification; remove .demo/bin/cloudflared.exe and retry")
    with urllib.request.urlopen("https://api.github.com/repos/cloudflare/cloudflared/releases/latest", timeout=30) as reply:
        release = json.load(reply)
    asset = next(a for a in release["assets"] if a["name"] == "cloudflared-windows-amd64.exe")
    digest = asset.get("digest", "")
    url = asset["browser_download_url"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or not url.startswith("https://github.com/cloudflare/cloudflared/releases/download/"):
        raise RuntimeError("Official release lacks a SHA256 digest or has an unexpected download URL")
    binary.parent.mkdir(parents=True, exist_ok=True)
    temporary = binary.with_suffix(".download")
    urllib.request.urlretrieve(url, temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest[7:]:
        temporary.unlink()
        raise RuntimeError("Cloudflare download checksum mismatch")
    temporary.replace(binary)
    metadata.write_text(json.dumps({"version":release["tag_name"], "sha256":digest[7:]}, indent=2))
    return binary


def start(args, **kwargs):
    return subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0, **kwargs)


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--install-only", action="store_true")
    parser.add_argument("--duration", type=float, help="optional seconds after readiness, for a smoke run")
    args = parser.parse_args()
    LOCAL.mkdir(exist_ok=True)
    binary = install_cloudflared()
    if args.install_only:
        subprocess.run([str(binary), "--version"], check=True)
        return
    if not 1 <= args.port <= 65535 or (args.duration is not None and args.duration <= 0):
        parser.error("Use a valid port and positive duration")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))  # fail instead of exposing an unrelated existing service
    if not args.skip_build:
        subprocess.run(["npm.cmd" if sys.platform == "win32" else "npm", "run", "build"], cwd=ROOT / "web", check=True)
    if not (ROOT / "web" / "dist" / "index.html").exists():
        raise RuntimeError("Build web first; web/dist/index.html is missing")
    tunnel = backend = None
    state_path = LOCAL / "tunnel.json"
    state_path.unlink(missing_ok=True)
    try:
        with (LOCAL / "cloudflared.log").open("w", encoding="utf-8") as log:
            tunnel = start([str(binary), "--no-autoupdate", "tunnel", "--url", f"http://127.0.0.1:{args.port}",
                            "--protocol", "http2"], stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        deadline = time.monotonic() + 60
        origin = None
        while time.monotonic() < deadline:
            if tunnel.poll() is not None:
                raise RuntimeError("cloudflared exited; see .demo/cloudflared.log")
            log_text = (LOCAL / "cloudflared.log").read_text(encoding="utf-8", errors="replace")
            found = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", log_text)
            if found:
                origin = found.group()
                break
            time.sleep(.25)
        if not origin:
            raise RuntimeError("No Quick Tunnel URL after 60s; inspect .demo/cloudflared.log and venue firewall")
        env = os.environ.copy()
        env.update(DZ_PUBLIC_URL=origin, DZ_AUTOSTART="0", DZ_ROBOTS="3", DZ_SEED="7", DZ_SPEED="2",
                   DZ_CONTROL_LEASES="1", DZ_VOICE="0", DZ_GEMINI="0")
        env["DZ_PRESENTER_TOKEN"] = env.get("DZ_PRESENTER_TOKEN") or secrets.token_urlsafe(32)
        private_path = LOCAL / "presenter-token.txt"
        fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as private:
            private.write(env["DZ_PRESENTER_TOKEN"])
        with (LOCAL / "backend.log").open("w", encoding="utf-8") as log:
            backend = start([sys.executable, "-m", "uvicorn", "deadzone.app:app", "--host", "127.0.0.1", "--port", str(args.port)],
                            cwd=ROOT / "server", env=env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 60
        while True:
            if backend.poll() is not None:
                raise RuntimeError("Backend exited; see .demo/backend.log")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Backend did not become ready in 60s")
            time.sleep(.25)
        state = {"url":origin, "backend_pid":backend.pid, "tunnel_pid":tunnel.pid, "port":args.port}
        state_path.write_text(json.dumps(state, indent=2))
        print(json.dumps({"url":origin, "phone":origin+"/phone", "microphone_check":origin+"/mic-check",
                          "presenter_token_file":str(private_path), "voice":"off; pipeline pending", "stop":"Ctrl+C"}), flush=True)
        started = time.monotonic()
        while args.duration is None or time.monotonic() - started < args.duration:
            if backend.poll() is not None or tunnel.poll() is not None:
                raise RuntimeError("A demo process exited; inspect .demo logs")
            time.sleep(.25)
    finally:
        stop(tunnel)
        stop(backend)
        state_path.unlink(missing_ok=True)
        (LOCAL / "presenter-token.txt").unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
