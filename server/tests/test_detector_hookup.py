"""Robot perception goes through the trained detector; decoys in the floor plan use negative crops."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FloorPlan  # noqa: E402
from deadzone.robot import perception  # noqa: E402
from deadzone.robot.robot import Robot  # noqa: E402
from deadzone.sim import DEFAULT_PLAN  # noqa: E402


class FakeRadio:
    def cmd_reachable(self):
        return True

    def neighbors(self):
        return []

    def receive(self):
        return []


class FakeIO:
    """Two hot spots in view: a survivor crop and a radiator decoy crop."""
    radio = FakeRadio()

    def thermal(self):
        return [{"id": "S1", "pos": (3.0, 2.0), "crop": "pos_0001.png", "conf": 0.99},
                {"id": "D1", "pos": (3.0, 2.5), "crop": "neg_0001.png", "conf": 0.99}]


def robot():
    return Robot("R1", "Scout 1", "#fff", (2.0, 2.0, 0.0), (40, 40), 0.25, (1.0, 1.0))


def test_floorplan_decoys_point_at_negative_crops():
    fp = FloorPlan.load(DEFAULT_PLAN)
    decoys = fp.data["decoys"]
    assert {d["thermal"] for d in decoys} == {"neg_0001.png", "neg_0002.png", "neg_0003.png"}
    for d in decoys:
        ix, iy = fp.to_cell(*d["pos"])
        assert not fp.occ[iy, ix] and not fp.nogo[iy, ix]


def test_perceive_uses_the_detector():
    perception.reset_detector()
    det = perception.get_detector()
    r = robot()
    r._perceive(FakeIO())
    if det.mode == "sim":
        assert set(r.found) == {"S1", "D1"}       # fallback trusts every hot spot
    else:
        assert set(r.found) == {"S1"}             # the model rejects the radiator
        assert r.found["S1"]["conf"] >= det.threshold


def test_perceive_falls_back_to_sim_sensor(monkeypatch):
    monkeypatch.setenv("DETECTOR", "sim")
    perception.reset_detector()
    try:
        r = robot()
        r._perceive(FakeIO())
        assert set(r.found) == {"S1", "D1"}
    finally:
        perception.reset_detector()


@pytest.fixture(autouse=True)
def _fresh_detector():
    yield
    perception.reset_detector()
