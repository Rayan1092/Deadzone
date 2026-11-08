"""Bayesian survivor belief: where the people still unaccounted for probably are.

Phase 1 is display only (nothing here steers a robot). One grid cell = one floor-plan cell.

  prior      from the building prior, never truth: 0 in walls and occupied cells, rooms above
             corridors, collapse areas (rubble) and radio dead zones (steel rooms) above rooms;
             hazards keep their prior (people can be there even if robots cannot)
  miss       every cell a thermal camera observes (RANGE_M, FOV, line of sight on the observer's
             own map) with no person in it is multiplied by 1 - recall(d): recall RECALL_NEAR up
             to NEAR_M, falling linearly to RECALL_FAR at RANGE_M
  confirm    a confirmed survivor's cell is accounted for (drawn at 255) and the cells within
             CONFIRM_RADIUS_M are lowered; a rejected hot spot's cell is lowered
  normalize  the unaccounted mass sums to the expected survivors still missing: the building's
             `expected_survivors` prior (default EXPECTED_DEFAULT) minus confirmed ones

Each robot keeps its own miss grid and confirmations from its own sensors (Reality); the team
belief is their merge with the prior. CommandBelief is the same arithmetic fed only with
delivered data (robot poses from telemetry, survivor reports): what the command post knows.
"""
import math

import numpy as np

from ..floorplan import OCC
from ..geometry import points_in_poly

RANGE_M = 5.0                 # thermal camera range (io.thermal contract)
FOV = math.radians(120)       # thermal camera cone
RECALL_NEAR, NEAR_M = 0.96, 3.5   # detector recall at demo range ...
RECALL_FAR = 0.5                  # ... and at the 5 m edge
CONFIRM_RADIUS_M = 3.0        # a confirmed survivor explains the heat around them
CONFIRM_NEIGHBOUR_FACTOR = 0.3
REJECT_FACTOR = 0.2           # "hot, but not a person"
EXPECTED_DEFAULT = 3          # expected_survivors prior when the floor plan has none
PRIOR = {"corridor": 0.4, "room": 1.0, "collapse": 2.0, "dead_zone": 2.0}
RAYS = 48                     # ray samples across the cone per observation


def recall(d):
    """Detector recall at distance d (m): flat at demo range, falling toward the camera's edge."""
    if d <= NEAR_M:
        return RECALL_NEAR
    return RECALL_NEAR + (RECALL_FAR - RECALL_NEAR) * min(1.0, (d - NEAR_M) / (RANGE_M - NEAR_M))


def expected_survivors(fp_data):
    try:
        n = int(fp_data.get("expected_survivors", EXPECTED_DEFAULT))
    except (TypeError, ValueError):
        n = EXPECTED_DEFAULT
    return max(0, n)


def prior_grid(fp_data, occ, cell):
    """Prior probability mass per cell from the building prior (rooms, rubble, steel rooms,
    walls). `occ` is the prior occupancy grid (walls and known rubble), never the truth of the
    collapse."""
    h, w = occ.shape
    xs = (np.arange(w) + 0.5) * cell
    ys = (np.arange(h) + 0.5) * cell
    cx, cy = np.meshgrid(xs, ys)
    prior = np.full((h, w), PRIOR["corridor"], dtype=np.float32)
    for room in fp_data.get("rooms", []):
        mask = points_in_poly(cx, cy, room["poly"])
        name = str(room.get("name", "")).lower()
        dead = room.get("steel") or room.get("id") == "E2" or "cage" in name or "vault" in name
        if dead:
            prior[mask] = PRIOR["dead_zone"]
        elif any(k in name for k in ("corridor", "hall", "lobby")):
            prior[mask] = np.maximum(prior[mask], PRIOR["corridor"])
        else:
            prior[mask] = np.maximum(prior[mask], PRIOR["room"])
    for rb in fp_data.get("rubble", []):
        mask = points_in_poly(cx, cy, rb["poly"])
        prior[mask] = np.maximum(prior[mask], PRIOR["collapse"])
        # a collapse also raises the cells around the pile (people trapped at its edge)
        x0, y0 = min(p[0] for p in rb["poly"]) - 1.0, min(p[1] for p in rb["poly"]) - 1.0
        x1, y1 = max(p[0] for p in rb["poly"]) + 1.0, max(p[1] for p in rb["poly"]) + 1.0
        ring = (cx >= x0) & (cx <= x1) & (cy >= y0) & (cy <= y1) & ~mask
        prior[ring] = np.maximum(prior[ring], PRIOR["collapse"] * 0.75)
    prior[occ.astype(bool)] = 0.0
    return prior


def _line_clear(occ, x0, y0, x1, y1):
    """Bresenham line of sight between two cells on an occupancy grid (end cell excluded)."""
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    x, y = x0, y0
    h, w = occ.shape
    while (x, y) != (x1, y1):
        if not (0 <= x < w and 0 <= y < h) or ((x, y) != (x0, y0) and occ[y, x]):
            return False
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return True


def observed_cells(pose, occ, cell):
    """Cells inside the camera cone with line of sight on `occ`, with their distance (m):
    {(ix, iy): d}. Rays are sampled across the cone and stop at the first occupied cell."""
    x, y, th = pose
    h, w = occ.shape
    ox, oy = int(x // cell), int(y // cell)
    out = {}
    steps = int(RANGE_M / (cell / 2))
    for a in np.linspace(th - FOV / 2, th + FOV / 2, RAYS):
        ca, sa = math.cos(a), math.sin(a)
        for k in range(1, steps + 1):
            d = k * cell / 2
            ix, iy = int((x + ca * d) // cell), int((y + sa * d) // cell)
            if not (0 <= ix < w and 0 <= iy < h) or occ[iy, ix]:
                break
            if (ix, iy) != (ox, oy) and (ix, iy) not in out:
                out[(ix, iy)] = d
    return out


class Belief:
    """One observer's evidence: a miss grid (product of miss likelihoods), confirmations and
    rejections. `missing_grid()` combines them with the prior and normalizes."""

    def __init__(self, prior, cell, expected=EXPECTED_DEFAULT):
        self.prior = prior
        self.cell = cell
        self.expected = expected
        self.miss = np.ones_like(prior, dtype=np.float32)
        self.confirmed = {}       # id -> (ix, iy)
        self.rejected = {}        # id -> (ix, iy)
        self.observations = 0

    def observe(self, pose, occ, exclude=()):
        """The camera looked from `pose` and saw no person in these cells. `exclude` lists the
        positions of hot spots seen this look (a seen person is confirmed or still being judged,
        not missed)."""
        cells = observed_cells(pose, occ, self.cell)
        for pos in exclude:
            cells.pop(self._cell(pos), None)
        if not cells:
            return 0
        ix = np.fromiter((c[0] for c in cells), dtype=np.int64, count=len(cells))
        iy = np.fromiter((c[1] for c in cells), dtype=np.int64, count=len(cells))
        d = np.fromiter(cells.values(), dtype=np.float32, count=len(cells))
        self.miss[iy, ix] *= 1.0 - np.vectorize(recall, otypes=[np.float32])(d)
        self.observations += 1
        return len(cells)

    def _cell(self, pos):
        h, w = self.prior.shape
        return min(w - 1, max(0, int(pos[0] // self.cell))), min(h - 1, max(0, int(pos[1] // self.cell)))

    def confirm(self, sid, pos):
        self.confirmed[sid] = self._cell(pos)

    def reject(self, hid, pos):
        self.rejected[hid] = self._cell(pos)

    def missing(self):
        """Expected survivors still unaccounted for."""
        return max(0.0, float(self.expected - len(self.confirmed)))

    def missing_grid(self):
        """Normalized probability mass of the people still missing, per cell."""
        return combine(self.prior, [self.miss], self.confirmed.values(), self.rejected.values(), self.cell, self.missing())

    def render(self, scale_max=None):
        return render(self.missing_grid(), self.confirmed.values(), scale_max)


def combine(prior, misses, confirmed, rejected, cell, missing):
    g = prior.astype(np.float32).copy()
    for m in misses:
        g *= m
    h, w = g.shape
    for ix, iy in rejected:
        g[iy, ix] *= REJECT_FACTOR
    r = int(math.ceil(CONFIRM_RADIUS_M / cell))
    ys, xs = np.ogrid[-r:r + 1, -r:r + 1]
    disk = xs * xs + ys * ys <= r * r
    for ix, iy in confirmed:
        x0, x1, y0, y1 = max(0, ix - r), min(w, ix + r + 1), max(0, iy - r), min(h, iy + r + 1)
        sub = disk[y0 - (iy - r):y1 - (iy - r), x0 - (ix - r):x1 - (ix - r)]
        g[y0:y1, x0:x1][sub] *= CONFIRM_NEIGHBOUR_FACTOR
        g[iy, ix] = 0.0                        # accounted for: no missing mass here
    total = float(g.sum())
    if total > 0 and missing > 0:
        g *= missing / total
    else:
        g[:] = 0.0
    return g


def render(grid, confirmed, scale_max=None):
    """uint8 view: 0..254 proportional to missing mass (against `scale_max`, default the grid's
    own maximum), 255 on confirmed survivors' cells."""
    top = float(grid.max()) if scale_max is None else float(scale_max)
    out = np.zeros(grid.shape, dtype=np.uint8)
    if top > 0:
        out[:] = np.clip(np.rint(grid / top * 254.0), 0, 254).astype(np.uint8)
    for ix, iy in confirmed:
        out[iy, ix] = 255
    return out


def team_belief(robots, prior, cell, expected):
    """Reality: every robot's miss grid, confirmations and rejections merged with the prior.
    Returns (missing grid, confirmed cells, missing count)."""
    robots = list(robots)
    confirmed, rejected = {}, {}
    for r in robots:
        confirmed.update(r.belief.confirmed)
        rejected.update(r.belief.rejected)
    missing = max(0.0, float(expected - len(confirmed)))
    grid = combine(prior, [r.belief.miss for r in robots], confirmed.values(), rejected.values(), cell, missing)
    return grid, list(confirmed.values()), missing


class CommandBelief(Belief):
    """The command post's belief from delivered data only: it observes along delivered robot
    poses on Command's own map and confirms delivered survivor reports. Feed it from the
    delivery path (CommandPost.receive): `observe_delivered` once per telemetry bundle (a repeat
    of the same robot and sent time is ignored), `confirm` per delivered survivor record."""

    def __init__(self, prior, cell, expected=EXPECTED_DEFAULT):
        super().__init__(prior, cell, expected)
        self.seen_t = {}          # robot id -> sent time of the last pose observed

    def observe_delivered(self, rid, pose, sent_t, occ):
        if self.seen_t.get(rid) == sent_t or pose is None or len(pose) < 3:
            return 0
        self.seen_t[rid] = sent_t
        return self.observe(pose, occ)
