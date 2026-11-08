"""AI Lab export (ml/make_ai_lab.py) matches the format Yusuf asked for in yusuf.md and only
points at files that exist. No torch needed."""
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot.perception import CROP_DIR, ML_DIR  # noqa: E402

RESULTS = ML_DIR / "results"
LAB = json.loads((RESULTS / "lab.json").read_text(encoding="utf-8"))


def test_top_level_shape():
    assert {"model", "metrics", "confusion", "curve", "examples"} <= set(LAB)
    assert {"name", "input_px", "params", "onboard_ms"} <= set(LAB["model"])
    assert {"accuracy", "precision", "recall", "f1", "n_test"} <= set(LAB["metrics"])


def test_metrics_and_confusion_match_eval():
    m = json.loads((RESULTS / "metrics.json").read_text())
    c = m["confusion"]
    assert LAB["confusion"]["labels"] == ["person", "not person"]
    assert LAB["confusion"]["matrix"] == [[c["tp"], c["fn"]], [c["fp"], c["tn"]]]
    assert sum(map(sum, LAB["confusion"]["matrix"])) == LAB["metrics"]["n_test"] == m["n"]
    assert abs(LAB["metrics"]["accuracy"] - m["accuracy"]) < 1e-3


def test_examples_are_12_and_12_and_exist_at_192px():
    ex = LAB["examples"]
    assert sum(e["label"] == "person" for e in ex) == 12
    assert sum(e["label"] == "not person" for e in ex) == 12
    for e in ex:
        assert {"file", "label", "predicted", "conf"} <= set(e)
        path = RESULTS / e["file"]
        assert path.is_file() and Image.open(path).size == (192, 192)
        assert e["predicted"] == ("person" if e["conf"] >= LAB["model"]["threshold"] else "not person")


def test_curve_points_have_all_fields():
    for p in LAB["curve"]:
        assert {"epoch", "train_loss", "val_loss", "train_acc", "val_acc"} <= set(p)
    assert LAB["curve"] or "pending" in LAB["curve_note"]


def test_runtime_crops_point_at_served_files():
    assert len(LAB["runtime"]) == 6
    for e in LAB["runtime"]:
        for key in ("file", "heatmap", "heatmap_alpha"):
            assert e[key].startswith("/crops/")
            assert (CROP_DIR / e[key][len("/crops/"):]).is_file()
