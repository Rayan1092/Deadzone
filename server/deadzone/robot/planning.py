"""Traversability, frontier search and A* on the robot's own map."""
import heapq
import math
from collections import deque

import numpy as np

from ..floorplan import UNKNOWN, FREE, OCC

INFLATE_CELLS = 1
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
      (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142))


def dilate(mask, r):
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx == 0 and dy == 0:
                continue
            shifted = np.zeros_like(mask)
            ys = slice(max(dy, 0), mask.shape[0] + min(dy, 0))
            yd = slice(max(-dy, 0), mask.shape[0] + min(-dy, 0))
            xs = slice(max(dx, 0), mask.shape[1] + min(dx, 0))
            xd = slice(max(-dx, 0), mask.shape[1] + min(-dx, 0))
            shifted[ys, xs] = mask[yd, xd]
            out |= shifted
    return out


def traversable(grid, nogo=None, allow_unknown=False):
    """Known-free cells away from obstacles and outside no-go zones."""
    blocked = dilate(grid == OCC, INFLATE_CELLS)
    ok = (grid == FREE) | (allow_unknown & (grid == UNKNOWN))
    ok &= ~blocked
    if nogo is not None:
        ok &= ~nogo
    return ok


def nearest_traversable(trav, start, radius=4):
    sx, sy = start
    h, w = trav.shape
    if 0 <= sx < w and 0 <= sy < h and trav[sy, sx]:
        return start
    best, bd = None, 1e9
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            x, y = sx + dx, sy + dy
            if 0 <= x < w and 0 <= y < h and trav[y, x] and dx * dx + dy * dy < bd:
                best, bd = (x, y), dx * dx + dy * dy
    return best


def frontier_clusters(grid, trav, start, blacklist=(), min_size=4):
    """One BFS from start over traversable cells. Returns clusters sorted by score.

    Each cluster: dict(cells=[(x, y)], size, dist (cells), goal=(x, y) closest cell).
    """
    h, w = grid.shape
    start = nearest_traversable(trav, start)
    if start is None:
        return [], None, None
    unknown = grid == UNKNOWN
    dist = np.full((h, w), -1, dtype=np.int32)
    parent = {}
    q = deque([start])
    dist[start[1], start[0]] = 0
    frontier = []
    while q:
        x, y = q.popleft()
        if any(0 <= x + dx < w and 0 <= y + dy < h and unknown[y + dy, x + dx] for dx, dy in N4):
            frontier.append((x, y))
        for dx, dy, _ in N8:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and trav[ny, nx] and dist[ny, nx] < 0:
                dist[ny, nx] = dist[y, x] + 1
                parent[(nx, ny)] = (x, y)
                q.append((nx, ny))

    # group frontier cells into 8-connected clusters
    fset = set(frontier)
    seen, clusters = set(), []
    for c in frontier:
        if c in seen:
            continue
        comp, stack = [], [c]
        seen.add(c)
        while stack:
            cx, cy = stack.pop()
            comp.append((cx, cy))
            for dx, dy, _ in N8:
                n = (cx + dx, cy + dy)
                if n in fset and n not in seen:
                    seen.add(n)
                    stack.append(n)
        if len(comp) < min_size:
            continue
        goal = min(comp, key=lambda p: dist[p[1], p[0]])
        if any(abs(goal[0] - b[0]) + abs(goal[1] - b[1]) < 6 for b in blacklist):
            continue
        clusters.append({"cells": comp, "size": len(comp), "dist": int(dist[goal[1], goal[0]]), "goal": goal})
    return clusters, parent, start


def bfs_path(parent, start, goal):
    path = [goal]
    while path[-1] != start:
        path.append(parent[path[-1]])
    return path[::-1]


def astar(trav, start, goal, cost=None):
    """8-connected A* with octile heuristic. Returns list of cells or None."""
    h, w = trav.shape
    start = nearest_traversable(trav, start)
    goal = nearest_traversable(trav, goal, radius=6)
    if start is None or goal is None:
        return None
    gx, gy = goal

    def heur(x, y):
        dx, dy = abs(x - gx), abs(y - gy)
        return (dx + dy) + (1.4142 - 2) * min(dx, dy)

    g = {start: 0.0}
    parent = {}
    pq = [(heur(*start), start)]
    closed = set()
    while pq:
        _, cur = heapq.heappop(pq)
        if cur == goal:
            return bfs_path(parent, start, goal)
        if cur in closed:
            continue
        closed.add(cur)
        x, y = cur
        for dx, dy, c in N8:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h) or not trav[ny, nx]:
                continue
            if dx and dy and not (trav[y, nx] and trav[ny, x]):
                continue  # no corner cutting
            ng = g[cur] + c + (cost[ny, nx] if cost is not None else 0.0)
            if ng < g.get((nx, ny), 1e18):
                g[(nx, ny)] = ng
                parent[(nx, ny)] = cur
                heapq.heappush(pq, (ng + heur(nx, ny), (nx, ny)))
    return None


def wall_cost(grid, weight=2.0):
    """Extra cost near obstacles so paths stay centered in corridors and doors."""
    occ = grid == OCC
    near1 = dilate(occ, 2)
    near2 = dilate(occ, 3)
    return weight * near1.astype(float) + 0.5 * weight * near2.astype(float)


def simplify(cells, cell, every=2):
    if not cells:
        return []
    keep = list(cells[::every])
    if keep[-1] != cells[-1]:
        keep.append(cells[-1])
    return [((x + 0.5) * cell, (y + 0.5) * cell) for x, y in keep]


def path_length(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
