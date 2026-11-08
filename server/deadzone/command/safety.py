"""Planning estimates from the building prior and DELIVERED Command knowledge."""
from dataclasses import dataclass
from collections import deque
import os

import numpy as np

from ..floorplan import FREE, OCC
from ..geometry import points_in_poly
from ..network.propagation import LINK_DOWN_DBM, rssi
from ..robot import planning
from ..robot.power import CAPACITY_WH, P_IDLE_W, P_COMPUTE_W, P_RADIO_W, P_DRIVE_W_PER_MPS, RESERVE_PCT
from .plan import area, centroid, segments_intersect


@dataclass(frozen=True)
class RobotSpec:
    stairs: bool = False
    max_rubble_height: float = 0.0  # current physics cannot climb obstacles
    capacity_wh: float = CAPACITY_WH
    speed: float = 0.8

    @property
    def cruise_w(self):
        return P_IDLE_W + P_COMPUTE_W + P_RADIO_W + P_DRIVE_W_PER_MPS * self.speed


def overlap(a, b):
    for p, q in zip(a, a[1:] + a[:1]):
        if any(segments_intersect(p, q, r, s) for r, s in zip(b, b[1:] + b[:1])):
            return True
    return (bool(points_in_poly(np.array(a[0][0]), np.array(a[0][1]), b)) or
            bool(points_in_poly(np.array(b[0][0]), np.array(b[0][1]), a)))


class SafetyChecker:
    def __init__(self, prior, robot_specs, energy_time_scale=1.0):
        self.prior, self.robot_specs = prior, robot_specs
        self.energy_time_scale = energy_time_scale
        # Default on (Rayan, with Aziz's files authorized): a phone no-go reaches every deployed robot and
        # a robot inside a new no-go is routed out; DZ_GLOBAL_NO_GO=0 restores the legacy behaviour.
        self.global_no_go = os.environ.get("DZ_GLOBAL_NO_GO", "1") != "0"

    def _comms(self, pos, relays):
        """Predicted reachability; never inspect the simulation's live link graph."""
        positions = [self.prior.cmd_pos, *[r["pos"] for r in relays.values()], pos]
        seen, pending = {0}, [0]
        while pending:
            i = pending.pop()
            if i == len(positions) - 1:
                return True
            for j, other in enumerate(positions):
                if j not in seen and rssi(self.prior, positions[i], other) >= LINK_DOWN_DBM:
                    seen.add(j)
                    pending.append(j)
        return False

    def check(self, plan, post, now):
        fp = self.prior
        cx, cy = fp.cell_centers()
        blocked = fp.nogo.copy()
        hazard_polys = [h["poly"] for h in fp.data.get("hazards", [])]
        plan_polys = [g.poly for g in plan.no_go]
        for g in plan.no_go:
            blocked |= points_in_poly(cx, cy, g.poly)
        # Unknown cells use the pre-collapse prior. Only delivered observations
        # can add collapse debris to this grid; no truth rubble is read here.
        grid = np.where(fp.occ | (post.map == OCC), OCC, FREE).astype(np.uint8)
        trav = planning.traversable(grid, blocked)
        violations, warnings, states, route_cache = [], [], {}, {}
        # A responder's no-go area always wins over a search zone: the robots never plan through it
        # (they skip the excluded part of their zone, or hold when it walls them in). So a conflict
        # caused only by the plan's own no-go areas is a warning, never a refusal that would leave
        # the robots driving through the area. Building hazards, walls, a blocked route home and
        # the legacy mode (DZ_GLOBAL_NO_GO=0) still refuse as before.
        soft = self.global_no_go and bool(plan_polys)
        trav_hazards = planning.traversable(grid, fp.nogo) if soft else trav  # without the plan's no-go

        def reject(zone, rule, value, limit, msg):
            violations.append({"robot": zone.robot, "zone": zone.id, "rule": rule,
                               "value": value, "limit": limit, "msg": msg})

        def warn(zone, rule, msg):
            warnings.append({"robot": zone.robot, "zone": zone.id, "rule": rule, "level": "warning",
                             "value": True, "limit": False, "msg": msg})

        def reachable_without_plan_no_go(start, goal):
            a, b = fp.to_cell(*start), fp.to_cell(*goal)
            if not fp.in_bounds(*a) or not fp.in_bounds(*b) or not trav_hazards[b[1], b[0]]:
                return False
            if not trav_hazards[a[1], a[0]]:
                return False
            return planning.astar(trav_hazards, a, b) is not None

        def route_length(start, goal):
            a, b = fp.to_cell(*start), fp.to_cell(*goal)
            key = a, b
            if key not in route_cache:
                if not fp.in_bounds(*a) or not fp.in_bounds(*b) or not trav[b[1], b[0]]:
                    route_cache[key] = None
                else:
                    escape = self._escape_start(a, trav, grid, blocked)
                    if escape is None:
                        route_cache[key] = None
                    else:
                        safe_start, distance = escape
                        path = planning.astar(trav, safe_start, b)
                        route_cache[key] = None if path is None else distance + planning.path_length(
                            [fp.to_world(*p) for p in path])
            return route_cache[key]

        for zone in sorted(plan.zones, key=lambda z: (z.robot, z.priority, z.id)):
            spec = self.robot_specs.get(zone.robot)
            if spec is None:
                reject(zone, "capability", zone.robot, None, f"Robot {zone.robot} is not deployed")
                continue
            if zone.requires.stairs and not spec.stairs:
                reject(zone, "capability", "stairs", False, f"{zone.robot} cannot use stairs")
            if zone.requires.rubble_height > spec.max_rubble_height:
                reject(zone, "capability", zone.requires.rubble_height, spec.max_rubble_height,
                       f"{zone.robot} cannot cross the required rubble height")
            if any(overlap(zone.poly, poly) for poly in hazard_polys):
                reject(zone, "no_go_overlap", True, False, f"Zone {zone.id} overlaps a no-go area")
            elif any(overlap(zone.poly, poly) for poly in plan_polys):
                if soft:
                    warn(zone, "no_go_overlap", f"{zone.robot} skips the part of zone {zone.id} inside the no-go area")
                else:
                    reject(zone, "no_go_overlap", True, False, f"Zone {zone.id} overlaps a no-go area")
            telemetry = post.robots.get(zone.robot)
            if telemetry is None:
                reject(zone, "battery_reserve", None, RESERVE_PCT,
                       f"No delivered battery telemetry for {zone.robot}; wait for its report")
                continue
            if zone.robot not in states:
                # An offline robot may have kept driving since its last report.
                age = max(0.0, now - telemetry["sent_t"])
                states[zone.robot] = {"pos": telemetry["pose"][:2], "distance": 0.0,
                                      "wh": spec.capacity_wh * telemetry["battery_pct"] / 100 -
                                      age * spec.cruise_w * self.energy_time_scale / 3600}
            state = states[zone.robot]
            zx, zy = centroid(zone.poly)
            candidates = np.argwhere(points_in_poly(cx, cy, zone.poly) & trav)
            if not len(candidates):
                if soft and np.any(points_in_poly(cx, cy, zone.poly) & trav_hazards):
                    warn(zone, "zone_unreachable", f"Zone {zone.id} is inside the no-go area: {zone.robot} skips it")
                else:
                    reject(zone, "zone_unreachable", False, True, f"Zone {zone.id} has no safe traversable cells")
                continue
            iy, ix = min(candidates, key=lambda p: (cx[tuple(p)] - zx) ** 2 + (cy[tuple(p)] - zy) ** 2)
            target = fp.to_world(int(ix), int(iy))
            outbound, home = route_length(state["pos"], target), route_length(target, fp.entry)
            if outbound is None or home is None:
                # cut off by the plan's no-go only, and the robot can still get home: it obeys the
                # no-go (searches what it can reach, or holds until the no-go changes)
                # (only when it cannot reach the zone at all: a zone it could reach but not leave
                # toward home still refuses)
                if (soft and outbound is None and route_length(state["pos"], fp.entry) is not None
                        and reachable_without_plan_no_go(state["pos"], target)
                        and reachable_without_plan_no_go(target, fp.entry)):
                    warn(zone, "zone_unreachable", f"The no-go area cuts {zone.robot} off from zone {zone.id}: it searches what it can reach")
                else:
                    reject(zone, "zone_unreachable", False, True, f"No safe route to {zone.id} and back home")
                continue
            state["distance"] += outbound + area(zone.poly) / 8.0
            state["pos"] = target
            energy = (state["distance"] + home) / spec.speed * spec.cruise_w * self.energy_time_scale / 3600
            reserve = 100 * (state["wh"] - energy) / spec.capacity_wh
            if reserve < RESERVE_PCT:
                reject(zone, "battery_reserve", round(reserve, 1), RESERVE_PCT,
                       f"{zone.robot} estimated reserve {reserve:.1f}%, minimum {RESERVE_PCT:.0f}%")
            can_go_dark = zone.comms == "lost_link_ok" and plan.lost_link_budget_s > 0
            if not can_go_dark and not self._comms(target, post.relays):
                reject(zone, "comms_plan", False, True,
                       f"Zone {zone.id} predicts a dead zone; use a relay chain or lost_link_ok with a positive budget")
        result = {"ok": not violations, "plan_id": plan.plan_id, "violations": violations}
        if warnings:   # additive: only when a no-go area overrides part of the plan
            result["warnings"] = warnings
        return result

    def _escape_start(self, start, trav, grid, blocked):
        sx, sy = start
        if trav[sy, sx]:
            return start, 0.0
        fp = self.prior
        # Only a new responder exclusion can permit this estimate. Occupied cells
        # and the building's static hazards never become traversable here.
        if (not self.global_no_go or not blocked[sy, sx] or fp.nogo[sy, sx]
                or grid[sy, sx] == OCC):
            return None
        limit = int(6.0 / fp.cell)  # same coordinate window as Rayan's physical escape
        seen, queue = {start}, deque([(sx, sy, 0)])
        while queue:
            x, y, steps = queue.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (not fp.in_bounds(nx, ny) or (nx, ny) in seen or grid[ny, nx] == OCC
                        or fp.nogo[ny, nx] or abs(nx - sx) > limit or abs(ny - sy) > limit):
                    continue
                if trav[ny, nx]:
                    return (nx, ny), (steps + 1) * fp.cell
                seen.add((nx, ny))
                queue.append((nx, ny, steps + 1))
        return None
