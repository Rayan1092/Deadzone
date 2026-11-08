"""Every shipped building carries one heat source of each type (Rayan, 2026-11-09), valid for Aziz's
DZ_HEAT_SOURCES parser, reachable, out of hazards, and clear of survivors and decoys."""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data" / "floorplans"))
import generate  # noqa: E402

from deadzone.floorplan import FloorPlan  # noqa: E402
from deadzone.thermal import HEAT_TYPES, heat_spots  # noqa: E402

BUILDINGS = ["collapse_01", "showcase_01"] + [f"variants/collapse_01_v{i}" for i in range(1, 6)] + \
            [f"generated/gen_{i}" for i in range(1, 4)]


@pytest.mark.parametrize("name", BUILDINGS)
def test_heat_sources_are_valid_and_sensible(name):
    data = json.loads((ROOT / "data" / "floorplans" / f"{name}.json").read_text(encoding="utf-8"))
    sources = data["heat_sources"]
    assert sorted(s["type"] for s in sources) == sorted(HEAT_TYPES)
    for s in sources:
        assert set(s) == {"id", "type", "x", "y", "temp_c", "size_m"}, "exactly the agreed schema"
    fp = FloorPlan(data)
    spots = heat_spots(fp, 7)                                   # Aziz's parser accepts every entry
    assert [h["source_id"] for h in spots] == [s["id"] for s in sources]
    reach = generate.reachable(fp)
    people = [p["pos"] for p in data["survivors"] + data.get("decoys", [])]
    for s in sources:
        ix, iy = fp.to_cell(s["x"], s["y"])
        assert reach[iy, ix] and not fp.nogo[iy, ix], f"{name} {s['id']} not reachable or in a hazard"
        assert min(math.dist(p, (s["x"], s["y"])) for p in people) >= 2.0, f"{name} {s['id']} crowds a person"


def test_variants_inherit_the_base_heat_sources():
    base = json.loads((ROOT / "data" / "floorplans" / "collapse_01.json").read_text(encoding="utf-8"))
    for i in range(1, 6):
        v = json.loads((ROOT / "data" / "floorplans" / "variants" / f"collapse_01_v{i}.json").read_text(encoding="utf-8"))
        assert v["heat_sources"] == base["heat_sources"]


def test_generated_buildings_place_heat_sources_without_random_draws():
    data = generate.generate(2)
    assert data["heat_sources"] == generate.place_heat_sources(data)
    assert sorted(s["type"] for s in data["heat_sources"]) == sorted(HEAT_TYPES)


@pytest.mark.parametrize("name", BUILDINGS)
def test_user_facing_text(name):
    """Deployment data pass (Rayan, 2026-11-09): the screen shows names, never file ids."""
    data = json.loads((ROOT / "data" / "floorplans" / f"{name}.json").read_text(encoding="utf-8"))
    assert data["name"] and data["description"] and "_" not in data["name"] and data["name"] != data["id"]
    assert len(data["description"]) <= 220 and "\n" not in data["description"]
    for s in data["survivors"]:
        assert s["id"].startswith("S") and s["descriptor"] and len(s["descriptor"]) <= 60
    for e in data.get("events", []) + data.get("timeline", []):
        assert e.get("label"), f"{name}: every scripted event has banner text"
