"""Seeded collapsed-building generator (data/floorplans/generate.py, Q&A only)."""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "data" / "floorplans"))

import generate  # noqa: E402
from deadzone.command.rescue import RescueRoute  # noqa: E402
from deadzone.robot.robot import fit_route  # noqa: E402
from deadzone.sim import Sim  # noqa: E402


@pytest.mark.parametrize("seed", range(1, 21))
def test_every_seed_gives_a_valid_building(seed):
    data = generate.generate(seed)
    assert generate.validate(data) == []
    assert data["validation"]["ok"] and data["generator"]["seed"] == seed
    assert len(data["survivors"]) == 3 and len(data["decoys"]) == 3
    assert {r["id"] for r in data["rooms"]} >= {"C1", "E1", "E2"}
    assert all(h["type"] in generate.HAZARDS for h in data["hazards"])
    assert [e["do"] for e in data["timeline"]] == ["rubble", "overcurrent", "aftershock"]
    assert all(s["thermal"] in generate.SURVIVOR_CROPS for s in data["survivors"])


def test_same_seed_same_building_and_seeds_differ():
    a, b = generate.generate(5), generate.generate(5)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert generate.generate(6)["walls"] != a["walls"]


def test_cli_never_overwrites_the_demo_building(tmp_path, monkeypatch):
    demo = ROOT / "data" / "floorplans" / "collapse_01.json"
    before = demo.read_bytes()
    monkeypatch.setattr(sys, "argv", ["generate.py", "--seed", "3", "--out", str(demo)])
    with pytest.raises(SystemExit):
        generate.main()
    assert demo.read_bytes() == before
    monkeypatch.setattr(sys, "argv", ["generate.py", "--seed", "3", "--out", str(tmp_path / "g.json")])
    generate.main()
    assert json.loads((tmp_path / "g.json").read_text())["id"] == "gen_3"


def test_robots_run_a_generated_building_and_its_timeline(tmp_path):
    data = generate.generate(2)
    path = tmp_path / "gen_2.json"
    path.write_text(json.dumps(data))
    sim = Sim(plan_path=path, n_robots=3, seed=7)
    done, kinds, reported = set(), set(), set()
    while sim.time < 240:
        generate.play(sim, data["timeline"], done)
        sim.tick()
        for e in sim.drain_events():
            kinds.add(e["kind"])
            if e["kind"] == "survivor_reported":
                reported.add(e["survivor"])
    assert done == {0, 1, 2}, "every timeline event played"
    assert {"aftershock", "fault"} <= kinds
    assert reported, "robots find and report survivors in a generated building"


def test_long_routes_fit_commands_cap_and_short_ones_are_untouched():
    short = [[1.0 + 0.5 * k, 15.0] for k in range(40)]
    assert fit_route(short) == short
    straight = [[1.0 + 0.5 * k, 15.0] for k in range(100)]        # Command compacts this itself
    assert fit_route(straight) == straight
    zigzag = [[1.0 + 0.5 * k, 15.0 + (0.25 if k % 2 else 0.0)] for k in range(150)]
    fitted = fit_route(zigzag)
    assert len(fitted) <= 60 and fitted[0] == zigzag[0] and fitted[-1] == zigzag[-1]
    route = RescueRoute.model_validate({"survivor": "S1", "by": "R1", "t": 1.0, "path": fitted,
                                        "length_m": 74.5, "beacon": None})
    assert len(route.path) <= 60
    assert max(math.dist(p, q) for p, q in zip(fitted, fitted[1:])) < 5
