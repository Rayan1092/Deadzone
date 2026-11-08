"""Responder route ordering from delivered knowledge, never medical triage."""
import math

from ..floorplan import OCC

RANK = {"low": 0, "medium": 1, "high": 2}


def route_cells(path, prior):
    """Sample every segment, including endpoints; compact routes keep their turns."""
    if len(path) == 1:
        yield prior.to_cell(*path[0])
    for a, b in zip(path, path[1:]):
        steps = max(1, math.ceil(math.dist(a, b) / (prior.cell / 2)))
        for i in range(steps + 1):
            f = i / steps
            yield prior.to_cell(a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))


def rescue_order(post, now, prior):
    view = post.view(now)
    known = {s["id"] for s in view["survivors"]}
    command_map = post.map.copy()
    survivors = []
    for route in view["routes"]:
        if route["survivor"] not in known:
            continue
        high, medium = set(), set()
        clearance = route.get("clearance_m")
        if clearance is None:
            medium.add("clearance_unknown")
        elif clearance < .25:
            high.add("very_low_clearance")
        elif clearance < .5:
            medium.add("narrow_clearance")
        if now - route["t"] > 60:
            medium.add("route_older_than_60s")
        for ix, iy in route_cells(route["path"], prior):
            if prior.in_bounds(ix, iy):
                if command_map[iy, ix] >= OCC:
                    high.add("reported_route_obstructed")
                if prior.nogo[iy, ix]:
                    high.add("known_hazard_on_route")
        survivors.append({"survivor": route["survivor"], "by": route["by"],
                          "length_m": route["length_m"], "risk": "high" if high else "medium" if medium else "low",
                          "reasons": sorted(high | medium), "reported_t": route["reported_t"]})
    survivors.sort(key=lambda s: (RANK[s["risk"]], s["length_m"], s["survivor"]))
    return {"generated_at": now, "source": "command", "survivors": survivors}
