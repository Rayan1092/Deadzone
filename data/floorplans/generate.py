"""Seeded collapsed-building generator (Q&A only, never the main demo).

    py data/floorplans/generate.py --seed 42                   # -> data/floorplans/generated/gen_42.json
    py data/floorplans/generate.py --seed 42 --png out.png     # also draw a preview

Any seed gives a different collapsed building in the same JSON format as collapse_01, so
Sim(plan_path=...) loads it as is:

  layout     a central corridor from the entrance, rooms north and south of it with one door
             each, and a warehouse at the far end with a steel storage cage (metal walls)
  materials  concrete outer walls, brick / drywall / concrete inside, metal cage
  hazards    gas, fire, flooding, unstable floor (no-go zones), never over a door
  rubble     a few static debris piles, never sealing a room
  people     3 survivors (one in the steel cage when it is reachable) and 3 decoys
             (radiator, engine, coffee machine), all reachable, using the runtime crops the
             detector already judges
  timeline   a disaster script made only of existing director actions (rubble, aftershock,
             overcurrent), in the shape of the `director` control value

Every building is validated before it is written: everything reachable from the entrance
with the planner's wall inflation, survivors and decoys out of hazards and debris, rooms not
cut off, and the cage verified as a radio dead zone (no direct link to the command post).
If a draw fails, the next variant of the same seed is tried, so a seed always gives the same
building. collapse_01.json is never touched.
"""
import argparse
import json
import math
import random
import sys
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "server"))

from deadzone.floorplan import FloorPlan  # noqa: E402
from deadzone.network.propagation import LINK_UP_DBM, rssi  # noqa: E402
from deadzone.robot import planning  # noqa: E402

VERSION = 1
SIZES = [(36, 28), (40, 30), (44, 32)]
MATERIALS = {"drywall": 4, "brick": 10, "concrete": 16, "metal": 22, "rubble": 8}
INNER = ["brick", "brick", "drywall", "concrete"]
ROOM_NAMES = ["Office A", "Office B", "Break Room", "Storage", "Boiler Room", "Loading Office",
              "Server Room", "Lab", "Locker Room", "Workshop", "Records", "Kitchen", "First Aid"]
HAZARDS = ["gas", "fire", "flooding", "unstable_floor"]
DECOYS = [("radiator", "neg_0001.png"), ("engine", "neg_0002.png"), ("coffee machine", "neg_0003.png")]
SURVIVOR_CROPS = ["pos_0001.png", "pos_0002.png", "pos_0003.png"]
DOOR_W = 1.2
MAX_VARIANTS = 40


def r1(v):
    return round(float(v), 2)


def hwall(y, x0, x1, material, doors=()):
    """Horizontal wall from x0 to x1 at y, split around door centers (DOOR_W wide)."""
    out, x = [], x0
    for d in sorted(doors):
        a, b = d - DOOR_W / 2, d + DOOR_W / 2
        if a > x + 1e-6:
            out.append({"a": [r1(x), r1(y)], "b": [r1(a), r1(y)], "material": material})
        x = b
    if x1 > x + 1e-6:
        out.append({"a": [r1(x), r1(y)], "b": [r1(x1), r1(y)], "material": material})
    return out


def vwall(x, y0, y1, material, doors=(), width=DOOR_W):
    out, y = [], y0
    for d in sorted(doors):
        a, b = d - width / 2, d + width / 2
        if a > y + 1e-6:
            out.append({"a": [r1(x), r1(y)], "b": [r1(x), r1(a)], "material": material})
        y = b
    if y1 > y + 1e-6:
        out.append({"a": [r1(x), r1(y)], "b": [r1(x), r1(y1)], "material": material})
    return out


def rect(x0, y0, x1, y1):
    return [[r1(x0), r1(y0)], [r1(x1), r1(y0)], [r1(x1), r1(y1)], [r1(x0), r1(y1)]]


def split(rng, x0, x1, lo=7.0, hi=12.0):
    """Cut [x0, x1] into room widths between lo and hi (the last one takes the rest)."""
    xs, x = [x0], x0
    while x1 - x > hi:
        x += rng.uniform(lo, min(hi, x1 - x - lo)) if x1 - x - lo > lo else (x1 - x) / 2
        xs.append(round(x * 2) / 2)
        x = xs[-1]
    xs.append(x1)
    return xs


def draw(seed, variant):
    rng = random.Random(f"{seed}:{variant}")
    W, H = rng.choice(SIZES)
    cw = rng.choice([3.0, 4.0])
    cy = round(H / 2 * 2) / 2
    yS, yN = cy - cw / 2, cy + cw / 2
    wh = rng.choice([8.0, 10.0, 12.0])              # warehouse width at the far (east) end
    xe = W - wh

    walls = [{"a": [0, 0], "b": [W, 0], "material": "concrete"},
             {"a": [W, 0], "b": [W, H], "material": "concrete"},
             {"a": [W, H], "b": [0, H], "material": "concrete"},
             *vwall(0, 0, H, "concrete", doors=[cy], width=2.0)]
    doors = [{"at": [0, cy], "width": 2.0, "axis": "y", "state": "open"}]
    rooms = [{"id": "C1", "name": "Main Corridor", "poly": rect(0, yS, xe, yN)}]
    names = ROOM_NAMES[:]
    rng.shuffle(names)

    room_doors = []                                   # (room id, door xy) for hazard placement
    for side, (y0, y1, wall_y, prefix) in {"N": (yN, H, yN, "N"), "S": (0, yS, yS, "S")}.items():
        xs = split(rng, 0, xe)
        dxs = []
        for k, (a, b) in enumerate(zip(xs, xs[1:])):
            rid = f"{prefix}{k + 1}"
            rooms.append({"id": rid, "name": names.pop(), "poly": rect(a, y0, b, y1)})
            d = r1(rng.uniform(a + 1.5, b - 1.5))
            dxs.append(d)
            doors.append({"at": [d, wall_y], "width": DOOR_W, "axis": "x",
                          "state": rng.choice(["open", "open", "broken"])})
            room_doors.append((rid, (d, wall_y)))
            if k > 0:                                 # divider between neighbouring rooms
                walls += vwall(a, y0, y1, rng.choice(INNER))
        walls += hwall(wall_y, 0, xe, rng.choice(["brick", "drywall"]), doors=dxs)
    walls += vwall(xe, 0, yS, "concrete") + vwall(xe, yN, H, "concrete")
    rooms.append({"id": "E1", "name": "Warehouse Floor", "poly": rect(xe, 0, W, H)})

    # steel storage cage against the east wall, north or south corner, door facing the hall
    cgw, cgh = rng.uniform(4.0, 5.5), rng.uniform(5.5, min(8.0, H / 2 - 3))
    north = rng.random() < 0.5
    cx0 = W - cgw
    cy_wall = H - cgh if north else cgh
    door_x = r1(W - rng.uniform(1.0, 1.6))
    walls += hwall(cy_wall, cx0, W, "metal", doors=[door_x])
    walls += vwall(cx0, cy_wall, H, "metal") if north else vwall(cx0, 0, cy_wall, "metal")
    doors.append({"at": [door_x, r1(cy_wall)], "width": DOOR_W, "axis": "x", "state": "open"})
    cage = rect(cx0, cy_wall, W, H) if north else rect(cx0, 0, W, cy_wall)
    rooms.append({"id": "E2", "name": "Steel Storage Cage", "poly": cage})
    if rng.random() < 0.7:                            # shelf inside: no line of sight from the door
        py = cy_wall + (3.0 if north else -3.0)
        walls.append({"a": [r1(cx0 + 1.4), r1(py)], "b": [r1(W), r1(py)], "material": "metal"})
    if rng.random() < 0.5:                            # loose metal shelving in the hall
        sy = r1(rng.uniform(4, H - 4))
        walls.append({"a": [r1(xe + 1.5), sy], "b": [r1(xe + 1.5 + rng.uniform(2.5, 4)), sy], "material": "metal"})

    # hazards: part of a room, on the side away from its door (never over a door)
    hazards = []
    side_rooms = [r for r in rooms if r["id"][0] in "NS"]
    for k, room in enumerate(rng.sample(side_rooms, k=min(len(side_rooms), rng.randint(1, 3)))):
        (x0, y0), (x1, _), (_, y1) = room["poly"][0], room["poly"][1], room["poly"][2]
        door_y = dict(room_doors)[room["id"]][1]
        depth = (y1 - y0) * rng.uniform(0.3, 0.55)
        hy0, hy1 = (y1 - depth, y1 - 0.3) if abs(door_y - y0) < 1e-6 else (y0 + 0.3, y0 + depth)
        hazards.append({"id": f"H{k + 1}", "type": rng.choice(HAZARDS),
                        "poly": rect(x0 + 0.3, hy0, x1 - 0.3, hy1)})

    # static debris piles
    rubble = []
    for k in range(rng.randint(2, 4)):
        s = rng.uniform(1.0, 1.8)
        x, y = rng.uniform(2, W - 2), rng.uniform(2, H - 2)
        rubble.append({"id": f"RB{k + 1}", "poly": rect(x - s / 2, y - s / 2, x + s / 2, y + s / 2),
                       "height": r1(rng.uniform(0.8, 1.6))})

    data = {"id": f"gen_{seed}", "name": f"Generated collapse #{seed}", "size": [W, H], "cell": 0.25,
            "wall_height": 3.0, "materials": dict(MATERIALS), "walls": walls, "doors": doors,
            "rooms": rooms, "rubble": rubble, "hazards": hazards, "survivors": [], "decoys": [],
            "entry": [1.0, cy], "command_post": {"pos": [-2.0, cy], "tx_dbm": 20},
            "generator": {"seed": seed, "variant": variant, "version": VERSION}}
    return data, rng, {"cage": cage, "north": north, "door_x": door_x, "xe": xe, "yS": yS, "yN": yN}


def reachable(fp):
    """Cells the planner could stand in (1-cell inflation of walls, debris and hazards),
    reachable from the entrance on the truth map."""
    trav = ~planning.dilate(fp.occ | fp.nogo, 1)
    sx, sy = fp.to_cell(*fp.entry)
    seen = np.zeros_like(trav)
    if not trav[sy, sx]:
        return seen
    q = deque([(sx, sy)])
    seen[sy, sx] = True
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < fp.w and 0 <= ny < fp.h and trav[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((nx, ny))
    return seen


def in_poly(pt, poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs) <= pt[0] <= max(xs) and min(ys) <= pt[1] <= max(ys)


def place_people(data, rng, info):
    """Survivors and decoys on reachable cells, out of hazards. S1 goes into the cage."""
    fp = FloorPlan(data)
    reach = reachable(fp)
    iy, ix = np.nonzero(reach)
    pts = [((x + 0.5) * fp.cell, (y + 0.5) * fp.cell) for x, y in zip(ix, iy)]
    entry = fp.entry
    far = [p for p in pts if math.dist(p, entry) >= 8 and
           not any(in_poly(p, h["poly"]) for h in data["hazards"])]
    rng.shuffle(far)
    cage = [p for p in far if in_poly(p, info["cage"])]
    chosen = []
    if cage:                                          # the dark survivor
        cage.sort(key=lambda p: -abs(p[1] - (info["cage"][0][1] if info["north"] else info["cage"][2][1])))
        chosen.append(cage[0])
    for p in far:
        if len(chosen) == 3:
            break
        if all(math.dist(p, c) >= 6 for c in chosen):
            chosen.append(p)
    if len(chosen) < 3:
        return False
    data["survivors"] = [{"id": f"S{k + 1}", "pos": [r1(x), r1(y)], "thermal": SURVIVOR_CROPS[k]}
                         for k, (x, y) in enumerate(chosen)]
    decoys = []
    for p in far:
        if len(decoys) == 3:
            break
        if all(math.dist(p, c) >= 4 for c in chosen + decoys) and not in_poly(p, info["cage"]):
            decoys.append(p)
    if len(decoys) < 3:
        return False
    data["decoys"] = [{"id": f"D{k + 1}", "label": DECOYS[k][0], "pos": [r1(x), r1(y)], "thermal": DECOYS[k][1]}
                      for k, (x, y) in enumerate(decoys)]
    return True


def make_timeline(data, rng, info):
    """Disaster script from existing director actions only (`director` control values)."""
    W, H = data["size"]
    cy = data["entry"][1]
    x_cor = r1(rng.uniform(6, info["xe"] - 3))
    hall = [r1(rng.uniform(info["xe"] + 2, W - 6)), r1(rng.uniform(3, H - 3))]
    return [
        {"t": rng.randint(70, 110), "do": "rubble", "at": [x_cor, r1(cy + rng.uniform(-0.5, 0.5))], "size": 1.4,
         "label": "Ceiling tiles come down in the main corridor"},
        {"t": rng.randint(130, 170), "do": "overcurrent", "robot": rng.choice(["R1", "R2", "R3"]), "duration_s": 1.0,
         "label": "A wheel jams on debris"},
        {"t": rng.randint(180, 230), "do": "aftershock", "at": hall,
         "label": "Aftershock: part of the warehouse roof collapses (the first relay is lost if one is up)"},
    ]


def validate(data):
    """List of problems; empty means the building is good."""
    problems = []
    fp = FloorPlan(data)
    reach = reachable(fp)
    if not reach.any():
        return ["entrance blocked"]
    cx, cy = fp.cell_centers()
    from deadzone.geometry import points_in_poly
    for room in data["rooms"]:
        mask = points_in_poly(cx, cy, room["poly"]) & ~fp.occ & ~fp.nogo
        if mask.sum() and (reach & mask).sum() < 0.3 * mask.sum():
            problems.append(f"room {room['id']} mostly cut off")
    for kind in ("survivors", "decoys"):
        for s in data[kind]:
            ix, iy = fp.to_cell(*s["pos"])
            near = reach[max(0, iy - 2):iy + 3, max(0, ix - 2):ix + 3].any()
            if fp.occ[iy, ix] or fp.nogo[iy, ix] or not near:
                problems.append(f"{s['id']} not reachable or in debris / hazard")
    for d in data["doors"]:
        ix, iy = fp.to_cell(*d["at"])
        if fp.nogo[max(0, iy - 2):iy + 3, max(0, ix - 2):ix + 3].any():
            problems.append(f"hazard over the door at {d['at']}")
    cage = next((r for r in data["rooms"] if r["id"] == "E2"), None)
    if cage:
        (x0, y0), (x1, _), (_, y1) = cage["poly"][0], cage["poly"][1], cage["poly"][2]
        mid = ((x0 + x1) / 2 + 0.6, (y0 + y1) / 2)
        if rssi(fp, data["command_post"]["pos"], mid, data["command_post"]["tx_dbm"]) >= LINK_UP_DBM:
            problems.append("steel cage is not a radio dead zone")
    if len(data["survivors"]) != 3 or len(data["decoys"]) != 3:
        problems.append("need 3 survivors and 3 decoys")
    return problems


def generate(seed):
    """The building for this seed (first valid variant). Deterministic."""
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    last = None
    for variant in range(MAX_VARIANTS):
        data, rng, info = draw(seed, variant)
        # drop debris piles that would cut something off or sit on a door
        keep = []
        for rb in data["rubble"]:
            data["rubble"] = keep + [rb]
            near_door = any(math.dist(d["at"], [(rb["poly"][0][0] + rb["poly"][2][0]) / 2,
                                                (rb["poly"][0][1] + rb["poly"][2][1]) / 2]) < 2.5
                            for d in data["doors"])
            if not near_door and math.dist(data["entry"], rb["poly"][0]) > 4 and not validate_rooms_only(data):
                keep.append(rb)
        data["rubble"] = keep
        if not place_people(data, rng, info):
            last = ["could not place survivors / decoys"]
            continue
        data["timeline"] = make_timeline(data, rng, info)
        last = validate(data)
        if not last:
            data["validation"] = {"ok": True, "checks": [
                "everything reachable from the entrance with 1-cell wall inflation",
                "survivors and decoys out of hazards and debris", "no hazard over a door",
                "every room at least 30% reachable", "steel cage has no direct link to the command post"]}
            return data
    raise RuntimeError(f"seed {seed}: no valid building in {MAX_VARIANTS} variants ({last})")


def play(sim, timeline, done):
    """Headless timeline player: apply every event whose time has come, once. `done` is a set
    of event indexes already played (keep it between calls). The app version is Aziz's: each
    event is the `value` of a `{"action": "director"}` control message."""
    for i, ev in enumerate(timeline):
        if i in done or sim.time + 1e-6 < ev["t"]:
            continue
        done.add(i)
        if ev["do"] == "rubble":
            sim.drop_rubble(ev["at"], size=ev.get("size", 1.4))
        elif ev["do"] == "overcurrent":
            sim.inject_overcurrent(ev["robot"], duration_s=ev.get("duration_s", 1.0))
        elif ev["do"] == "aftershock":
            sim.aftershock(at=ev.get("at"), relay=ev.get("relay"))


def validate_rooms_only(data):
    fp = FloorPlan(data)
    reach = reachable(fp)
    if not reach.any():
        return ["entrance blocked"]
    cx, cy = fp.cell_centers()
    from deadzone.geometry import points_in_poly
    bad = []
    for room in data["rooms"]:
        mask = points_in_poly(cx, cy, room["poly"]) & ~fp.occ & ~fp.nogo
        if mask.sum() and (reach & mask).sum() < 0.3 * mask.sum():
            bad.append(room["id"])
    return bad


def preview(data, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    colors = {"concrete": "#3d3d3a", "brick": "#a5532f", "drywall": "#9c9a92", "metal": "#2a78d6"}
    hz = {"gas": "#eda100", "fire": "#e34948", "flooding": "#3987e5", "unstable_floor": "#8a6d3b"}
    W, H = data["size"]
    fig, ax = plt.subplots(figsize=(W / 4, H / 4 + 0.6), facecolor="#fcfcfb")
    for h in data["hazards"]:
        ax.add_patch(Polygon(h["poly"], color=hz[h["type"]], alpha=0.25, lw=0))
        ax.text(*np.mean(h["poly"], axis=0), h["type"].replace("_", " "), ha="center", fontsize=8, color="#52514e")
    for rb in data["rubble"]:
        ax.add_patch(Polygon(rb["poly"], color="#7a746a", alpha=0.8, lw=0))
    for w in data["walls"]:
        ax.plot([w["a"][0], w["b"][0]], [w["a"][1], w["b"][1]], color=colors[w["material"]], lw=3 if w["material"] != "drywall" else 2)
    for r in data["rooms"]:
        ax.text(*np.mean(r["poly"], axis=0), r["name"], ha="center", va="center", fontsize=7, color="#52514e", alpha=0.8)
    for s in data["survivors"]:
        ax.plot(*s["pos"], "o", color="#1baf7a", ms=9)
        ax.text(s["pos"][0] + 0.5, s["pos"][1] + 0.5, s["id"], fontsize=8)
    for d in data["decoys"]:
        ax.plot(*d["pos"], "s", color="#e87ba4", ms=7)
        ax.text(d["pos"][0] + 0.5, d["pos"][1] + 0.5, d["label"], fontsize=7)
    for ev in data["timeline"]:
        if "at" in ev:
            ax.plot(*ev["at"], "x", color="#e34948", ms=10, mew=2)
            ax.text(ev["at"][0] + 0.4, ev["at"][1] - 1.0, f"{ev['do']} {ev['t']} s", fontsize=7, color="#e34948")
    ax.plot(*data["entry"], ">", color="#0b0b0b", ms=10)
    ax.set_xlim(-3, W + 1)
    ax.set_ylim(-1, H + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"{data['name']} ({W} x {H} m)", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor="#fcfcfb")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--png", type=Path, default=None)
    args = ap.parse_args()
    data = generate(args.seed)
    out = args.out or HERE / "generated" / f"gen_{args.seed}.json"
    if out.resolve() == (HERE / "collapse_01.json").resolve():
        sys.exit("refusing to overwrite collapse_01.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    if args.png:
        preview(data, args.png)
    print(f"wrote {out}: {data['size'][0]} x {data['size'][1]} m, {len(data['rooms'])} rooms, "
          f"{len(data['hazards'])} hazards, {len(data['rubble'])} debris piles, variant {data['generator']['variant']}")


if __name__ == "__main__":
    main()
