import importlib.util

import pytest

from deadzone.robot import perception

HIT = {"id": "S1", "pos": (1.0, 2.0), "crop": "pos_0001.png", "conf": 0.99}


def test_sim_env_passthrough():
    det = perception.make_detector(env={"DETECTOR": "sim"})
    assert det.mode == "sim"
    assert perception.filter_hits([HIT], det) == [HIT]


def test_missing_model_passthrough(tmp_path):
    det = perception.make_detector(model_path=tmp_path / "nope.pt", env={})
    assert det.mode == "sim"
    assert perception.filter_hits([HIT, {**HIT, "crop": None}], det) == [HIT, {**HIT, "crop": None}]


def test_default_detector_never_raises():
    perception.reset_detector()
    try:
        out = perception.filter_hits([{"id": "S9", "pos": (0, 0), "crop": None}])
        assert out and out[0]["id"] == "S9"
    finally:
        perception.reset_detector()


HAS_TORCH = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("torchvision") is not None
HAS_MODEL = perception.DEFAULT_MODEL.is_file()


@pytest.mark.skipif(not (HAS_TORCH and HAS_MODEL), reason="needs torch and ml/models/detector.pt")
def test_model_accepts_survivors_rejects_decoys():
    det = perception.make_detector(env={})
    assert det.mode == "model"
    names = sorted(p.name for p in perception.CROP_DIR.glob("*.png"))
    assert any(n.startswith("pos_") for n in names) and any(n.startswith("neg_") for n in names)
    def person(n):
        return n.startswith(("pos_", "unsure_person"))

    def doubtful(n):                                   # distant view of an "unsure, moving closer" pair
        return n.startswith("unsure_") and not n.endswith("_close.png")

    for n in names:
        s = det.score(n)
        assert s is not None
        if doubtful(n):
            assert 0.35 <= s < 0.75, (n, s)
        elif person(n):
            assert s >= det.threshold, (n, s)
        else:
            assert s < det.threshold, (n, s)
    hits = [{**HIT, "id": n, "crop": n} for n in names]
    kept = {h["id"] for h in perception.filter_hits(hits, det)}
    assert kept == {n for n in names if det.score(n) >= det.threshold}
    assert {n for n in names if person(n) and not doubtful(n)} <= kept
    assert not any(n.startswith("neg_") for n in kept)
