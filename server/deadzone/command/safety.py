"""Planning estimates from the building prior and DELIVERED Command knowledge."""
from dataclasses import dataclass

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
        no_go_polys = [h["poly"] for h in fp.data.get("hazards", [])] + [g.poly for g in plan.no_go]
        for g in plan.no_go:
            blocked |= points_in_poly(cx, cy, g.poly)
        # Unknown cells use the pre-collapse prior. Only delivered observations
        # can add collapse debris to this grid; no truth rubble is read here.
        grid = np.where(fp.occ | (post.map == OCC), OCC, FREE).astype(np.uint8)
        trav = planning.traversable(grid, blocked)
        violations, states, route_cache = [], {}, {}

        def reject(zone, rule, value, limit, msg):
            violations.append({"robot": zone.robot, "zone": zone.id, "rule": rule,
                               "value": value, "limit": limit, "msg": msg})

        def route_length(start, goal):
            a, b = fp.to_cell(*start), fp.to_cell(*goal)
            key = a, b
            if key not in route_cache:
                if not all(fp.in_bounds(*p) and trav[p[1], p[0]] for p in (a, b)):
                    route_cache[key] = None
                else:
                    path = planning.astar(trav, a, b)
                    route_cache[key] = None if path is None else planning.path_length(
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
            if any(overlap(zone.poly, poly) for poly in no_go_polys):
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
                reject(zone, "zone_unreachable", False, True, f"Zone {zone.id} has no safe traversable cells")
                continue
            iy, ix = min(candidates, key=lambda p: (cx[tuple(p)] - zx) ** 2 + (cy[tuple(p)] - zy) ** 2)
            target = fp.to_world(int(ix), int(iy))
            outbound, home = route_length(state["pos"], target), route_length(target, fp.entry)
            if outbound is None or home is None:
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
        return {"ok": not violations, "plan_id": plan.plan_id, "violations": violations}
