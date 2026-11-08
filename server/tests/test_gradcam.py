"""Grad-CAM heatmaps + crop manifest (ml/gradcam.py) and the heatmap field on robot events."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot import perception  # noqa: E402
from deadzone.sim import Sim  # noqa: E402

RUNTIME = perception.CROP_DIR
MANIFEST = RUNTIME / "manifest.json"


def model_detector():
    det = perception.make_detector()          # honors DETECTOR=sim like the robots do
    if det.mode != "model":
        pytest.skip(f"trained model not loaded ({det.reason})")
    return det


def test_manifest_lists_every_runtime_crop():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    crops = sorted(p.name for p in RUNTIME.glob("*.png"))
    assert sorted(e["file"] for e in m["crops"]) == crops
    fp = json.loads((perception.REPO / "data" / "floorplans" / "collapse_01.json").read_text())
    uses = {s["thermal"]: s["id"] for s in fp["survivors"] + fp["decoys"]}
    for e in m["crops"]:
        assert {"id", "file", "heatmap", "heatmap_alpha", "label", "conf"} <= set(e)
        assert (RUNTIME / e["heatmap"]).is_file() and (RUNTIME / e["heatmap_alpha"]).is_file()
        assert e["id"] == uses.get(e["file"])
        assert e["label"] == ("person" if e["file"].startswith("pos") else "not person")
        assert e["predicted"] == e["label"]        # the runtime props behave as the slide says
        assert 0.0 <= e["conf"] <= 1.0


def test_manifest_conf_matches_the_robot_detector():
    det = model_detector()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for e in m["crops"]:
        assert det.score(e["file"]) == pytest.approx(e["conf"], abs=1e-3)
        assert det.heatmap(e["file"]) == e["heatmap"]
    assert det.heatmap("missing.png") is None and det.heatmap(None) is None


def test_no_heatmap_in_sim_fallback():
    det = perception.make_detector(env={"DETECTOR": "sim"})
    assert det.heatmap("pos_0001.png") is None


def test_gradcam_map_is_normalized():
    det = model_detector()
    ml = str(perception.ML_DIR)
    if ml not in sys.path:
        sys.path.insert(0, ml)
    import gradcam
    from PIL import Image
    x = det.tf(Image.open(RUNTIME / "pos_0001.png")).unsqueeze(0)
    cam, prob = gradcam.gradcam(det.model, x)
    assert cam.shape == (6, 6) and cam.min() >= 0 and cam.max() == pytest.approx(1.0)
    assert prob == pytest.approx(det.score("pos_0001.png"), abs=1e-3)


def test_survivor_found_carries_heatmap_to_command():
    model_detector()
    perception.reset_detector()
    sim = Sim(n_robots=3, seed=7)
    found = None
    while sim.time < 60 and found is None:
        sim.tick()
        found = next((e for e in sim.drain_events() if e["kind"] == "survivor_found"), None)
    assert found is not None, "S3 is found near the entrance in the first ~20 s"
    assert found["heatmap"] == f"heatmaps/{Path(found['crop']).stem}.png"
    for _ in range(50):
        sim.tick()
    assert sim.post.survivors[found["survivor"]]["heatmap"] == found["heatmap"]
