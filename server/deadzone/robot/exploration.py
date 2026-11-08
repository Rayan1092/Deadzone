"""Progress-based exploration using only the onboard map and camera footprint."""

import heapq
import math

import numpy as np

from ..floorplan import FREE, OCC, UNKNOWN
from ..geometry import wrap_angle
from . import planning


def line_clear(trav, a, b, cell):
    """Conservative segment check, including the two sides of diagonal corners."""
    n = max(1, math.ceil(math.dist(a, b) / (cell / 3)))
    previous = None
    h, w = trav.shape
    for k in range(n + 1):
        x, y = (math.floor((a[i] + (b[i] - a[i]) * k / n) / cell) for i in (0, 1))
        if not (0 <= x < w and 0 <= y < h and trav[y, x]):
            return False
        if previous is not None:
            px, py = previous
            if x != px and y != py and not (trav[py, x] and trav[y, px]):
                return False
        previous = x, y
    return True


def safe_waypoints(cells, trav, cell):
    """Remove redundant waypoints without cutting across a wall or doorway corner."""
    points = [((x + 0.5) * cell, (y + 0.5) * cell) for x, y in cells]
    result, i = [], 0
    while i < len(points):
        result.append(points[i])
        if i == len(points) - 1:
            break
        j = i + 1
        while (
            j + 1 < len(points)
            and math.dist(points[i], points[j + 1]) <= 2.0
            and line_clear(trav, points[i], points[j + 1], cell)
        ):
            j += 1
        i = j
    return result


def reachable_paths(trav, grid, start, cell):
    """One clearance-weighted search for all goals, with no diagonal corner cutting."""
    h, w = trav.shape
    start = planning.nearest_traversable(trav, start)
    if start is None:
        return None, None, None, None
    cost = planning.wall_cost(grid, weight=0.4)
    distance = np.full(trav.shape, np.inf)
    length = np.full(trav.shape, np.inf)
    parent = np.full(trav.shape, -1, dtype=np.int32)
    sx, sy = start
    distance[sy, sx] = length[sy, sx] = 0
    heap = [(0.0, sy * w + sx)]
    while heap:
        d, index = heapq.heappop(heap)
        y, x = divmod(index, w)
        if d > distance[y, x]:
            continue
        for dx, dy, step in planning.N8:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h and trav[ny, nx]):
                continue
            if dx and dy and not (trav[y, nx] and trav[ny, x]):
                continue
            nd = d + step + cost[ny, nx]
            if nd < distance[ny, nx]:
                distance[ny, nx] = nd
                length[ny, nx] = length[y, x] + step * cell
                parent[ny, nx] = index
                heapq.heappush(heap, (nd, ny * w + nx))
    return distance, length, parent, start


class ProgressExplorer:
    def __init__(self, shape, cell):
        self.cell = cell
        self.surveyed = np.zeros(shape, dtype=bool)
        self.team_surveyed = np.zeros(shape, dtype=bool)
        self.peer_views = {}
        self.peer_map_count = -1
        self.goal = None
        self.goal_t = 0.0
        self.goal_claimed = False
        self.scan_left = 0.0
        self.scan_deadline = 0.0
        self.scan_goal = None
        self.last_pose = None
        self.last_observed_t = -99.0
        self.recent_views = []
        self.searches = 0
        # Thermal camera contract: 5m range, 120-degree forward cone. Occupancy
        # comes from lidar, so mapped floor is not automatically camera-searched.
        self.ranges = np.arange(cell / 2, 5.0 + cell / 2, cell / 2)

    def reset_goal(self):
        """A new operator task cancels commitment, but keeps learned coverage."""
        self.goal = None
        self.scan_goal = None
        self.scan_left = 0.0

    def _rays(self, grid, pose, full=False):
        angles = (
            np.linspace(-math.pi, math.pi, 48, endpoint=False)
            if full
            else pose[2] + np.linspace(-math.pi / 3, math.pi / 3, 32)
        )
        ix = np.floor(
            (pose[0] + np.cos(angles)[:, None] * self.ranges) / self.cell
        ).astype(int)
        iy = np.floor(
            (pose[1] + np.sin(angles)[:, None] * self.ranges) / self.cell
        ).astype(int)
        h, w = grid.shape
        inside = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
        values = np.full(ix.shape, OCC, dtype=np.uint8)
        values[inside] = grid[iy[inside], ix[inside]]
        # For actual coverage, unknown space blocks the visibility claim. For
        # selecting an exploration viewpoint, it is potential information until
        # a known wall blocks the ray.
        stops = (values == OCC) if full else (values != FREE)
        before = np.ones_like(stops)
        before[:, 1:] = ~np.maximum.accumulate(stops[:, :-1], axis=1)
        visible = before & inside
        return ix, iy, values, visible

    def observe(self, grid, pose, now, exploring):
        if self.last_pose is not None and self.scan_left > 0:
            self.scan_left = max(
                0.0, self.scan_left - abs(wrap_angle(pose[2] - self.last_pose[2]))
            )
        self.last_pose = tuple(pose)
        if not exploring or now >= self.scan_deadline:
            self.scan_left = 0.0
        if now - self.last_observed_t < 0.2:
            return
        self.last_observed_t = now
        ix, iy, values, visible = self._rays(grid, pose)
        seen = visible & (values == FREE)
        self.surveyed[iy[seen], ix[seen]] = True

    def observe_peer(self, grid, pose):
        """Use delivered telemetry only; never another robot's live position/map."""
        try:
            valid = (
                pose is not None
                and len(pose) == 3
                and all(math.isfinite(v) for v in pose)
            )
        except (TypeError, ValueError):
            valid = False
        if not valid:
            return
        key = int(pose[0]), int(pose[1]), int(wrap_angle(pose[2]) / (math.pi / 4))
        self.peer_views[key] = tuple(pose)
        if len(self.peer_views) > 256:
            del self.peer_views[next(iter(self.peer_views))]
        self._mark_peer(grid, pose)

    def _mark_peer(self, grid, pose):
        ix, iy, values, visible = self._rays(grid, pose)
        seen = visible & (values == FREE)
        self.team_surveyed[iy[seen], ix[seen]] = True

    def _gain(self, grid, x, y):
        ix, iy, values, visible = self._rays(
            grid, ((x + 0.5) * self.cell, (y + 0.5) * self.cell, 0), full=True
        )
        valid = visible & ((values == FREE) | (values == UNKNOWN))
        cells = np.unique(iy[valid] * grid.shape[1] + ix[valid])
        ys, xs = np.divmod(cells, grid.shape[1])
        unseen = (grid[ys, xs] == FREE) & ~(
            self.surveyed[ys, xs] | self.team_surveyed[ys, xs]
        )
        unknown = grid[ys, xs] == UNKNOWN
        return (unseen.sum() + 0.6 * unknown.sum()) * self.cell**2

    def plan(self, grid, trav, pose, now, current_path, zone=None, claimed=()):
        known = np.count_nonzero(grid == FREE)
        if known != self.peer_map_count:
            for peer_pose in self.peer_views.values():
                self._mark_peer(grid, peer_pose)
            self.peer_map_count = known
        if self.scan_left > 0.05 and now < self.scan_deadline:
            return [], self.scan_goal
        if self.goal is not None:
            xy = ((self.goal[0] + 0.5) * self.cell, (self.goal[1] + 0.5) * self.cell)
            if math.dist(pose[:2], xy) < 0.6:
                self.recent_views.append((xy, now))
                self.recent_views = self.recent_views[-64:]
                self.scan_goal, self.goal = self.goal, None
                # The forward 120 degrees were seen on approach; sweep the rest.
                self.scan_left, self.scan_deadline = 4 * math.pi / 3, now + 3.5
                return [], self.scan_goal
            newly_claimed = (
                any(math.dist(xy, p) < 4 for p in claimed) and not self.goal_claimed
            )
            if (
                current_path
                and not newly_claimed
                and now - self.goal_t < 45
                and trav[self.goal[1], self.goal[0]]
            ):
                return current_path, self.goal
        costs, length, parent, start = reachable_paths(
            trav,
            grid,
            (int(pose[0] // self.cell), int(pose[1] // self.cell)),
            self.cell,
        )
        self.searches += 1
        if start is None:
            return None
        unknown = grid == UNKNOWN
        edge = np.zeros_like(unknown)
        edge[1:] |= unknown[:-1]
        edge[:-1] |= unknown[1:]
        edge[:, 1:] |= unknown[:, :-1]
        edge[:, :-1] |= unknown[:, 1:]
        surveyed = self.surveyed | self.team_surveyed
        candidates = np.isfinite(costs) & trav & (edge | ~surveyed) & (length >= 0.8)
        # Integral image is only a cheap shortlist; final gain raycasts stop at
        # known walls; unknown cells contribute potential information only.
        interesting = ((grid == FREE) & ~surveyed) | unknown
        integral = (
            np.pad(interesting.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        )
        ys, xs = np.nonzero(candidates)
        ranked = []
        radius = max(1, int(3 / self.cell))
        bins = {}
        for x, y in zip(xs.tolist(), ys.tolist()):
            xy = ((x + 0.5) * self.cell, (y + 0.5) * self.cell)
            if any(
                now - t < 25 and math.dist(xy, old) < 1.0
                for old, t in self.recent_views
            ):
                continue
            x0, x1 = max(0, x - radius), min(grid.shape[1], x + radius + 1)
            y0, y1 = max(0, y - radius), min(grid.shape[0], y + radius + 1)
            area = (
                integral[y1, x1]
                - integral[y0, x1]
                - integral[y1, x0]
                + integral[y0, x0]
            ) * self.cell**2
            preference = 0.0
            if zone is not None:
                if zone["mask"][y, x]:
                    preference += 5.0
                else:
                    preference -= (
                        2 if zone["id"].startswith("voice:") else 1.5
                    ) * math.dist(xy, zone["center"])
            if any(math.dist(xy, p) < 4 for p in claimed):
                preference -= 12
            score = 2 * math.sqrt(area) - 0.7 * length[y, x] + preference
            key = int(x * self.cell), int(y * self.cell)
            if key not in bins or score > bins[key][0]:
                bins[key] = (score, x, y, preference)
        ranked = sorted(bins.values(), reverse=True)[:32]
        best = None
        for _, x, y, preference in ranked:
            gain = self._gain(grid, x, y)
            if gain < 0.3:
                continue
            score = 3 * math.sqrt(gain) - 0.7 * length[y, x] + preference
            if best is None or score > best[0]:
                best = (score, x, y)
        if best is None:
            self.goal = None
            return None
        _, x, y = best
        cells = [(x, y)]
        while cells[-1] != start:
            index = parent[cells[-1][1], cells[-1][0]]
            if index < 0:
                return None
            yy, xx = divmod(int(index), grid.shape[1])
            cells.append((xx, yy))
        cells.reverse()
        self.goal, self.goal_t = (x, y), now
        self.goal_claimed = any(
            math.dist(((x + 0.5) * self.cell, (y + 0.5) * self.cell), p) < 4
            for p in claimed
        )
        return safe_waypoints(cells, trav, self.cell), self.goal
