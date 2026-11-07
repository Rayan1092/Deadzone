"""Small geometry helpers shared by the sim and the robots."""
import numpy as np


def points_in_poly(px, py, poly):
    """Vectorized even-odd point in polygon test. px, py are arrays of the same shape."""
    poly = np.asarray(poly, dtype=float)
    inside = np.zeros(np.shape(px), dtype=bool)
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        crosses = ((yi > py) != (yj > py))
        with np.errstate(divide="ignore", invalid="ignore"):
            x_at = (xj - xi) * (py - yi) / (yj - yi) + xi
        inside ^= crosses & (px < x_at)
        j = i
    return inside


def count_crossings(p, q, segs):
    """Boolean mask of which segments (N x 4: ax, ay, bx, by) the segment p->q crosses."""
    if len(segs) == 0:
        return np.zeros(0, dtype=bool)
    px, py = p
    qx, qy = q
    ax, ay, bx, by = segs[:, 0], segs[:, 1], segs[:, 2], segs[:, 3]
    rx, ry = qx - px, qy - py
    sx, sy = bx - ax, by - ay
    denom = rx * sy - ry * sx
    with np.errstate(divide="ignore", invalid="ignore"):
        t = ((ax - px) * sy - (ay - py) * sx) / denom
        u = ((ax - px) * ry - (ay - py) * rx) / denom
    return (np.abs(denom) > 1e-9) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)


def wrap_angle(a):
    return (a + np.pi) % (2 * np.pi) - np.pi
