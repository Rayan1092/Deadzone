"""Exercise real export bytes and opt-in/read-only boundaries through ASGI."""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Mount

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deadzone.ai_lab import AILabAssets

api = importlib.import_module("deadzone.app")
ROOT = Path(__file__).resolve().parents[2]


def test_feature_disabled(monkeypatch):
    monkeypatch.delenv("DZ_AI_LAB", raising=False)
    with TestClient(api.app) as client:
        for path in ("results/metrics.json", "slides/confusion_matrix.png"):
            assert client.get("/ai-lab/" + path).status_code == 404
            assert client.head("/ai-lab/" + path).status_code == 404


@pytest.mark.parametrize("root,asset,media", [
    ("results", "metrics.json", "application/json"),
    ("results", "confusion_matrix.png", "image/png"),
    ("slides", "pipeline.png", "image/png"),
    ("slides", "crops_grid.png", "image/png"),
    ("slides", "stats_card.png", "image/png"),
    ("slides", "benchmark.json", "application/json"),
])
def test_export_bytes_and_head(monkeypatch, root, asset, media):
    monkeypatch.setenv("DZ_AI_LAB", "1")
    directory = ROOT / ("ml/results" if root == "results" else "docs/assets")
    with TestClient(api.app) as client:
        url = f"/ai-lab/{root}/{asset}"
        # Compare HEAD/GET lengths for the same uncompressed representation.
        response = client.get(url, headers={"Accept-Encoding": "identity"})
        assert response.status_code == 200
        assert response.content == (directory / asset).read_bytes()
        assert response.headers["content-type"].startswith(media)
        assert response.headers["cache-control"] == "no-cache"
        head = client.head(url, headers={"Accept-Encoding": "identity"})
        assert head.status_code == 200 and head.content == b""
        assert head.headers["content-length"] == response.headers["content-length"]
        monkeypatch.setenv("DZ_AI_LAB", "0")
        assert client.get(url, headers={"If-None-Match": response.headers["etag"]}).status_code == 404


def test_read_only_and_path_boundaries(monkeypatch, tmp_path):
    monkeypatch.setenv("DZ_AI_LAB", "1")
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "curve.json").write_text('{"epochs": [1]}')
    (exports / "weights.pt").write_bytes(b"not-public")
    (exports / ".private.json").write_text('{"private": true}')
    (tmp_path / "outside.json").write_text('{"outside": true}')
    app = Starlette(routes=[Mount("/exports", app=AILabAssets(directory=exports))])
    with TestClient(app) as client:
        assert client.get("/exports/curve.json").json() == {"epochs": [1]}
        for path in ("", "missing.json", "weights.pt", ".private.json", "%2e%2e%2foutside.json"):
            assert client.get("/exports/" + path).status_code == 404
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert client.request(method, "/exports/curve.json", content=b"overwrite").status_code == 405
        assert (exports / "curve.json").read_text() == '{"epochs": [1]}'


def test_merged_lab_manifest_images_all_resolve(monkeypatch):
    monkeypatch.setenv("DZ_AI_LAB", "1")
    with TestClient(api.app) as client:
        response = client.get("/ai-lab/results/lab.json")
        assert response.status_code == 200
        lab = response.json()
        assert len(lab["examples"]) == 24
        paths = ["/ai-lab/results/" + e["file"] for e in lab["examples"]]
        paths += ["/ai-lab/results/" + lab["assets"]["confusion_png"], *lab["assets"]["slides"]]
        paths += [r[k] for r in lab["runtime"] for k in ("file", "heatmap", "heatmap_alpha") if r.get(k)]
        for path in paths:
            asset = client.get(path)
            assert asset.status_code == 200 and asset.content, path
            assert asset.headers["content-type"].startswith("image/"), path
