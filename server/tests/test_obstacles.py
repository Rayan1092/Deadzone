"""Static shelf footprints affect sensors, safety priors and the real radio model."""
from copy import deepcopy

import numpy as np
import pytest

from deadzone.floorplan import FloorPlan
from deadzone.network.propagation import rssi
from deadzone.robot.lidar import raycast


def plan():
    return {"id": "shelves", "name": "Shelves", "size": [12, 10], "cell": .25,
            "materials": {"metal": 18, "wood": 3}, "walls": [], "hazards": [],
            "entry": [1, 5], "command_post": {"pos": [0, 5]},
            "obstacles": [{"id": "shelf-1", "material": "metal", "height": 1.8,
                           "poly": [[5, 4], [6, 4], [6, 6], [5, 6]]}]}


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("DZ_OBSTACLES", "1")


def test_shelf_is_occupied_and_blocks_lidar():
    fp = FloorPlan(plan())
    ix, iy = fp.to_cell(5.5, 5)
    assert fp.occ[iy, ix]
    angles, distances, hits = raycast(fp.occ, fp.cell, (2, 5, 0))
    forward = np.argmin(np.abs(angles))
    assert hits[forward] and 2.5 < distances[forward] < 3.5


@pytest.mark.parametrize("material,loss", [("metal", 18), ("wood", 3)])
def test_each_crossed_shelf_face_uses_its_declared_radio_loss(material, loss):
    data = plan()
    data["obstacles"][0]["material"] = material
    empty = deepcopy(data)
    empty["obstacles"] = []
    a, b = (2, 5), (9, 5)
    assert rssi(FloorPlan(empty), a, b) - rssi(FloorPlan(data), a, b) == pytest.approx(2 * loss)


def test_very_thin_shelves_still_occupy_boundary_cells():
    data = plan()
    data["obstacles"][0]["poly"] = [[5.01, 4], [5.04, 4], [5.04, 6], [5.01, 6]]
    fp = FloorPlan(data)
    ix, iy = fp.to_cell(5.02, 5)
    assert fp.occ[iy, ix]  # no cell centre lies inside this footprint


def test_public_prior_keeps_known_shelves_without_hidden_collapse_data():
    data = plan()
    data.update(survivors=[{"id": "secret", "pos": [10, 8]}],
                rubble=[{"poly": [[8, 7], [9, 7], [9, 8], [8, 8]]}])
    truth = FloorPlan(data)
    public = truth.planning_data()
    assert public["obstacles"] == data["obstacles"]
    assert not {"survivors", "rubble", "dynamic_walls"}.intersection(public)
    prior = FloorPlan(public)
    assert prior.occ[20, 22] and not prior.occ[30, 34]
    public["obstacles"][0]["poly"][0][0] = 0
    assert data["obstacles"][0]["poly"][0][0] == 5


def test_default_off_keeps_legacy_occupancy_radio_and_public_metadata(monkeypatch):
    monkeypatch.delenv("DZ_OBSTACLES", raising=False)
    data = plan()
    fp = FloorPlan(data)
    assert not fp.occ.any() and not len(fp.segs)
    assert "obstacles" not in fp.planning_data()
    empty = deepcopy(data)
    empty.pop("obstacles")
    assert rssi(fp, (2, 5), (9, 5)) == rssi(FloorPlan(empty), (2, 5), (9, 5))


@pytest.mark.parametrize("poly", [[], [[1, 1], [2, 2]], [[1, 1], [2, 2], [3, 3]],
                                    [[-1, 1], [2, 1], [2, 2]], [[1, 1], [float('nan'), 2], [2, 1]]])
def test_invalid_enabled_footprints_fail_at_load(poly):
    data = plan()
    data["obstacles"][0]["poly"] = poly
    with pytest.raises(ValueError, match="Obstacle"):
        FloorPlan(data)


def test_missing_material_defaults_to_metal_and_unknown_material_is_rejected():
    data = plan()
    data["obstacles"][0].pop("material")
    assert list(FloorPlan(data).seg_loss) == [18] * 4
    data["obstacles"][0]["material"] = "missing"
    with pytest.raises(ValueError, match="material"):
        FloorPlan(data)
