"""Load a floor plan JSON and rasterize it into a truth grid."""
import json
from pathlib import Path

import numpy as np

from .geometry import points_in_poly

# Occupancy grid values shared by every map in the system (see docs/protocol.md)
UNKNOWN, FREE, OCC, NOGO = 0, 1, 2, 3


class FloorPlan:
    def __init__(self, data: dict):
        self.data = data
        self.W, self.H = data["size"]
        self.cell = data["cell"]
        self.w = int(round(self.W / self.cell))
        self.h = int(round(self.H / self.cell))
        mats = data["materials"]

        # Wall segments for propagation (rubble edges count too)
        segs, loss = [], []
        for wall in data["walls"]:
            segs.append([*wall["a"], *wall["b"]])
            loss.append(mats[wall["material"]])
        for rb in data.get("rubble", []):
            poly = rb["poly"]
            for i in range(len(poly)):
                a, b = poly[i], poly[(i + 1) % len(poly)]
                segs.append([*a, *b])
                loss.append(mats.get("rubble", 8))
        self.segs = np.array(segs, dtype=float)
        self.seg_loss = np.array(loss, dtype=float)

        # Truth occupancy (walls + rubble) and hazard mask
        self.occ = np.zeros((self.h, self.w), dtype=bool)
        for wall in data["walls"]:
            self._raster_segment(wall["a"], wall["b"])
        cx, cy = self.cell_centers()
        for rb in data.get("rubble", []):
            self.occ |= points_in_poly(cx, cy, rb["poly"])
        self.nogo = np.zeros_like(self.occ)
        for hz in data.get("hazards", []):
            self.nogo |= points_in_poly(cx, cy, hz["poly"])

        self.entry = tuple(data["entry"])
        self.cmd_pos = tuple(data["command_post"]["pos"])
        self.cmd_tx = data["command_post"].get("tx_dbm", 20)

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def cell_centers(self):
        xs = (np.arange(self.w) + 0.5) * self.cell
        ys = (np.arange(self.h) + 0.5) * self.cell
        return np.meshgrid(xs, ys)

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
