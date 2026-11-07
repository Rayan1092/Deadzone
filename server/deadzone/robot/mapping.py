"""Occupancy grid built only from the robot's own lidar returns."""
import numpy as np

from ..floorplan import UNKNOWN, FREE, OCC


class OccupancyMap:
    def __init__(self, w, h, cell):
        self.w, self.h, self.cell = w, h, cell
        self.grid = np.zeros((h, w), dtype=np.uint8)      # UNKNOWN everywhere
        self.dirty = np.zeros((h, w), dtype=bool)         # changed since last map patch

    def integrate(self, pose, angles, ranges, hits):
        x, y, _ = pose
        step = self.cell / 2
        r = np.arange(0, ranges.max(), step)
        # free space: every sample strictly before the return
        px = x + np.outer(np.cos(angles), r)
        py = y + np.outer(np.sin(angles), r)
        before = r[None, :] < (ranges[:, None] - step * 0.5)
        ix = np.floor(px / self.cell).astype(int)
        iy = np.floor(py / self.cell).astype(int)
        ok = before & (ix >= 0) & (iy >= 0) & (ix < self.w) & (iy < self.h)
        fx, fy = ix[ok], iy[ok]
        keep = self.grid[fy, fx] != OCC
        self._set(fx[keep], fy[keep], FREE)
        # occupied: the cell of each actual return
        hx = np.floor((x + np.cos(angles[hits]) * ranges[hits]) / self.cell).astype(int)
        hy = np.floor((y + np.sin(angles[hits]) * ranges[hits]) / self.cell).astype(int)
        ok = (hx >= 0) & (hy >= 0) & (hx < self.w) & (hy < self.h)
        self._set(hx[ok], hy[ok], OCC)
        # the robot's own footprint is free
        cx, cy = int(x // self.cell), int(y // self.cell)
        if 0 <= cx < self.w and 0 <= cy < self.h and self.grid[cy, cx] == UNKNOWN:
            self._set(np.array([cx]), np.array([cy]), FREE)

    def mark_occupied(self, ix, iy):
        self._set(np.atleast_1d(ix), np.atleast_1d(iy), OCC)

    def _set(self, ix, iy, val):
        changed = self.grid[iy, ix] != val
        self.grid[iy[changed], ix[changed]] = val
        self.dirty[iy[changed], ix[changed]] = True

    def take_patch(self):
        """Return changed cells as (ix, iy, value) arrays and clear the dirty mask."""
        iy, ix = np.nonzero(self.dirty)
        vals = self.grid[iy, ix]
        self.dirty[:] = False
        return ix.astype(np.uint16), iy.astype(np.uint16), vals.astype(np.uint8)
