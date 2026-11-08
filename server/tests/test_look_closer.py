"""'Unsure, moving closer': a hot spot the onboard detector scores between 0.35 and 0.75 from a
distance is not decided on the spot when a close-up crop exists (ml/crops/runtime/<crop>_close.png).
The robot says so, drives to about 1.4 m of it and judges the close-up; the final verdict carries
both scores. Crops without a close-up, and every demo crop (scores near 0 or 1), behave as before."""
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot import perception  # noqa: E402
from deadzone.robot.perception import CROP_DIR  # noqa: E402
from deadzone.robot.robot import CLOSE_LOOK_M, UNSURE_HI, UNSURE_LO  # noqa: E402
from deadzone.sim import Sim  # noqa: E402

UNSURE_PERSON, UNSURE_OBJECT = "unsure_person_01.png", "unsure_object_01.png"


def building(tmp_path, survivors, decoys):
    data = {"id": "look-closer-test", "name": "Look closer", "size": [16, 10], "cell": 0.25,
            "materials": {"brick": 4, "rubble": 8, "concrete": 16},
            "walls": [{"a": a, "b": b, "material": "concrete"} for a, b in
                      [([0, 0], [16, 0]), ([16, 0], [16, 10]), ([16, 10], [0, 10]), ([0, 10], [0, 6]), ([0, 4], [0, 0])]],
            "doors": [{"at": [0, 5], "width": 2.0, "axis": "y", "state": "open"}],
            "rooms": [{"id": "A", "name": "Hall", "poly": [[0, 0], [16, 0], [16, 10], [0, 10]]}],
            "rubble": [], "hazards": [], "survivors": survivors, "decoys": decoys,
            "entry": [1.0, 5.0], "command_post": {"pos": [-2.0, 5.0], "tx_dbm": 30}}
    path = tmp_path / "b.json"
    path.write_text(json.dumps(data))
    return path


def run(path, seconds):
    """Returns the sim, the event log and (closest approach before the first confirmation, closest
    distance over the whole run) between the robot and any survivor."""
    perception.reset_detector()
    sim = Sim(plan_path=path, n_robots=1, seed=7)
    log, before, overall, confirmed = [], 99.0, 99.0, False
    while sim.time < seconds:
        sim.tick()
        b = sim.bodies["R1"]
        for s in sim.fp.data["survivors"]:
            d = math.dist((b["x"], b["y"]), s["pos"])
            overall = min(overall, d)
            if not confirmed:
                before = min(before, d)
        for e in sim.drain_events():
            log.append((round(sim.time, 1), e))
            confirmed |= e["kind"] == "survivor_found"
    return sim, log, (before, overall)


@pytest.mark.skipif(not (CROP_DIR / UNSURE_PERSON).is_file(), reason="unsure crops not shipped")
def test_unsure_person_is_confirmed_after_a_close_look(tmp_path):
    if perception.get_detector().mode != "model":
        pytest.skip("trained detector unavailable")
    det = perception.get_detector()
    assert UNSURE_LO <= det.score(UNSURE_PERSON) < UNSURE_HI and det.score("unsure_person_01_close.png") >= det.threshold
    path = building(tmp_path, [{"id": "S1", "pos": [5.5, 5.0], "thermal": UNSURE_PERSON}], [])
    sim, log, closest = run(path, 40)
    unsure = next((t, e) for t, e in log if e["kind"] == "hotspot_unsure")
    found = next((t, e) for t, e in log if e["kind"] == "survivor_found")
    assert unsure[1]["id"] == "S1" and UNSURE_LO <= unsure[1]["conf"] < UNSURE_HI
    assert unsure[1]["say"].startswith("AI unsure") and "moving closer" in unsure[1]["say"]
    assert unsure[0] < found[0] <= unsure[0] + 25
    assert found[1]["looked_closer"] and found[1]["conf"] >= det.threshold
    assert found[1]["conf_far"] == unsure[1]["conf"] and found[1]["crop"] == "unsure_person_01_close.png"
    assert not any(e["kind"] == "hotspot_rejected" for _, e in log)
    before, overall = closest
    assert before >= 1.0, "the approach stops short of the person (1.4 m standoff)"
    assert overall >= 0.5, "after confirmation the usual 0.5 m clearance holds"
    assert sim.robots["R1"].counters["detector_unsure"] == 1 and sim.robots["R1"].unsure == {}
    assert "S1" in sim.post.survivors                    # the confirmed report still reaches Command


@pytest.mark.skipif(not (CROP_DIR / UNSURE_OBJECT).is_file(), reason="unsure crops not shipped")
def test_unsure_object_is_rejected_after_a_close_look(tmp_path):
    if perception.get_detector().mode != "model":
        pytest.skip("trained detector unavailable")
    path = building(tmp_path, [{"id": "S9", "pos": [14.5, 1.0], "thermal": "pos_0001.png"}],
                    [{"id": "D1", "label": "engine", "pos": [5.5, 5.0], "thermal": UNSURE_OBJECT}])
    sim, log, _ = run(path, 40)
    unsure = next((t, e) for t, e in log if e["kind"] == "hotspot_unsure")
    rejected = next((t, e) for t, e in log if e["kind"] == "hotspot_rejected")
    assert unsure[1]["id"] == "D1" and rejected[1]["id"] == "D1" and unsure[0] < rejected[0]
    assert rejected[1]["looked_closer"] and rejected[1]["conf"] < perception.get_detector().threshold
    assert "D1" not in sim.robots["R1"].found and "D1" not in sim.post.survivors


def test_without_a_close_up_an_unsure_score_is_decided_at_once(tmp_path, monkeypatch):
    class Half(perception.Passthrough):
        mode, threshold = "model", 0.6

        def score(self, crop_name):
            return 0.5 if crop_name else None

    monkeypatch.setattr(perception, "_detector", Half("test"))
    monkeypatch.setattr(perception, "reset_detector", lambda: None)
    path = building(tmp_path, [{"id": "S1", "pos": [5.5, 5.0], "thermal": "pos_0001.png"}], [])
    sim = Sim(plan_path=path, n_robots=1, seed=7)
    log = []
    while sim.time < 15:
        sim.tick()
        log += sim.drain_events()
    assert not any(e["kind"] == "hotspot_unsure" for e in log)
    assert any(e["kind"] == "hotspot_rejected" and e["id"] == "S1" for e in log)   # 0.5 < 0.6, as before
