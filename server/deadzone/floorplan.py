"""Load a floor plan JSON and rasterize it into a truth grid."""
import json
import os
from copy import deepcopy
from pathlib import Path

import numpy as np

from .geometry import points_in_poly

# Occupancy grid values shared by every map in the system (see docs/protocol.md)
UNKNOWN, FREE, OCC, NOGO = 0, 1, 2, 3


# Radio loss per furniture piece crossed (dB), DZ_OBSTACLES=1. Furniture is not a wall:
# Rappaport, Wireless Communications: Principles and Practice (2nd ed.), Table 4.3, partition
# losses measured at 1.3 GHz, light partitions and light machinery 1 to 4 dB. The default is the
# low end, 1 dB, because the exported footprints are open shelving and desks; a piece can declare
# its own `loss_db` (a loaded pallet rack 4). A straight path enters and leaves a footprint, so
# each footprint edge carries half of the piece's loss. Walls and rubble keep the materials table.
# Note (docs/FACTS.md): the demo plan's ZW zone has only 1.6 dB of command-post link margin by
# design, so it is the first zone to go marginal when anything sits on that line.
FURNITURE_LOSS_DB = 1.0


class FloorPlan:
    def __init__(self, data: dict):
        self.data = data
        self.W, self.H = data["size"]
        self.cell = data["cell"]
        self.w = int(round(self.W / self.cell))
        self.h = int(round(self.H / self.cell))
        mats = data["materials"]
        self.obstacles_enabled = os.environ.get("DZ_OBSTACLES") == "1"
        obstacles = self._validated_obstacles() if self.obstacles_enabled else []

        # Wall segments for propagation (rubble edges count too)
        segs, loss = [], []
        for wall in [*data["walls"], *data.get("dynamic_walls", [])]:
            segs.append([*wall["a"], *wall["b"]])
            loss.append(mats[wall["material"]])
        for rb in data.get("rubble", []):
            poly = rb["poly"]
            for i in range(len(poly)):
                a, b = poly[i], poly[(i + 1) % len(poly)]
                segs.append([*a, *b])
                loss.append(mats.get("rubble", 8))
        for poly, material_loss in obstacles:
            for a, b in zip(poly, poly[1:] + poly[:1]):
                segs.append([*a, *b])
                loss.append(material_loss)
        self.segs = np.array(segs, dtype=float)
        self.seg_loss = np.array(loss, dtype=float)

        # Truth occupancy (walls + rubble) and hazard mask
        self.occ = np.zeros((self.h, self.w), dtype=bool)
        for wall in [*data["walls"], *data.get("dynamic_walls", [])]:
            self._raster_segment(wall["a"], wall["b"])
        cx, cy = self.cell_centers()
        for rb in data.get("rubble", []):
            self.occ |= points_in_poly(cx, cy, rb["poly"])
        for poly, _ in obstacles:
            self.occ |= points_in_poly(cx, cy, poly)
            for a, b in zip(poly, poly[1:] + poly[:1]):
                self._raster_segment(a, b)
        self.nogo = np.zeros_like(self.occ)
        for hz in data.get("hazards", []):
            self.nogo |= points_in_poly(cx, cy, hz["poly"])

        self.entry = tuple(data["entry"])
        self.cmd_pos = tuple(data["command_post"]["pos"])
        self.cmd_tx = data["command_post"].get("tx_dbm", 20)

    def _validated_obstacles(self):
        obstacles = self.data.get("obstacles", [])
        if not isinstance(obstacles, list):
            raise ValueError("obstacles must be a list of polygon footprints")
        out = []
        for i, obstacle in enumerate(obstacles):
            if not isinstance(obstacle, dict):
                raise ValueError(f"Obstacle {i} must have a poly footprint")
            try:
                poly = np.asarray(obstacle.get("poly"), dtype=float)
            except (TypeError, ValueError):
                raise ValueError(f"Obstacle {i} has invalid polygon coordinates") from None
            if (poly.ndim != 2 or poly.shape[1] != 2 or len(poly) < 3 or not np.isfinite(poly).all()
                    or (poly[:, 0] < 0).any() or (poly[:, 0] > self.W).any()
                    or (poly[:, 1] < 0).any() or (poly[:, 1] > self.H).any()):
                raise ValueError(f"Obstacle {i} needs >=3 finite vertices inside the building")
            cross = poly[:, 0] * np.roll(poly[:, 1], -1) - np.roll(poly[:, 0], -1) * poly[:, 1]
            if abs(float(cross.sum())) <= 1e-9:
                raise ValueError(f"Obstacle {i} footprint must have positive area")
            material = obstacle.get("material", "metal")
            if not isinstance(material, str) or material not in self.data["materials"]:
                raise ValueError(f"Obstacle {i} material must be declared in materials")
            # Furniture is its own radio class: a desk or a shelf is not a wall of that material.
            # Each crossed footprint edge costs the piece's `loss_db` (default FURNITURE_LOSS_DB),
            # never the wall table's loss for its material.
            try:
                loss_db = float(obstacle.get("loss_db", FURNITURE_LOSS_DB))
            except (TypeError, ValueError):
                raise ValueError(f"Obstacle {i} loss_db must be finite and nonnegative") from None
            if not np.isfinite(loss_db) or loss_db < 0:
                raise ValueError(f"Obstacle {i} loss_db must be finite and nonnegative")
            out.append((poly.tolist(), loss_db / 2.0))     # per edge; a crossing costs loss_db
        return out

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def cell_centers(self):
        xs = (np.arange(self.w) + 0.5) * self.cell
        ys = (np.arange(self.h) + 0.5) * self.cell
        return np.meshgrid(xs, ys)

    def planning_data(self):
        """Public pre-collapse structure, without hidden survivors or debris."""
        keys = ("id", "name", "size", "cell", "wall_height", "materials", "walls",
                "doors", "rooms", "hazards", "entry", "command_post")
        if self.obstacles_enabled:
            keys += ("obstacles",)
        data = {key: deepcopy(self.data[key]) for key in keys if key in self.data}
        for door in data.get("doors", []):
            door["state"] = "open"  # post-collapse door damage is not part of the prior
        return data

    def to_cell(self, x, y):
        return int(x // self.cell), int(y // self.cell)

    def to_world(self, ix, iy):
        return (ix + 0.5) * self.cell, (iy + 0.5) * self.cell

    def in_bounds(self, ix, iy):
        return 0 <= ix < self.w and 0 <= iy < self.h

    def add_rubble(self, poly):
        """Runtime rubble fall (fault injection). Updates truth and propagation."""
        cx, cy = self.cell_centers()
        self.occ |= points_in_poly(cx, cy, poly)
        mats = self.data["materials"]
        new = [[*poly[i], *poly[(i + 1) % len(poly)]] for i in range(len(poly))]
        self.segs = np.vstack([self.segs, np.array(new, dtype=float)])
        self.seg_loss = np.concatenate([self.seg_loss, np.full(len(new), mats.get("rubble", 8))])

    def _raster_segment(self, a, b):
        a, b = np.asarray(a, float), np.asarray(b, float)
        n = int(np.ceil(np.linalg.norm(b - a) / (self.cell / 4))) + 1
        pts = a + np.outer(np.linspace(0, 1, n), b - a)
        ix = np.clip((pts[:, 0] // self.cell).astype(int), 0, self.w - 1)
        iy = np.clip((pts[:, 1] // self.cell).astype(int), 0, self.h - 1)
        self.occ[iy, ix] = True

    def add_wall(self, wall):
        """Runtime truth wall, separated from public pre-collapse wall metadata."""
        self._raster_segment(wall["a"], wall["b"])
        self.segs = np.vstack([self.segs, np.array([[*wall["a"], *wall["b"]]], dtype=float)])
        self.seg_loss = np.append(self.seg_loss, self.data["materials"][wall["material"]])
        self.data.setdefault("dynamic_walls", []).append(deepcopy(wall))
