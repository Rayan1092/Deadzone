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
from deadzone.command.plan import PlanManager, SearchPlan  # noqa: E402
from deadzone.command.rescue import RescueRoute  # noqa: E402
from deadzone.command.safety import SafetyChecker  # noqa: E402
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


# ---------------------------------------------------------------- big buildings and default plans
SHOWCASE = ROOT / "data" / "floorplans" / "showcase_01.json"


def centre(poly):
    return [(poly[0][0] + poly[2][0]) / 2, (poly[0][1] + poly[2][1]) / 2]


def test_big_building_has_two_dead_zones_and_a_three_area_earthquake():
    data = generate.generate(1, size=(80, 60))
    assert generate.validate(data) == []
    assert data["size"] == [80.0, 60.0] and data["generator"]["layout"] == "multi_hall"
    assert len(generate.steel_rooms(data)) == 2 and len(data["rooms"]) >= 25
    assert len(data["survivors"]) == 4 and len(data["decoys"]) == 4
    for room in generate.steel_rooms(data):                       # one survivor deep in each dead zone
        assert any(generate.in_poly(s["pos"], room["poly"]) for s in data["survivors"])
        assert not any(generate.in_poly(d["pos"], room["poly"]) for d in data["decoys"])
    shocks = [e for e in data["timeline"] if e["do"] == "aftershock"]
    assert len(shocks) == 3 and shocks[1]["t"] == shocks[0]["t"] + 10
    assert [e["do"] for e in data["timeline"]][:2] == ["rubble", "overcurrent"]
    again = generate.generate(1, size=(80, 60))
    assert json.dumps(again, sort_keys=True) == json.dumps(data, sort_keys=True)


@pytest.mark.parametrize("kw", [dict(seed=1), dict(seed=2), dict(seed=3), dict(seed=1, size=(80, 60))],
                         ids=["gen_1", "gen_2", "gen_3", "big_1"])
def test_default_plan_passes_the_real_safety_checker(tmp_path, kw):
    data = generate.generate(**kw)
    plan = generate.default_plan(data)
    assert plan["plan_id"] == f"P-{data['id']}"
    assert data["default_plan"].startswith("data/plans/") and data["default_plan"].endswith(f"/{data['id']}.plan.json")
    assert {z["robot"] for z in plan["zones"]} == set(generate.ROBOTS)
    dark = [z for z in plan["zones"] if z["comms"] == "lost_link_ok"]
    for room in generate.steel_rooms(data):                       # every dead zone sits in a lost_link_ok zone
        assert any(generate.in_poly(centre(room["poly"]), z["poly"]) for z in dark), room["id"]
    for z in plan["zones"]:                                       # zones never cover a hazard
        for h in data["hazards"]:
            assert not generate.in_poly(centre(h["poly"]), z["poly"]), (z["id"], h["id"])
    path = tmp_path / "b.json"
    path.write_text(json.dumps(data))
    result = generate.check_plan(path, plan)
    assert result["ok"], result["violations"]


def test_showcase_building_on_disk_matches_its_generator_and_plan():
    data = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    g = data["generator"]
    again = generate.generate(g["seed"], size=tuple(data["size"]), plan_id=data["id"], name=data["name"],
                              location="showcase_01")
    assert json.dumps(again, sort_keys=True) == json.dumps(data, sort_keys=True)
    assert generate.validate(data) == [] and len(generate.steel_rooms(data)) == 2
    assert data["size"] == [80.0, 60.0] and sum(e["do"] == "aftershock" for e in data["timeline"]) == 3
    assert data["default_plan"] == "data/plans/showcase_01.plan.json"
    plan = json.loads((ROOT / data["default_plan"]).read_text(encoding="utf-8"))
    assert plan == generate.default_plan(data)
    for name in ("gen_1", "gen_2", "gen_3"):                      # every shipped sample has its plan file
        sample = json.loads((ROOT / "data" / "floorplans" / "generated" / f"{name}.json").read_text(encoding="utf-8"))
        assert sample["default_plan"] == f"data/plans/generated/{name}.plan.json"
        assert (ROOT / sample["default_plan"]).exists()
    # nothing but buildings under data/floorplans/: the server registers every JSON there as a map
    stray = [p for p in (ROOT / "data" / "floorplans").rglob("*.json") if p.name.endswith(".plan.json") or p.name == "index.json"]
    assert stray == []


def test_variants_of_the_demo_building_keep_the_dark_survivor_and_shuffle_the_rest(tmp_path):
    base = json.loads((ROOT / "data" / "floorplans" / "collapse_01.json").read_text(encoding="utf-8"))
    inherited = set(generate.validate(base))                     # collapse_01's own geometry findings
    cage = next(r for r in base["rooms"] if r["id"] == "E2")
    original = tuple(tuple(p["pos"]) for p in base["survivors"] + base["decoys"])
    seen = set()
    for seed in (1, 2, 3):
        v = generate.variant_of(base, seed)
        assert all(v[k] == base[k] for k in ("walls", "doors", "rooms", "hazards", "rubble", "entry", "command_post", "size"))
        assert v["id"] == f"collapse_01_v{seed}" and v["default_plan"] == generate.plan_location(f"variants/{v['id']}")
        assert not (set(generate.validate(v)) - inherited)
        assert generate.in_poly(v["survivors"][0]["pos"], cage["poly"])          # the dark find stays in the cage
        assert [s["thermal"] for s in v["survivors"]] == [s["thermal"] for s in base["survivors"]]
        assert not any(generate.in_poly(d["pos"], cage["poly"]) for d in v["decoys"])
        placement = tuple(tuple(p["pos"]) for p in v["survivors"] + v["decoys"])
        assert placement != original and placement not in seen
        seen.add(placement)
        assert json.dumps(generate.variant_of(base, seed), sort_keys=True) == json.dumps(v, sort_keys=True)
    index = json.loads((ROOT / "data" / "plans" / "variants" / "index.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in index["variants"]] == [f"collapse_01_v{s}" for s in range(1, 6)]
    for e in index["variants"]:                                  # shipped files match the generator
        assert e["scenario"] == f"variants/{e['id']}"           # the id GET /api/scenarios lists (has "variant")
        on_disk = json.loads((ROOT / e["file"]).read_text(encoding="utf-8"))
        again = generate.variant_of(base, on_disk["generator"]["seed"])
        assert json.dumps(on_disk, sort_keys=True) == json.dumps(again, sort_keys=True)
        assert (ROOT / e["default_plan"]).exists()
    v1 = generate.variant_of(base, 1)
    path = tmp_path / "v1.json"
    path.write_text(json.dumps(v1))
    result = generate.check_plan(path, generate.default_plan(v1))
    assert result["ok"], result["violations"]


def test_robots_run_the_showcase_with_its_plan_and_earthquake():
    data = json.loads(SHOWCASE.read_text(encoding="utf-8"))
    plan = generate.default_plan(data)
    sim = Sim(plan_path=SHOWCASE, n_robots=3, seed=7)
    sim.tick()
    manager = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
    manager.save(SearchPlan.model_validate(plan))
    assert manager.dispatch(plan["plan_id"])["ok"]
    done, kinds, found = set(), {}, set()
    while sim.time < data["timeline"][-1]["t"] + 10:            # through the third collapse area
        generate.play(sim, data["timeline"], done)
        sim.tick()
        for e in sim.drain_events():
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
            if e["kind"] == "survivor_found":
                found.add(e["survivor"])
    assert done == set(range(len(data["timeline"]))), "the whole earthquake script played"
    assert kinds.get("aftershock") == 3 and kinds.get("fault")
    assert found, "robots find survivors in the showcase building"
