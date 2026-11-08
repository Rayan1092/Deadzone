"""Seeded collapsed-building generator (Q&A only, never the main demo).

    py data/floorplans/generate.py --seed 42                   # -> data/floorplans/generated/gen_42.json
    py data/floorplans/generate.py --seed 42 --png out.png     # also draw a preview
    py data/floorplans/generate.py --seed 3 --size 80 60 --id showcase_01 --name "..." \\
        --out data/floorplans/showcase_01.json --png data/floorplans/showcase_01.png --check

Any seed gives a different collapsed building in the same JSON format as collapse_01, so
Sim(plan_path=...) loads it as is. Every building also gets a default search plan next to it
(`<file>.plan.json`, the P-1 format: zones per robot, `lost_link_ok` on zones the radio model
predicts dark), referenced as `default_plan` in the building JSON.

  small (default sizes 36x28 to 44x32, `--size` with height <= 34):
  layout     a central corridor from the entrance, rooms north and south of it with one door
             each, and a warehouse at the far end with a steel storage cage (metal walls)
  big (`--size 80 60` and the like):
  layout     two or three parallel halls joined by cross halls, rooms in bands between them,
             a warehouse across the far end with a steel cage, and a steel vault in the far
             band: two radio dead zones, more rooms, 4 survivors and 4 decoys
  materials  concrete outer walls, brick / drywall / concrete inside, metal cage and vault
  hazards    gas, fire, flooding, unstable floor (no-go zones), never over a door
  rubble     a few static debris piles, never sealing a room
  people     survivors (one in each steel dead zone) and decoys (radiator, engine, coffee
             machine), all reachable, using the runtime crops the detector already judges
  timeline   a disaster script made only of existing director actions (rubble, aftershock,
             overcurrent), in the shape of the `director` control value; big buildings get a
             three-area earthquake (second collapse 10 s after the first)

Every building is validated before it is written: everything reachable from the entrance
with the planner's wall inflation, survivors and decoys out of hazards and debris, rooms not
cut off, and every steel room verified as a radio dead zone (no direct link to the command
post). If a draw fails, the next variant of the same seed is tried, so a seed always gives
the same building. collapse_01.json is never touched.
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
from deadzone.network.propagation import LINK_DOWN_DBM, LINK_UP_DBM, rssi  # noqa: E402
from deadzone.robot import planning  # noqa: E402

VERSION = 2
SIZES = [(36, 28), (40, 30), (44, 32)]
BIG_H = 34                                         # taller than this -> multi-hall layout
MATERIALS = {"drywall": 4, "brick": 10, "concrete": 16, "metal": 22, "rubble": 8}
INNER = ["brick", "brick", "drywall", "concrete"]
ROOM_NAMES = ["Office A", "Office B", "Break Room", "Storage", "Boiler Room", "Loading Office",
              "Server Room", "Lab", "Locker Room", "Workshop", "Records", "Kitchen", "First Aid"]
MORE_NAMES = ["Open Office", "Archive", "Mail Room", "Copy Room", "Meeting Room", "Supply Closet",
              "Pump Room", "Electrical Room", "Canteen", "Reception", "Dispatch", "Cold Store",
              "Paint Shop", "Tool Crib", "Chemical Store", "Maintenance", "Dock Office", "Training Room",
              "Print Shop", "Quality Lab", "Packing", "Uniform Store", "Battery Room", "Compressor Room"]
HAZARDS = ["gas", "fire", "flooding", "unstable_floor"]
DECOYS = [("radiator", "neg_0001.png"), ("engine", "neg_0002.png"), ("coffee machine", "neg_0003.png")]
SURVIVOR_CROPS = ["pos_0001.png", "pos_0002.png", "pos_0003.png"]
# crops the model scores near 0.5 from a distance, each with a clear <name>_close.png: the robot
# says "AI unsure, moving closer" and decides on the close-up (showcase and key-N variants only)
UNSURE_PERSON, UNSURE_OBJECT = "unsure_person_01.png", "unsure_object_01.png"
DOOR_W = 1.2
MAX_VARIANTS = 40
ROBOTS = ["R1", "R2", "R3"]                        # the default plan assumes the demo's 3 robots
COMMS_MARGIN_DB = 6.0                              # "relay" only when the centroid is clearly in range


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


def draw(seed, variant, size=None):
    rng = random.Random(f"{seed}:{variant}")
    W, H = size if size else rng.choice(SIZES)
    if H > BIG_H:
        return draw_big(rng, float(W), float(H), seed, variant)
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
    info = {"cages": [cage], "cage_doors": [(door_x, cy_wall)], "xe": xe, "yS": yS, "yN": yN,
            "halls": [cy], "cross": [], "n_people": 3, "big": False}
    return data, rng, info


def draw_big(rng, W, H, seed, variant):
    """Multi-hall layout for big buildings: parallel east-west halls, rooms in the bands between
    them, cross halls through the middle bands, a warehouse across the east end with a steel
    cage, and a steel vault in the band farthest from the entrance (second radio dead zone)."""
    cw, ccw = 4.0, 3.0
    n_halls = max(2, int(round(H / 20)))
    hall_y = [round(H * (k + 1) / (n_halls + 1) * 2) / 2 for k in range(n_halls)]
    wh = rng.choice([12.0, 14.0, 16.0])
    xe = W - wh
    m = n_halls // 2                                  # the entrance opens into this hall
    cy = hall_y[m]
    n_cross = 2 if xe >= 50 else 1
    cross_x = [round(xe * (j + 1) / (n_cross + 1) * 2) / 2 for j in range(n_cross)]

    walls = [{"a": [0, 0], "b": [W, 0], "material": "concrete"},
             {"a": [W, 0], "b": [W, H], "material": "concrete"},
             {"a": [W, H], "b": [0, H], "material": "concrete"},
             *vwall(0, 0, H, "concrete", doors=[cy], width=2.0)]
    doors = [{"at": [0, cy], "width": 2.0, "axis": "y", "state": "open"}]
    rooms = []
    for k, y in enumerate(hall_y):
        rooms.append({"id": f"H{k + 1}", "name": f"Hall {'ABC'[k]}", "poly": rect(0, y - cw / 2, xe, y + cw / 2)})
    for j, x in enumerate(cross_x):
        rooms.append({"id": f"X{j + 1}", "name": f"Cross Hall {j + 1}",
                      "poly": rect(x - ccw / 2, hall_y[0], x + ccw / 2, hall_y[-1])})
    names = ROOM_NAMES + MORE_NAMES
    rng.shuffle(names)
    used = {}

    def next_name():
        base = names.pop(0) if names else rng.choice(ROOM_NAMES + MORE_NAMES)
        used[base] = used.get(base, 0) + 1
        return base if used[base] == 1 else f"{base} {used[base]}"

    # bands between the halls (and the outer walls); each band is a row of rooms
    bands = [(0.0, hall_y[0] - cw / 2)]
    bands += [(hall_y[k] + cw / 2, hall_y[k + 1] - cw / 2) for k in range(n_halls - 1)]
    bands.append((hall_y[-1] + cw / 2, H))
    far_band = len(bands) - 1 if abs(bands[-1][0] - cy) >= abs(cy - bands[0][1]) else 0
    room_doors, band_rooms = [], []
    vault = None
    for b, (y0, y1) in enumerate(bands):
        edge = b in (0, len(bands) - 1)
        # x segments: cross halls cut the middle bands only
        cuts = [] if edge else [(x - ccw / 2, x + ccw / 2) for x in cross_x]
        segs, x = [], 0.0
        for a, c in cuts:
            segs.append((x, a))
            x = c
        segs.append((x, xe))
        row = []
        for sx0, sx1 in segs:
            xs = split(rng, sx0, sx1, lo=6.0, hi=11.0)
            for a, c in zip(xs, xs[1:]):
                row.append([a, c])
        # the vault: the room nearest the middle of the far band
        if b == far_band:
            vault = min(range(len(row)), key=lambda i: abs((row[i][0] + row[i][1]) / 2 - xe / 2))
        prefix = "ABCD"[b]
        band_mat = rng.choice(["brick", "drywall"])
        for i, (a, c) in enumerate(row):
            rid = f"{prefix}{i + 1}"
            is_vault = b == far_band and i == vault
            # door side: edge bands open toward their one hall, middle bands alternate
            if b == 0:
                low = False
            elif b == len(bands) - 1:
                low = True
            else:
                low = i % 2 == 0
            wall_y = y0 if low else y1
            mat = "metal" if is_vault else band_mat
            d = r1(rng.uniform(a + 1.5, c - 1.5))
            walls += hwall(wall_y, a, c, mat, doors=[d])
            if not edge:                              # the other long wall faces the other hall
                walls += hwall(y1 if low else y0, a, c, mat)
            doors.append({"at": [d, r1(wall_y)], "width": DOOR_W, "axis": "x",
                          "state": rng.choice(["open", "open", "broken"])})
            room_doors.append((rid, (d, wall_y)))
            room = {"id": rid, "name": "Steel Vault" if is_vault else next_name(), "poly": rect(a, y0, c, y1)}
            if is_vault:
                room["steel"] = True
            rooms.append(room)
            band_rooms.append(room)
            if i > 0 and abs(a - row[i - 1][1]) < 1e-6:  # divider between neighbouring rooms
                prev_vault = b == far_band and i - 1 == vault
                walls += vwall(a, y0, y1, "metal" if (is_vault or prev_vault) else rng.choice(INNER))
        for a, c in cuts:                             # cross hall side walls through this band
            walls += vwall(a, y0, y1, "concrete") + vwall(c, y0, y1, "concrete")
    walls += vwall(xe, 0, H, "concrete", doors=hall_y, width=cw)
    rooms.append({"id": "E1", "name": "Warehouse Floor", "poly": rect(xe, 0, W, H)})

    # steel storage cage against the east wall, north or south corner, door facing the hall
    cgw, cgh = rng.uniform(5.0, 7.0), rng.uniform(6.0, 9.0)
    north = rng.random() < 0.5
    cx0 = W - cgw
    cy_wall = H - cgh if north else cgh
    door_x = r1(W - rng.uniform(1.0, 1.8))
    walls += hwall(cy_wall, cx0, W, "metal", doors=[door_x])
    walls += vwall(cx0, cy_wall, H, "metal") if north else vwall(cx0, 0, cy_wall, "metal")
    doors.append({"at": [door_x, r1(cy_wall)], "width": DOOR_W, "axis": "x", "state": "open"})
    cage = rect(cx0, cy_wall, W, H) if north else rect(cx0, 0, W, cy_wall)
    rooms.append({"id": "E2", "name": "Steel Storage Cage", "poly": cage, "steel": True})
    py = cy_wall + (3.0 if north else -3.0)           # shelf inside: no line of sight from the door
    walls.append({"a": [r1(cx0 + 1.6), r1(py)], "b": [r1(W), r1(py)], "material": "metal"})
    for _ in range(rng.randint(1, 3)):                # loose metal shelving in the hall
        sy = r1(rng.uniform(3, H - 3))
        sx = r1(rng.uniform(xe + 1.5, W - cgw - 4))
        walls.append({"a": [sx, sy], "b": [r1(sx + rng.uniform(2.5, 4)), sy], "material": "metal"})

    # hazards: part of a room, on the side away from its door (never over a door, never the vault)
    hazards = []
    pool = [r for r in band_rooms if not r.get("steel")]
    for k, room in enumerate(rng.sample(pool, k=min(len(pool), rng.randint(3, 5)))):
        (x0, y0), (x1, _), (_, y1) = room["poly"][0], room["poly"][1], room["poly"][2]
        door_y = dict(room_doors)[room["id"]][1]
        depth = (y1 - y0) * rng.uniform(0.3, 0.55)
        hy0, hy1 = (y1 - depth, y1 - 0.3) if abs(door_y - y0) < 1e-6 else (y0 + 0.3, y0 + depth)
        hazards.append({"id": f"H{k + 1}", "type": rng.choice(HAZARDS),
                        "poly": rect(x0 + 0.3, hy0, x1 - 0.3, hy1)})

    rubble = []
    for k in range(rng.randint(5, 9)):
        s = rng.uniform(1.0, 2.0)
        x, y = rng.uniform(2, W - 2), rng.uniform(2, H - 2)
        rubble.append({"id": f"RB{k + 1}", "poly": rect(x - s / 2, y - s / 2, x + s / 2, y + s / 2),
                       "height": r1(rng.uniform(0.8, 1.6))})

    vault_room = next(r for r in band_rooms if r.get("steel"))
    vault_door = dict(room_doors)[vault_room["id"]]
    data = {"id": f"gen_{seed}", "name": f"Generated collapse #{seed}", "size": [W, H], "cell": 0.25,
            "wall_height": 3.0, "materials": dict(MATERIALS), "walls": walls, "doors": doors,
            "rooms": rooms, "rubble": rubble, "hazards": hazards, "survivors": [], "decoys": [],
            "entry": [1.0, cy], "command_post": {"pos": [-2.0, cy], "tx_dbm": 20},
            "generator": {"seed": seed, "variant": variant, "version": VERSION, "people": 4,
                          "layout": "multi_hall", "halls": hall_y, "cross_halls": cross_x}}
    info = {"cages": [cage, vault_room["poly"]], "cage_doors": [(door_x, cy_wall), vault_door],
            "xe": xe, "halls": hall_y, "cross": cross_x, "n_people": 4, "big": True,
            "entry_hall": rect(0, cy - cw / 2, xe, cy + cw / 2)}
    return data, rng, info


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
    """Survivors and decoys on reachable cells, out of hazards. One survivor per steel dead zone
    (as deep inside as it gets), the rest spread out; decoys never inside a dead zone."""
    fp = FloorPlan(data)
    reach = reachable(fp)
    iy, ix = np.nonzero(reach)
    pts = [((x + 0.5) * fp.cell, (y + 0.5) * fp.cell) for x, y in zip(ix, iy)]
    entry = fp.entry
    far = [p for p in pts if math.dist(p, entry) >= 8 and
           not any(in_poly(p, h["poly"]) for h in data["hazards"])]
    rng.shuffle(far)
    n = info.get("n_people", 3)
    chosen = []
    for cage, door in zip(info["cages"], info["cage_doors"]):
        inside = [p for p in far if in_poly(p, cage)]
        if not inside:
            return False
        inside.sort(key=lambda p: -math.dist(p, door))   # the dark survivor, far from the door
        chosen.append(inside[0])
    if info.get("big"):
        # big buildings take long to search (3 robots, 4,800 m2): one person collapsed in the
        # entrance hall 12 to 22 m in, where the robots pass in the first minute, so the showcase
        # pays off early; the dead-zone survivors stay the hard ones
        near = [p for p in far if 12 <= math.dist(p, entry) <= 22 and in_poly(p, info["entry_hall"])
                and all(math.dist(p, c) >= 6 for c in chosen)]
        if not near:
            return False
        chosen.append(near[0])
    for p in far:
        if len(chosen) == n:
            break
        if all(math.dist(p, c) >= 6 for c in chosen):
            chosen.append(p)
    if len(chosen) < n:
        return False
    data["survivors"] = [{"id": f"S{k + 1}", "pos": [r1(x), r1(y)], "thermal": SURVIVOR_CROPS[k % len(SURVIVOR_CROPS)]}
                         for k, (x, y) in enumerate(chosen)]
    if info.get("big"):
        # the entrance-hall survivor and the second decoy use the crops the model is unsure about
        # from a distance, so the showcase shows "AI unsure, moving closer" in its first minute
        data["survivors"][len(info["cages"])]["thermal"] = UNSURE_PERSON
    decoys = []
    for p in far:
        if len(decoys) == n:
            break
        if all(math.dist(p, c) >= 4 for c in chosen + decoys) and not any(in_poly(p, c) for c in info["cages"]):
            decoys.append(p)
    if len(decoys) < n:
        return False
    data["decoys"] = [{"id": f"D{k + 1}", "label": DECOYS[k % len(DECOYS)][0], "pos": [r1(x), r1(y)],
                       "thermal": DECOYS[k % len(DECOYS)][1]} for k, (x, y) in enumerate(decoys)]
    if info.get("big") and len(data["decoys"]) > 1:
        data["decoys"][1]["thermal"] = UNSURE_OBJECT
    return True


def make_timeline(data, rng, info):
    """Disaster script from existing director actions only (`director` control values)."""
    W, H = data["size"]
    cy = data["entry"][1]
    if not info.get("big"):
        x_cor = r1(rng.uniform(6, info["xe"] - 3))
        hall = [r1(rng.uniform(info["xe"] + 2, W - 6)), r1(rng.uniform(3, H - 3))]
        return [
            {"t": rng.randint(70, 110), "do": "rubble", "at": [x_cor, r1(cy + rng.uniform(-0.5, 0.5))], "size": 1.4,
             "label": "Ceiling tiles come down in the main corridor"},
            {"t": rng.randint(130, 170), "do": "overcurrent", "robot": rng.choice(ROBOTS), "duration_s": 1.0,
             "label": "A wheel jams on debris"},
            {"t": rng.randint(180, 230), "do": "aftershock", "at": hall,
             "label": "Aftershock: part of the warehouse roof collapses (the first relay is lost if one is up)"},
        ]
    # big building: a three-area earthquake, the second collapse 10 s after the first
    t1 = rng.randint(170, 190)
    cross = rng.choice(info["cross"])
    far_hall = info["halls"][-1] if info["halls"][-1] != cy else info["halls"][0]
    return [
        {"t": rng.randint(70, 100), "do": "rubble", "at": [r1(rng.uniform(6, 16)), r1(cy + rng.uniform(-0.5, 0.5))],
         "size": 1.4, "label": "Ceiling tiles come down in the entrance hall"},
        {"t": rng.randint(120, 150), "do": "overcurrent", "robot": rng.choice(ROBOTS), "duration_s": 1.0,
         "label": "A wheel jams on debris"},
        {"t": t1, "do": "aftershock", "at": [r1(rng.uniform(info["xe"] + 2, W - 8)), r1(rng.uniform(4, H - 4))],
         "label": "Earthquake, area 1 of 3: the warehouse roof comes down (a powered relay is lost if one is up)"},
        {"t": t1 + 10, "do": "aftershock", "at": [r1(cross), r1(rng.uniform(info["halls"][0] + 2, info["halls"][-1] - 2))],
         "label": "Area 2 of 3, ten seconds later: the cross hall collapses"},
        {"t": rng.randint(225, 250), "do": "aftershock", "at": [r1(rng.uniform(8, info["xe"] - 8)), r1(far_hall)],
         "label": "Area 3 of 3: the far hall collapses"},
    ]


def steel_rooms(data):
    return [r for r in data["rooms"] if r.get("steel") or r["id"] == "E2"]


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
    for room in steel_rooms(data):
        (x0, y0), (x1, _), (_, y1) = room["poly"][0], room["poly"][1], room["poly"][2]
        mid = ((x0 + x1) / 2 + 0.6, (y0 + y1) / 2)
        if rssi(fp, data["command_post"]["pos"], mid, data["command_post"]["tx_dbm"]) >= LINK_UP_DBM:
            problems.append(f"steel room {room['id']} is not a radio dead zone")
    n = data.get("generator", {}).get("people", 3)
    if len(data["survivors"]) != n or len(data["decoys"]) != n:
        problems.append(f"need {n} survivors and {n} decoys")
    return problems


def default_plan(data, robots=ROBOTS):
    """Default search plan in the P-1 format (phone plan schema), built from the rooms: zones are
    runs of neighbouring hazard-free rooms plus the halls and the warehouse, split between the
    deployed robots (default R1..R3) west to east by area. A zone whose centre the radio model
    does not predict clearly in range of the command post is `lost_link_ok` (so every steel dead
    zone is), the rest `relay`. Rooms with a hazard keep only their door-side strip, so no zone
    overlaps a no-go area (the safety checker rejects that)."""
    robots = list(robots)
    fp = FloorPlan(data)
    cmd = data["command_post"]
    hazards = data["hazards"]
    steel_ids = {r["id"] for r in steel_rooms(data)}
    steel_centres = [((r["poly"][0][0] + r["poly"][2][0]) / 2, (r["poly"][0][1] + r["poly"][2][1]) / 2)
                     for r in steel_rooms(data)]

    def bounds(poly):
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        return min(xs), min(ys), max(xs), max(ys)

    pieces = []                                       # (x0, y0, x1, y1) rectangles, hazard free
    for room in data["rooms"]:
        if room["id"] in steel_ids and room["id"] == "E2":
            continue                                  # inside the warehouse zone already
        x0, y0, x1, y1 = bounds(room["poly"])
        inside = [bounds(h["poly"]) for h in hazards if in_poly([(h["poly"][0][0] + h["poly"][2][0]) / 2,
                                                                   (h["poly"][0][1] + h["poly"][2][1]) / 2], room["poly"])]
        if not inside:
            pieces.append((x0, y0, x1, y1))
            continue
        hx0, hy0, hx1, hy1 = inside[0]
        gap = 0.3
        if hy0 - y0 > y1 - hy1:                                    # hazard at the top: keep the bottom strip
            if (hy0 - gap) - y0 >= 2.5:
                pieces.append((x0, y0, x1, hy0 - gap))
        elif y1 - (hy1 + gap) >= 2.5:                              # hazard at the bottom: keep the top strip
            pieces.append((x0, hy1 + gap, x1, y1))
    # merge runs of neighbouring rooms with the same y extent (same band, touching in x)
    pieces.sort(key=lambda p: (p[1], p[3], p[0]))
    merged = []
    for p in pieces:
        if merged and abs(merged[-1][1] - p[1]) < 1e-6 and abs(merged[-1][3] - p[3]) < 1e-6 \
                and abs(merged[-1][2] - p[0]) < 1e-6:
            merged[-1] = (merged[-1][0], p[1], p[2], p[3])
        else:
            merged.append(p)
    # split west to east between the robots by area
    merged.sort(key=lambda p: ((p[0] + p[2]) / 2, p[1]))
    total = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in merged)
    zones, acc, robot = [], 0.0, 0
    entry = data["entry"]
    for x0, y0, x1, y1 in merged:
        a = (x1 - x0) * (y1 - y0)
        if robot < len(robots) - 1 and acc + a / 2 > total * (robot + 1) / len(robots):
            robot += 1
        acc += a
        centre = ((x0 + x1) / 2, (y0 + y1) / 2)
        level = rssi(fp, cmd["pos"], centre, cmd["tx_dbm"])
        # a zone that holds a steel dead zone may go dark even if its centre is in range
        # (the warehouse floor is in line of sight down the corridor, the cage inside it is not)
        holds_dead_zone = any(in_poly(steel_centre, rect(x0, y0, x1, y1)) for steel_centre in steel_centres)
        zones.append({"robot": robots[robot], "poly": rect(x0, y0, x1, y1), "dist": math.dist(entry, centre),
                      "comms": "lost_link_ok" if holds_dead_zone or level < LINK_DOWN_DBM + COMMS_MARGIN_DB else "relay"})
    plan_zones = []
    for rid in robots:
        mine = sorted([z for z in zones if z["robot"] == rid], key=lambda z: z["dist"])
        for k, z in enumerate(mine):
            plan_zones.append({"id": f"Z{len(plan_zones) + 1}", "robot": rid, "priority": min(10, k + 1),
                               "comms": z["comms"], "poly": z["poly"]})
    # big buildings: trips out of signal are long, so the dark budget is three minutes (P-1 uses 60 s)
    return {"plan_id": f"P-{data['id']}", "author": "generator", "lost_link_budget_s": 180 if data["size"][1] > BIG_H else 60,
            "no_go": [], "zones": plan_zones}


def generate(seed, size=None, plan_id=None, name=None):
    """The building for this seed (first valid variant). Deterministic for (seed, size)."""
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if size is not None and (len(size) != 2 or min(size) < 24 or max(size) > 120):
        raise ValueError("size must be (width, height) in meters, 24 to 120")
    last = None
    for variant in range(MAX_VARIANTS):
        data, rng, info = draw(seed, variant, size)
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
            if plan_id:
                data["id"] = plan_id
            if name:
                data["name"] = name
            data["default_plan"] = f"{data['id']}.plan.json"
            data["validation"] = {"ok": True, "checks": [
                "everything reachable from the entrance with 1-cell wall inflation",
                "survivors and decoys out of hazards and debris", "no hazard over a door",
                "every room at least 30% reachable", "every steel room has no direct link to the command post"]}
            return data
    raise RuntimeError(f"seed {seed}: no valid building in {MAX_VARIANTS} variants ({last})")


def variant_of(base, seed):
    """Key N: the same building with the people shuffled. A validated variant of `base`
    (collapse_01): walls, rooms, doors, hazards, rubble, entry and command post stay byte for
    byte; one survivor stays deep inside every steel dead zone (the S1-style dark find), the other
    survivors and all decoys move to new reachable cells out of hazards and debris, at least 8 m
    from the entrance, people 6 m apart, decoys 4 m from everyone and never inside a dead zone.
    Crops stay with their slot (S1 keeps pos_0001.png ...), so the detector's verdicts are the
    same as in the demo. Deterministic for (base id, seed)."""
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    base_id = base["id"]
    inherited = set(validate(base))     # geometry findings the base already has (collapse_01's gas
    for attempt in range(MAX_VARIANTS):  # room is mostly hazard); a variant is judged on its people only
        rng = random.Random(f"variant:{base_id}:{seed}:{attempt}")
        data = json.loads(json.dumps(base))
        fp = FloorPlan(data)
        reach = reachable(fp)
        iy, ix = np.nonzero(reach)
        entry = fp.entry
        far = [((x + 0.5) * fp.cell, (y + 0.5) * fp.cell) for x, y in zip(ix, iy)]
        far = [p for p in far if math.dist(p, entry) >= 8 and not any(in_poly(p, h["poly"]) for h in data["hazards"])]
        rng.shuffle(far)
        steel = [r["poly"] for r in steel_rooms(data)]
        chosen = []
        for poly in steel:
            inside = sorted((p for p in far if in_poly(p, poly)), key=lambda p: -math.dist(p, entry))
            if not inside:
                break
            chosen.append(rng.choice(inside[:max(1, len(inside) // 3)]))   # the deep third of the room
        for p in far:
            if len(chosen) == len(base["survivors"]):
                break
            if not any(in_poly(p, s) for s in steel) and all(math.dist(p, c) >= 6 for c in chosen):
                chosen.append(p)
        decoys = []
        for p in far:
            if len(decoys) == len(base.get("decoys", [])):
                break
            if not any(in_poly(p, s) for s in steel) and all(math.dist(p, c) >= 4 for c in chosen + decoys):
                decoys.append(p)
        if len(chosen) < len(base["survivors"]) or len(decoys) < len(base.get("decoys", [])):
            continue
        data["survivors"] = [dict(s, pos=[r1(x), r1(y)]) for s, (x, y) in zip(base["survivors"], chosen)]
        data["decoys"] = [dict(d, pos=[r1(x), r1(y)]) for d, (x, y) in zip(base.get("decoys", []), decoys)]
        # the last survivor and the last decoy take the "unsure from a distance" crops, so key N
        # also shows the look-closer moment; the dead-zone survivor keeps the demo's crop
        if len(data["survivors"]) > len(steel):
            data["survivors"][-1]["thermal"] = UNSURE_PERSON
        if data["decoys"]:
            data["decoys"][-1]["thermal"] = UNSURE_OBJECT
        data["id"] = f"{base_id}_v{seed}"
        data["name"] = f"{base['name']}, variant {seed}"
        data["generator"] = {"kind": "variant", "base": base_id, "seed": seed, "attempt": attempt, "version": VERSION,
                             "people": len(chosen)}
        data["default_plan"] = f"{data['id']}.plan.json"
        if not [p for p in validate(data) if p not in inherited]:
            data["validation"] = {"ok": True, "checks": [
                "same walls, rooms, hazards, debris, entry and command post as the base building",
                "one survivor deep inside every steel dead zone", "survivors and decoys reachable, out of hazards and debris",
                "every steel room has no direct link to the command post"]}
            return data
    raise RuntimeError(f"{base_id} variant {seed}: no valid placement in {MAX_VARIANTS} attempts")


def write_variant_index(folder):
    """variants/index.json: the files in the folder, for the reset-into-floorplan control to pick from."""
    files = sorted(p.name for p in Path(folder).glob("*.json") if not p.name.endswith(".plan.json") and p.name != "index.json")
    entries = []
    for name in files:
        d = json.loads((Path(folder) / name).read_text(encoding="utf-8"))
        entries.append({"file": name, "id": d["id"], "name": d["name"], "base": d.get("generator", {}).get("base"),
                        "default_plan": d.get("default_plan")})
    (Path(folder) / "index.json").write_text(json.dumps({"variants": entries}, indent=1), encoding="utf-8")
    return entries


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


def check_plan(path, plan):
    """Run the default plan through the real safety checker on a fresh headless sim (3 robots).
    Returns the checker result; `ok` must be true for the plan to be dispatchable."""
    from deadzone.command.plan import PlanManager, SearchPlan
    from deadzone.command.safety import SafetyChecker
    from deadzone.sim import Sim
    sim = Sim(plan_path=path, n_robots=len(ROBOTS), seed=7)
    sim.tick()                                        # Command hears the robots once
    manager = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
    manager.save(SearchPlan.model_validate(plan))
    return manager.check(plan["plan_id"])


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


def preview(data, path, plan=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    colors = {"concrete": "#3d3d3a", "brick": "#a5532f", "drywall": "#9c9a92", "metal": "#2a78d6"}
    hz = {"gas": "#eda100", "fire": "#e34948", "flooding": "#3987e5", "unstable_floor": "#8a6d3b"}
    robot_colors = {"R1": "#2ecc71", "R2": "#38bdf8", "R3": "#a78bfa"}
    W, H = data["size"]
    fig, ax = plt.subplots(figsize=(min(W / 4, 20), min(H / 4, 15) + 0.6), facecolor="#fcfcfb")
    if plan:
        for z in plan["zones"]:
            ax.add_patch(Polygon(z["poly"], facecolor=robot_colors.get(z["robot"], "#999"), alpha=0.10,
                                 edgecolor=robot_colors.get(z["robot"], "#999"), lw=0.8,
                                 ls="--" if z["comms"] == "lost_link_ok" else "-"))
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
    title = f"{data['name']} ({W:g} x {H:g} m)"
    if plan:
        title += "  ·  default plan: zone colours per robot, dashed = lost_link_ok"
    ax.set_title(title, loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor="#fcfcfb")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Seeded collapsed-building generator (Q&A only)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--size", type=float, nargs=2, metavar=("W", "H"), default=None,
                    help="building size in meters (default: a seeded choice of 36x28, 40x30, 44x32; "
                         "heights over 34 use the multi-hall layout)")
    ap.add_argument("--id", default=None, help="building id (default gen_<seed>)")
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--png", type=Path, default=None)
    ap.add_argument("--check", action="store_true", help="run the default plan through the safety checker")
    ap.add_argument("--variant-of", type=Path, default=None, metavar="BUILDING.json",
                    help="instead of a new building: the same building with survivors and decoys shuffled "
                         "(key N), written to data/floorplans/variants/<id>_v<seed>.json")
    args = ap.parse_args()
    if args.variant_of:
        base = json.loads(args.variant_of.read_text(encoding="utf-8"))
        data = variant_of(base, args.seed)
        out = args.out or HERE / "variants" / f"{data['id']}.json"
    else:
        data = generate(args.seed, size=tuple(args.size) if args.size else None, plan_id=args.id, name=args.name)
        out = args.out or HERE / "generated" / f"{data['id']}.json"
    if out.resolve() == (HERE / "collapse_01.json").resolve():
        sys.exit("refusing to overwrite collapse_01.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    plan = default_plan(data)
    plan_path = out.with_name(data["default_plan"])
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    plan_path.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    if args.png:
        preview(data, args.png, plan)
    if args.variant_of:
        index = write_variant_index(out.parent)
        print(f"wrote {out}: people shuffled, {len(data['survivors'])} survivors, {len(data['decoys'])} decoys; "
              f"index.json lists {len(index)} variant(s)")
    W, H = data["size"]
    g = data["generator"]
    print(f"wrote {out}: {W:g} x {H:g} m, {len(data['rooms'])} rooms, {len(steel_rooms(data))} steel dead zone(s), "
          f"{len(data['hazards'])} hazards, {len(data['rubble'])} debris piles, {len(data['survivors'])} survivors, "
          f"{sum(e['do'] == 'aftershock' for e in data.get('timeline', []))} collapse area(s), "
          f"variant {g.get('variant', g.get('attempt'))}")
    print(f"wrote {plan_path}: {len(plan['zones'])} zones, "
          f"{sum(z['comms'] == 'lost_link_ok' for z in plan['zones'])} lost_link_ok")
    if args.check:
        result = check_plan(out, plan)
        print("safety check:", "ok" if result["ok"] else result["violations"])
        if not result["ok"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
