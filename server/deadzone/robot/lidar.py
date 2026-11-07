"""Simulated 2D lidar by vectorized ray marching over the truth grid.

The sim calls raycast() with the TRUE pose and truth grid and hands the robot only
the beam angles and ranges. The robot never sees the truth grid itself.
"""
import numpy as np

N_BEAMS = 72
MAX_RANGE = 8.0


def raycast(occ, cell, pose, n_beams=N_BEAMS, max_range=MAX_RANGE):
    x, y, th = pose
    h, w = occ.shape
    angles = th + np.linspace(-np.pi, np.pi, n_beams, endpoint=False)
    step = cell / 2
    r = np.arange(step, max_range + step, step)
    px = x + np.outer(np.cos(angles), r)
    py = y + np.outer(np.sin(angles), r)
    ix = np.floor(px / cell).astype(int)
    iy = np.floor(py / cell).astype(int)
    outside = (ix < 0) | (iy < 0) | (ix >= w) | (iy >= h)
    hit = outside.copy()
    hit[~outside] = occ[iy[~outside], ix[~outside]]
    any_hit = hit.any(axis=1)
    first = np.argmax(hit, axis=1)
    ranges = np.where(any_hit, r[first], max_range)
    return angles, ranges, any_hit
