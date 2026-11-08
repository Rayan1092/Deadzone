"""Decoy crop pool (Rayan's batch item 4): real held-out FLIR thermal crops per heat-source type in
ml/crops/decoys with a manifest, the detector's false-alarm rate in ml/results/decoy_eval.json and
the Model Lab's lab.json, and the robot's detector able to score a `decoys/<file>` crop."""
import json
from pathlib import Path

import pytest

from deadzone.robot import perception
from deadzone.thermal import HEAT_TYPES

ML = Path(__file__).resolve().parents[2] / "ml"
POOL = ML / "crops" / "decoys"


def test_manifest_covers_every_type_and_files_exist():
    m = json.loads((POOL / "manifest.json").read_text(encoding="utf-8"))
    types = {c["type"] for c in m["crops"]}
    assert types == HEAT_TYPES
    for c in m["crops"]:
        assert (POOL / c["file"]).is_file()
        assert c["split"] in ("images_thermal_val", "video_thermal_test"), "held out: never trained on"
        assert c["verdict"] == ("person" if c["p_person"] >= m["threshold"] else "not a person")
        assert c["real"] == (c["type"] in ("dog", "sunlit")) and ("stand-in" in c["shows"]) != c["real"]
    assert m["false_alarms"] == sum(c["verdict"] == "person" for c in m["crops"])
    assert m["n"] == len(m["crops"])


def test_eval_and_model_lab_agree_with_the_manifest():
    m = json.loads((POOL / "manifest.json").read_text(encoding="utf-8"))
    ev = json.loads((ML / "results" / "decoy_eval.json").read_text(encoding="utf-8"))
    lab = json.loads((ML / "results" / "lab.json").read_text(encoding="utf-8"))["decoys"]
    assert (ev["n"], ev["false_alarms"], ev["false_alarm_rate"]) == (m["n"], m["false_alarms"], m["false_alarm_rate"])
    assert (lab["n"], lab["false_alarms"]) == (m["n"], m["false_alarms"])
    assert {e["type"] for e in lab["examples"]} == HEAT_TYPES
    for e in lab["examples"]:
        assert (ML / "results" / e["file"]).is_file()
        assert e["card"].startswith(e["verdict"].capitalize())


def test_robot_detector_scores_a_decoy_crop_like_the_manifest():
    det = perception.make_detector()
    if det.mode != "model":
        pytest.skip("trained model not loaded")
    m = json.loads((POOL / "manifest.json").read_text(encoding="utf-8"))
    for c in m["crops"][:5] + [c for c in m["crops"] if c["verdict"] == "person"]:
        assert det.score(f"decoys/{c['file']}") == c["p_person"]
    assert det.score("pos_0001.png") is not None, "runtime crops still resolve"
