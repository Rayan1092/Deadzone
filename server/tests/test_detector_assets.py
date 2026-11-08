"""Published crop URLs and active detector status for every client role."""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
api = importlib.import_module("deadzone.app")


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("DZ_AUTOSTART", "0")
    monkeypatch.setattr(api, "hub", api.Hub())
    with TestClient(api.app) as client:
        yield client


@pytest.mark.parametrize("name", [f"{kind}_{i:04d}.png" for kind in ("pos", "neg") for i in (1, 2, 3)])
def test_crop_images_are_served_as_png_before_spa_fallback(session, name):
    response = session.get(f"/crops/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == (api.CROP_DIR / name).read_bytes()


@pytest.mark.parametrize("path", ["missing.png", "%2e%2e/models/detector.pt", "%2e%2e%5cmodels%5cdetector.pt"])
def test_crop_mount_does_not_expose_other_files(session, path):
    assert session.get(f"/crops/{path}").status_code == 404


@pytest.mark.parametrize("mode", ["model", "sim"])
@pytest.mark.parametrize("role", ["planner", "relay"])
def test_screen_and_phone_hello_report_same_detector_on_connect_and_reset(session, monkeypatch, mode, role):
    monkeypatch.setattr(api, "get_detector", lambda: SimpleNamespace(mode=mode, reason="DETECTOR=sim"))
    with session.websocket_connect("/ws/screen") as screen:
        screen_messages = [screen.receive_json() for _ in range(4)]
        a = screen_messages[0]["data"]
        with session.websocket_connect(f"/ws/phone?client=status&role={role}") as phone:
            b = phone.receive_json()["data"]
            phone.receive_json()
            if role == "relay":
                phone.receive_json()
                # A joining relay refreshes the paused screen without stepping time.
                assert screen.receive_json()["t"] == "tick"
            assert a["detector"] == b["detector"] == mode
            assert "survivors" not in b["floorplan"] and "decoys" not in b["floorplan"]
            if mode == "sim":
                assert a["detector_reason"] == b["detector_reason"] == "DETECTOR=sim"
            else:
                assert "detector_reason" not in a and "detector_reason" not in b
            session.post("/api/control", json={"action": "reset"})
            assert screen.receive_json()["data"]["detector"] == mode
            assert phone.receive_json()["data"]["detector"] == mode
