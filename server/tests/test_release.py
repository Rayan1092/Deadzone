"""Public setup/launch paths and the shareable environment template."""
import ast
import importlib.util
import os
from pathlib import Path
import subprocess

from dotenv import dotenv_values
import pytest

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location("release_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def installation(tmp_path, module):
    python = tmp_path / ".venv" / ("Scripts/python.exe" if module.sys.platform == "win32" else "bin/python")
    for path in (python, tmp_path / "web/dist/index.html", tmp_path / "ml/models/detector.pt"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (tmp_path / "server").mkdir()
    (tmp_path / "server/.env").write_text("GEMINI_API_KEY=private-never-print\n")
    return python


def test_setup_uses_project_python_cpu_index_and_locked_web_dependencies(tmp_path, monkeypatch, capsys):
    setup = script("setup")
    python = installation(tmp_path, setup)
    calls = []
    monkeypatch.setattr(setup.shutil, "which", lambda _: "npm")
    monkeypatch.setattr(setup.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    before = dict(os.environ)
    assert setup.main([], root=tmp_path) == 0
    assert calls[0][0][:4] == [str(python), "-m", "pip", "install"]
    assert calls[1][0][-2:] == ["--index-url", "https://download.pytorch.org/whl/cpu"]
    assert calls[2][0] == ["npm", "ci"] and calls[3][0] == ["npm", "run", "build"]
    assert "Detector(DEFAULT_MODEL)" in calls[-1][0][-1]
    assert all(c[1]["check"] and not c[1].get("shell") for c in calls)
    assert {key for key in set(before) | set(os.environ) if before.get(key) != os.environ.get(key)} == set()
    assert "private-never-print" not in capsys.readouterr().out


def test_setup_check_is_read_only_and_failure_is_nonzero(tmp_path, monkeypatch):
    setup = script("setup")
    installation(tmp_path, setup)
    calls = []
    monkeypatch.setattr(setup.shutil, "which", lambda _: "npm")
    monkeypatch.setattr(setup.subprocess, "run", lambda args, **kwargs: calls.append(args))
    assert setup.main(["--check"], root=tmp_path) == 0
    assert len(calls) == 1 and "-c" in calls[0]
    def fail(*args, **kwargs): raise subprocess.CalledProcessError(1, "model check")
    monkeypatch.setattr(setup.subprocess, "run", fail)
    assert setup.main(["--check"], root=tmp_path) == 1
    monkeypatch.setattr(setup.shutil, "which", lambda _: None)
    assert setup.main([], root=tmp_path) == 1


def test_fresh_checkout_creates_its_own_environment_before_installing(tmp_path, monkeypatch):
    setup = script("setup")
    model = tmp_path / "ml/models/detector.pt"
    model.parent.mkdir(parents=True)
    model.touch()
    (tmp_path / "server").mkdir()
    (tmp_path / "web").mkdir()
    created, calls = [], []
    class Builder:
        def __init__(self, *, with_pip): assert with_pip
        def create(self, path):
            created.append(path)
            python = setup.python_path(tmp_path)
            python.parent.mkdir(parents=True)
            python.touch()
    monkeypatch.setattr(setup.venv, "EnvBuilder", Builder)
    monkeypatch.setattr(setup.shutil, "which", lambda _: "npm")
    monkeypatch.setattr(setup.subprocess, "run", lambda args, **kwargs: calls.append(args))
    assert setup.main([], root=tmp_path) == 0
    assert created == [tmp_path / ".venv"]
    assert calls[0][0] == str(setup.python_path(tmp_path))


def test_run_uses_the_default_lan_launcher_without_changing_flags(tmp_path, monkeypatch, capsys):
    run = script("run")
    python = installation(tmp_path, run)
    calls = []
    monkeypatch.setattr(run.subprocess, "call", lambda args, **kwargs: calls.append((args, kwargs)) or 0)
    before = dict(os.environ)
    assert run.main(["--port", "8012"], root=tmp_path) == 0
    assert calls == [([str(python), "-m", "deadzone", "--port", "8012"], {"cwd": tmp_path / "server"})]
    assert run.main(["--check"], root=tmp_path) == 0 and len(calls) == 1
    assert {key for key in set(before) | set(os.environ) if before.get(key) != os.environ.get(key)} == set()
    assert "private-never-print" not in capsys.readouterr().out
    (tmp_path / "web/dist/index.html").unlink()
    assert run.main([], root=tmp_path) == 1 and len(calls) == 1


def test_environment_example_is_complete_blank_and_defaults_to_no_extra_flags():
    template = (ROOT / "server/.env.example").read_text(encoding="utf-8")
    assert dotenv_values(ROOT / "server/.env.example") == {"GEMINI_API_KEY": "", "ELEVENLABS_API_KEY": ""}
    settings = set()
    for path in (ROOT / "server/deadzone").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                if value.startswith(("DZ_", "GEMINI_", "ELEVENLABS_", "DETECTOR")) and value.replace("_", "").isalnum():
                    settings.add(value)
    assert all(setting in template for setting in settings)
    assert all(f"ELEVENLABS_VOICE_R{i}=" in template for i in range(1, 10))
    assert subprocess.run(["git", "check-ignore", "--no-index", "-q", "--", "server/.env"], cwd=ROOT).returncode == 0
    assert not subprocess.check_output(["git", "ls-files", "--", "server/.env", ".demo"], cwd=ROOT).strip()
