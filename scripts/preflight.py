"""Shared, secret-safe checks for preflight.ps1 and preflight.sh."""
import argparse
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("GEMINI_API_KEY", "ELEVENLABS_API_KEY")


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(1, "FAIL preflight: invalid arguments\n")


class Report:
    def __init__(self):
        self.failed = False

    def check(self, name, ok, detail):
        self.failed |= not ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def demo_flags(path):
    """Read assignments from active PowerShell lines, never execute the runbook."""
    text = path.read_text(encoding="utf-8")
    section = re.search(r"(?ms)^## Pre-flight checks[^\n]*\n(.*?)(?=^## |\Z)", text)
    if not section:
        raise ValueError("No pre-flight section")
    expected, powershell = {}, False
    for line in section[1].splitlines():
        if line.strip().startswith("```"):
            powershell = not powershell and line.strip() == "```powershell"
            continue
        if not powershell:
            continue
        active = line.split("#", 1)[0]
        for key, value in re.findall(r"\$env:(DZ_[A-Z0-9_]+)\s*=\s*([^\s;]+)", active):
            value = value.strip("\"'")
            if key in expected and expected[key] != value:
                raise ValueError("Conflicting flag assignments")
            expected[key] = value
    if not {"DZ_ROBOTS", "DZ_SEED", "DZ_SPEED"}.issubset(expected):
        raise ValueError("Missing fixed demo setup")
    return expected


def env_file(path):
    # dotenv warnings and parse failures never echo any file content.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from dotenv import dotenv_values
        return {key: value for key, value in dotenv_values(path).items() if value is not None}


def venv_python(root):
    return root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def activation_ok(root, activation):
    try:
        return (activation == "ok" and Path(sys.prefix).resolve() == (root / ".venv").resolve()
                and Path(os.environ.get("VIRTUAL_ENV", "")).resolve() == (root / ".venv").resolve())
    except OSError:
        return False


def python_probe(python, code, *args, timeout=30):
    try:
        result = subprocess.run([str(python), "-c", code, *map(str, args)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def version(command, pattern):
    try:
        result = subprocess.run([command, "--version"], capture_output=True, text=True,
                                timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        found = re.search(pattern, result.stdout + result.stderr)
        return found[0] if result.returncode == 0 and found else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def port_free(port):
    probes = []
    try:
        for family, address in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
            try:
                probe = socket.socket(family, socket.SOCK_STREAM)
                probes.append(probe)
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                if family == socket.AF_INET6:
                    probe.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                probe.bind((address, port))
            except OSError as error:
                if family == socket.AF_INET6 and error.errno in (errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL):
                    continue
                return False
        return True
    finally:
        for probe in probes:
            probe.close()


def stop_process(process, *, windows=None):
    windows = os.name == "nt" if windows is None else windows
    tree_stopped = True
    if process.poll() is None and windows:
        # Windows .venv/python.exe may redirect to a second interpreter process.
        # Stop the owned tree BEFORE terminating the launcher and losing its children.
        try:
            result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            tree_stopped = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            tree_stopped = False
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    return tree_stopped


def listener_gone(port, timeout=3):
    deadline = time.monotonic() + timeout
    while True:
        with socket.socket() as probe:
            probe.settimeout(.15)
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(.05)


def server_probe(root, python, environ, *, port=8000, seconds=10):
    """Own only this paused probe child, and always stop it, even on Ctrl+C."""
    process, success, cleaned = None, False, True
    try:
        from websockets.sync.client import connect
        child_env = dict(environ, DZ_AUTOSTART="0")
        process = subprocess.Popen([str(python), "-m", "uvicorn", "deadzone.app:app", "--host",
            "127.0.0.1", "--port", str(port)], cwd=root / "server", env=child_env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline, observed = time.monotonic() + seconds, False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return False
            remaining = deadline - time.monotonic()
            if not observed:
                try:
                    with connect(f"ws://127.0.0.1:{port}/ws/screen", proxy=None,
                                 open_timeout=min(1, remaining), max_size=8_000_000) as ws:
                        hello = json.loads(ws.recv(timeout=min(1, remaining)))
                        if hello.get("t") != "hello" or hello.get("data", {}).get("detector") != "model":
                            return False
                        observed = True
                except (OSError, TimeoutError):
                    pass
            time.sleep(min(.1, max(0, deadline - time.monotonic())))
        success = observed and process.poll() is None
    except Exception:
        return False  # never print server output, credentials, payloads or exception text
    finally:
        if process is not None:
            cleaned = stop_process(process) and listener_gone(port)
    return success and cleaned


def run_checks(root=ROOT, *, activation="failed", environ=None):
    report = Report()
    environ = dict(os.environ if environ is None else environ)
    python = venv_python(root)
    active = activation_ok(root, activation)
    report.check(".venv activation", active, "active" if active else "missing or activation failed")
    cpu = python_probe(python, "import torch; assert torch.zeros(1, device='cpu').device.type == 'cpu'")
    report.check("torch", cpu, "CPU import OK" if cpu else "CPU import failed")
    model = root / "ml/models/detector.pt"
    report.check("detector.pt", model.is_file(), "present" if model.is_file() else "missing")
    loaded = model.is_file() and python_probe(python,
        "import sys, torch; torch.set_num_threads(1); sys.path.insert(0, sys.argv[1]); from common import load_checkpoint; "
        "model, _ = load_checkpoint(sys.argv[2], 'cpu'); "
        "assert next(model.parameters()).device.type == 'cpu'; "
        "result = model(torch.zeros(1, 3, 96, 96)); "
        "assert tuple(result.shape) == (1, 2) and torch.isfinite(result).all()",
        root / "ml", model)
    report.check("detector.pt load", loaded, "CPU load OK" if loaded else "CPU load failed")
    path = root / "server/.env"
    exists = path.is_file()
    report.check("server/.env", exists, "present" if exists else "missing")
    try:
        values = env_file(path) if exists else {}
    except Exception:
        values = {}
    for key in KEYS:
        set_key = bool(values.get(key, "").strip())
        report.check(key, set_key, "set" if set_key else "missing")
    # Match load_dotenv(override=False): process variables override the file.
    effective = {**values, **environ}
    try:
        expected = demo_flags(root / "docs/DEMO.md")
        bad = [key for key, value in expected.items() if effective.get(key) != value]
        report.check("DEMO flags", not bad, "match" if not bad else "missing/mismatch " + ", ".join(sorted(bad)))
        extra = sorted(re.sub(r"[^A-Za-z0-9_]", "?", key) for key, value in effective.items()
                       if key.startswith("DZ_") and key not in expected and value)
        report.check("extra DZ_ flags", not extra, "none" if not extra else ", ".join(extra))
    except Exception:
        report.check("DEMO flags", False, "runbook assignments unavailable")
        report.check("extra DZ_ flags", False, "runbook assignments unavailable")
    ports = {port: port_free(port) for port in (8000, 5173)}
    for port, free in ports.items():
        report.check(f"port {port}", free, "free" if free else "busy/unavailable")
    tunnel = shutil.which("cloudflared") is not None
    report.check("cloudflared PATH", tunnel, "found" if tunnel else "missing")
    node = version("node", r"v\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?")
    report.check("node version", node is not None, node or "missing/unavailable")
    launcher = "py" if os.name == "nt" or shutil.which("py") else "python3"
    py = version(launcher, r"Python \d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)")
    report.check("py version" if launcher == "py" else "python3 version", py is not None, py or "missing/unavailable")
    if not ports[8000]:
        report.check("server hello (10 s)", False, "not run: port 8000 busy/unavailable")
    elif not python.is_file():
        report.check("server hello (10 s)", False, "not run: .venv Python missing")
    else:
        hello = server_probe(root, python, effective)
        report.check("server hello (10 s)", hello, "detector=model" if hello else "real model not confirmed")
    return int(report.failed)


if __name__ == "__main__":
    parser = SafeParser(description=__doc__)
    parser.add_argument("--activation", choices=("ok", "failed"), default="failed")
    args = parser.parse_args()
    try:
        raise SystemExit(run_checks(activation=args.activation))
    except KeyboardInterrupt:
        print("FAIL preflight: interrupted", flush=True)
        raise SystemExit(1)
    except Exception:
        print("FAIL preflight: unavailable", flush=True)
        raise SystemExit(1)
