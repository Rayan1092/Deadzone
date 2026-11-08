"""Preflight must fail closed, avoid leaking keys, and clean up only its child."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("deadzone_preflight", ROOT / "scripts/preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/DEMO.md").write_text('''## Pre-flight checks (T-30 min)
```powershell
$env:DZ_ROBOTS=3; $env:DZ_SEED=7; $env:DZ_SPEED=1.5; $env:DZ_OBSTACLES=1
$env:DZ_GEMINI=1 # enabled
# $env:DZ_VOICE=1
```
## Other
```powershell
$env:DZ_DO_NOT_ALLOW=1
```
''')
    (tmp_path / "server").mkdir()
    (tmp_path / "server/.env").write_text('GEMINI_API_KEY="fake-secret-gemini-do-not-print"\n'
                                         'ELEVENLABS_API_KEY=fake-secret-eleven-do-not-print\n')
    model = tmp_path / "ml/models/detector.pt"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"test-checkpoint")
    python = preflight.venv_python(tmp_path)
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(preflight, "activation_ok", lambda *args: True)
    monkeypatch.setattr(preflight, "python_probe", lambda *args, **kwargs: True)
    monkeypatch.setattr(preflight, "port_free", lambda port: True)
    monkeypatch.setattr(preflight.shutil, "which", lambda command: command)
    monkeypatch.setattr(preflight, "version", lambda command, pattern: "v22.0.0" if command == "node" else "Python 3.12.0")
    calls = []
    monkeypatch.setattr(preflight, "server_probe", lambda *args, **kwargs: calls.append(args) or True)
    env = {"DZ_ROBOTS": "3", "DZ_SEED": "7", "DZ_SPEED": "1.5", "DZ_OBSTACLES": "1", "DZ_GEMINI": "1"}
    return tmp_path, env, calls


def test_runbook_reads_only_active_assignments_in_preflight(setup):
    root, env, _ = setup
    assert preflight.demo_flags(root / "docs/DEMO.md") == env


def test_all_pass_has_one_line_per_check_zero_exit_and_never_echoes_keys(setup, capsys):
    root, env, calls = setup
    assert preflight.run_checks(root, activation="ok", environ=env) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 15 and all(line.startswith("PASS ") for line in lines)
    assert "PASS GEMINI_API_KEY: set" in lines and "PASS ELEVENLABS_API_KEY: set" in lines
    assert "fake-secret" not in "\n".join(lines)
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["key", "model", "torch", "activation", "flag", "extra", "zero_extra",
                                  "port", "cloudflared", "node", "py", "hello", "env_file"])
def test_any_failure_is_nonzero_without_exposing_values(setup, monkeypatch, capsys, kind):
    root, env, calls = setup
    if kind == "key":
        (root / "server/.env").write_text('GEMINI_API_KEY=\nELEVENLABS_API_KEY="   "\n')
    elif kind == "model":
        (root / "ml/models/detector.pt").unlink()
    elif kind == "env_file":
        (root / "server/.env").unlink()
    elif kind == "torch":
        monkeypatch.setattr(preflight, "python_probe", lambda *args, **kwargs: False)
    elif kind == "activation":
        monkeypatch.setattr(preflight, "activation_ok", lambda *args: False)
    elif kind == "flag":
        env["DZ_SPEED"] = "unprinted-value"
    elif kind in ("extra", "zero_extra"):
        env["DZ_PRESENTER_TOKEN"] = "unprinted-value" if kind == "extra" else "0"
    elif kind == "port":
        monkeypatch.setattr(preflight, "port_free", lambda port: port != 8000)
    elif kind == "cloudflared":
        monkeypatch.setattr(preflight.shutil, "which", lambda command: None)
    elif kind in ("node", "py"):
        monkeypatch.setattr(preflight, "version", lambda command, pattern:
            None if command == kind else "v22.0.0" if command == "node" else "Python 3.12.0")
    elif kind == "hello":
        monkeypatch.setattr(preflight, "server_probe", lambda *args, **kwargs: False)
    assert preflight.run_checks(root, activation="ok", environ=env) == 1
    output = capsys.readouterr().out
    assert any(line.startswith("FAIL ") for line in output.splitlines())
    assert all(line.startswith(("PASS ", "FAIL ")) for line in output.splitlines())
    assert "fake-secret" not in output and "unprinted-value" not in output
    if kind == "port":
        assert not calls and "not run: port 8000" in output


def test_dotenv_flags_are_checked_and_process_environment_has_server_precedence(setup, capsys):
    root, env, _ = setup
    with (root / "server/.env").open("a") as file:
        file.write("DZ_SPEED=9\nDZ_GEMINI=0\n")
    assert preflight.run_checks(root, activation="ok", environ=env) == 0
    capsys.readouterr()
    with (root / "server/.env").open("a") as file:
        file.write("DZ_COMPACT_STREAM=0\n")
    assert preflight.run_checks(root, activation="ok", environ=env) == 1
    assert "extra DZ_ flags: DZ_COMPACT_STREAM" in capsys.readouterr().out


def test_busy_tcp_port_is_detected_without_disturbing_its_owner():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        assert not preflight.port_free(listener.getsockname()[1])
        assert not preflight.listener_gone(listener.getsockname()[1], timeout=.01)
        assert listener.fileno() >= 0


def test_cpu_worker_failure_and_timeout_do_not_print_subprocess_output(monkeypatch, capsys):
    monkeypatch.setattr(preflight.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stdout=b"secret", stderr=b"other-secret"))
    assert not preflight.python_probe("python", "bad")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("secret-command", 30, output=b"secret")
    monkeypatch.setattr(preflight.subprocess, "run", timeout)
    assert not preflight.python_probe("python", "bad")
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("mode,listener_closed,expected", [("sim", True, False), ("model", True, True),
                                                         ("model", False, False)])
def test_model_probe_requires_model_hello_and_always_stops_its_own_child(monkeypatch, mode, listener_closed, expected):
    from websockets.sync import client
    class Child:
        def __init__(self): self.stopped = False
        def poll(self): return 0 if self.stopped else None
        def terminate(self): self.stopped = True
        def wait(self, timeout): return 0
    child = Child()
    seen = {}
    def start(*args, **kwargs):
        seen.update(kwargs)
        return child
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def recv(self, **kwargs): return '{"t":"hello","data":{"detector":"' + mode + '","reason":"secret"}}'
    monkeypatch.setattr(preflight.subprocess, "Popen", start)
    monkeypatch.setattr(client, "connect", lambda *args, **kwargs: Socket())
    monkeypatch.setattr(preflight, "stop_process", lambda owned: owned.terminate() or True)
    monkeypatch.setattr(preflight, "listener_gone", lambda port: listener_closed)
    assert preflight.server_probe(ROOT, sys.executable, {"DZ_AUTOSTART": "1"}, seconds=.05) is expected
    assert child.stopped and seen["env"]["DZ_AUTOSTART"] == "0"
    assert seen["stdout"] == subprocess.DEVNULL and seen["stderr"] == subprocess.DEVNULL


@pytest.mark.parametrize("kill_succeeds", [True, False])
def test_windows_cleanup_targets_only_its_owned_tree_and_detects_failure(monkeypatch, kill_succeeds):
    class Child:
        pid = 123456789
        stopped = False
        def poll(self): return 0 if self.stopped else None
        def terminate(self): self.stopped = True
        def wait(self, timeout): return 0
    child, commands = Child(), []
    def taskkill(args, **kwargs):
        commands.append(args)
        assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
        if kill_succeeds:
            child.stopped = True
        return SimpleNamespace(returncode=0 if kill_succeeds else 1)
    monkeypatch.setattr(preflight.subprocess, "run", taskkill)
    assert preflight.stop_process(child, windows=True) is kill_succeeds
    assert child.stopped
    assert commands == [["taskkill", "/PID", str(child.pid), "/T", "/F"]]


def test_env_files_and_backups_are_ignored_but_the_blank_example_is_shareable():
    for path in ("server/.env", "server/.env.backup", "server/.env.local", ".env.production"):
        assert subprocess.run(["git", "check-ignore", "--no-index", "-q", "--", path], cwd=ROOT).returncode == 0
    assert subprocess.run(["git", "check-ignore", "--no-index", "-q", "--", "server/.env.example"], cwd=ROOT).returncode == 1
    assert not subprocess.check_output(["git", "ls-files", "--", "server/.env", ".env"], cwd=ROOT).strip()


def test_invalid_cli_arguments_are_not_echoed_as_possible_secrets():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/preflight.py"),
                             "--activation", "fake-api-key-do-not-print"], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stderr.strip() == "FAIL preflight: invalid arguments"
    assert "fake-api-key" not in result.stdout + result.stderr
