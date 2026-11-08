// Where the furniture goes, as data: one layout used both to draw the props (Props.jsx) and
// to export their footprints into the floor plan `obstacles` list (scripts/export-obstacles.mjs)
// that Aziz's DZ_OBSTACLES=1 sim treats as solid. One source, so what you see is what robots
// bump into. No React or three here, so Node can run it.
//
// An item is { id, kind, x, y, rot, opts }: sim position, sim heading of the prop's local x
// (props face local +z), and the component's own options. Everything standing on the floor that
// a robot cannot drive through is `solid` and gets a footprint (desks, cabinets, shelves, pallets,
// the forklift, counters, boilers, chairs, carton piles); flat and wall-mounted dressing (papers,
// whiteboards, pipe runs 1.5 m up the wall, signs, extinguishers) stays visual only. Decoys (the
// radiator, the engine, the coffee cart) are thermal targets: a footprint around one would block
// the sim's line of sight to it, so they stay out until the sim looks past a target's own body.

export const N = 0             // back to the north wall, facing south
export const S = Math.PI       // back to the south wall
export const W = Math.PI / 2   // back to the west wall, facing east
export const E = -Math.PI / 2

// Footprint in the prop's local frame [x0, x1, z0, z1] (from the component geometry), its
// height, and the radio material. Toppled pieces lie on the floor.
const SOLID = {
  desk: () => ({ rect: [-0.7, 0.7, -0.35, 0.35], height: 1.17, material: 'metal' }),
  filing: () => ({ rect: [-0.23, 0.23, -0.3, 0.3], height: 1.32, material: 'metal' }),
  filingToppled: () => ({ rect: [0.66, 1.98, -0.3, 0.3], height: 0.53, material: 'metal' }),
  bookshelf: ({ len = 1.6 }) => ({ rect: [-len / 2, len / 2, -0.17, 0.17], height: 1.9, material: 'wood' }),
  bookshelfToppled: ({ len = 1.6 }) => ({ rect: [-len / 2, len / 2, -0.2, 1.7], height: 0.34, material: 'wood' }),
  shelving: ({ len = 2, depth = 0.5 }) => ({ rect: [-len / 2 - 0.02, len / 2 + 0.02, -depth / 2 - 0.02, depth / 2 + 0.02], height: 2.0, material: 'metal' }),
  pallet: () => ({ rect: [-0.6, 0.6, -0.5, 0.5], height: 0.9, material: 'wood' }),
  palletRack: ({ len = 2.7, depth = 0.8 }) => ({ rect: [-len / 2 - 0.04, len / 2 + 0.04, -depth / 2 - 0.03, depth / 2 + 0.03], height: 2.1, material: 'metal' }),
  forklift: () => ({ rect: [-1.0, 1.7, -0.66, 0.66], height: 2.2, material: 'metal' }),
  counter: ({ len = 3 }) => ({ rect: [-len / 2 - 0.01, len / 2 + 0.01, -0.31, 0.31], height: 0.9, material: 'wood' }),
  fridge: () => ({ rect: [-0.35, 0.35, -0.34, 0.38], height: 1.8, material: 'metal' }),
  vending: () => ({ rect: [-0.45, 0.45, -0.4, 0.41], height: 1.85, material: 'metal' }),
  boiler: () => ({ rect: [-1.53, 2.03, -0.76, 0.76], height: 2.8, material: 'metal' }),
  // a robot cannot drive through an office chair either: upright (seat and five-star base) or on its back
  chair: ({ tipped = false }) => (tipped
    ? { rect: [-0.42, 0.42, -0.16, 1.06], height: 0.52, material: 'metal' }
    : { rect: [-0.31, 0.31, -0.31, 0.31], height: 0.95, material: 'metal' }),
  // a pile of cartons (Boxes: up to 0.65 m wide, offsets ±0.2 / ±0.15, two per layer)
  boxes: ({ n = 3 }) => ({ rect: [-0.56, 0.56, -0.46, 0.46], height: Math.round(0.36 * Math.ceil(n / 2) * 100) / 100, material: 'wood' }),
}
export const WOOD_LOSS_DB = 4   // added to a floor plan's materials when it gets wooden pieces

export const isSolid = (kind) => kind in SOLID
// An item is solid unless it is marked visual only (see MAIN_RUN_BASELINE below).
const solidItem = (item) => isSolid(item.kind) && !item.opts?.visualOnly

// Sim-space footprint polygon of an item (local x along `rot`, local +z = (sin, -cos)).
export function footprint(item) {
  return solidItem(item) ? bodyFootprint(item) : null
}

// The floor area a piece covers whether or not the sim treats it as solid (visual-only pieces
// included), for checking that no robot path runs through what the screen draws.
export function bodyFootprint(item) {
  const spec = SOLID[item.kind]?.(item.opts ?? {})
  if (!spec) return null
  return { ...rectPoly(item, spec.rect), height: spec.height, material: spec.material }
}
function rectPoly(item, [x0, x1, z0, z1]) {
  const c = Math.cos(item.rot ?? 0)
  const s = Math.sin(item.rot ?? 0)
  const at = (lx, lz) => [item.x + lx * c + lz * s, item.y + lx * s - lz * c]
  return { poly: [at(x0, z0), at(x1, z0), at(x1, z1), at(x0, z1)] }
}

// ------------------------------------------------------------------ decoys
// Decoys are thermal targets at fixed sim positions (their hot spot) and are never solid (a
// footprint would block the sim's line of sight to them). The prop drawn for one must still not
// stand on a path a robot drives in the main run, or the robot visibly drives through it: in
// collapse_01 robots pass the engine's spot on both sides (with robot collisions on, R1 and R3 at
// sim 172-238 s, web/tests/fixtures/seed7-paths.json), so a compact engine (60%) stands 0.85 m
// north-west of it, clear of every path. The camera box and tags follow the model.
export const DECOY_HALF = { radiator: [0.48, 0.12], engine: [0.8, 0.45], 'coffee machine': [0.4, 0.3] } // Props.jsx half extents (x, z)
const MAIN_RUN_DECOY_MOVES = { D2: { at: [37, 12], x: 36.35, y: 12.55, rot: Math.PI / 2, scale: 0.6 } }
export function decoyLayout(fp) {
  const main = fp?.id === 'collapse_01'
  return (fp?.decoys ?? []).map((d, i) => {
    const mv = main ? MAIN_RUN_DECOY_MOVES[d.id] : null
    const moved = Boolean(mv) && mv.at[0] === d.pos[0] && mv.at[1] === d.pos[1]
    return { ...d, hotspot: d.pos, pos: moved ? [mv.x, mv.y] : d.pos, rot: moved ? mv.rot : 0.15 + i * 0.1, scale: moved ? mv.scale ?? 1 : 1 }
  })
}
export function decoyFootprint(d) {
  const [hx, hz] = (DECOY_HALF[d.label] ?? [0.4, 0.4]).map((v) => v * (d.scale ?? 1))
  return rectPoly({ x: d.pos[0], y: d.pos[1], rot: d.rot }, [-hx, hx, -hz, hz]).poly
}

// ------------------------------------------------------------------ the demo building
// collapse_01, placed by hand (each piece against its wall, robots' paths clear).
// The main run (seed 7, DZ_OBSTACLES=1) and docs/DEMO.md's beats were measured with the demo
// building's chairs and carton piles drive-through; making them solid moves every beat (the
// demo guard: D1 57.9 to 72.1 s, S1 reported 118.5 to 160.2 s, S2 219.4 to 110.2 s). They stay
// visual only here until Rayan re-baselines; set false, re-run the exporter and the guard.
// Key-N variants (Q&A only) get them solid. Visual-only pieces stand where no robot drives in the
// main run (web/tests/mainRunPaths.test.js checks every one against the recorded seed-7 paths).
export const MAIN_RUN_BASELINE = true
const LOOSE_IN_MAIN_RUN = new Set(['chair', 'boxes'])
function demoLayout(mainRun) {
  const L = []
  const add = (kind, x, y, rot = 0, opts = {}) => L.push({ kind, x, y, rot,
    opts: mainRun && MAIN_RUN_BASELINE && LOOSE_IN_MAIN_RUN.has(kind) ? { ...opts, visualOnly: true } : opts })
  // Office A
  add('desk', 2.2, 29.5, N); add('desk', 7.4, 29.5, N)
  add('chair', 2.4, 28.75, N); add('chair', 7.0, 28.5, N + 0.6, { tipped: true })
  add('filing', 0.45, 21.6, W); add('filing', 0.45, 22.1, W)
  add('bookshelf', 9.72, 23, E)
  add('papers', 4, 23.5, 0, { n: 7, seed: 11, spread: 2.2 })
  // Office B
  add('desk', 19.5, 21.6, E); add('desk', 19.5, 25.6, E)
  add('chair', 18.75, 21.4, E); add('chair', 10.4, 29.4, W, { tipped: true }) // tipped one in the corner: with robot collisions on, R3 passes its old spot
  add('whiteboard', 10.11, 23.5, W)
  add('bookshelfToppled', 12.6, 29.4, N, { len: 1.8 })   // face down off the north wall
  add('papers', 16.5, 21, 0, { n: 5, seed: 23 })
  // Break room
  add('counter', 25.5, 29.55, N, { len: 3.6 }); add('fridge', 31.45, 29.45, N)
  add('vending', 20.58, 20.2, W)
  add('chair', 20.5, 29.4, W, { tipped: true })   // in the corner: R2 crosses the middle of the room
  // Storage
  ;[3, 5.2, 9.6].forEach((y, i) => add('shelving', 0.42, y, W, { seed: 31 + i * 7 }))
  ;[3.4, 9.4].forEach((x, i) => add('shelving', x, 0.42, S, { seed: 61 + i * 7 }))
  add('boxes', 11.4, 12.35, 0, { n: 5, seed: 71 }); add('boxes', 10.8, 0.9, 0, { n: 3, seed: 79 })
  // Boiler room (gas no-go: robots never enter)
  add('boiler', 15.5, 5.2, Math.PI / 2); add('boiler', 20.5, 5.2, Math.PI / 2)
  add('pipeRun', 18, 0.3, S, { len: 11.4 }); add('pipeRun', 12.25, 6.5, W, { len: 12.4 })
  // Loading office
  add('desk', 31.5, 10.2, E)
  add('chair', 30.4, 9.5, E + 0.8, { tipped: true })
  add('filing', 24.45, 2, W)
  add('filingToppled', 24.9, 3.4, W + 0.3)
  add('papers', 27, 8, 0, { n: 6, seed: 41 })
  // Warehouse
  add('palletRack', 39.45, 16.5, E, { seed: 83 })
  add('forklift', 33.3, 1.6, 0)
  add('pallet', 32.85, 29.2, W, { seed: 91 })
  add('shelving', 39.6, 27.4, E, { len: 2.4, depth: 0.45, seed: 97 })
  return L
}

// ------------------------------------------------------------------ any building
// Each room is read from its name and furnished along its walls (desks and cabinets in offices,
// shelving and pallets in storage, a counter in break rooms, boilers in plant rooms, nothing in
// corridors), with a default for rooms we cannot classify. Everything hugs a wall, stays 1.2 m
// clear of door openings and 0.8 m from corners.
const KIND = [
  [/corridor|hall|spine|stair|lobby|entry|passage/i, 'corridor'],
  [/office|admin|reception|loading office|meeting|ward|clinic|theatre|radiology/i, 'office'],
  [/storage|store|warehouse|stock|cage|supply|lab|pharm|archive/i, 'storage'],
  [/break|kitchen|canteen|cafe|waiting|staff/i, 'break'],
  [/boiler|plant|mechanical|utility|electrical|server/i, 'plant'],
]
export function roomKind(name = '') {
  return (KIND.find(([re]) => re.test(name)) ?? [null, 'default'])[1]
}
// Fisher-Yates with the seeded generator: the same order on every JS engine. (A random sort
// comparator is engine-defined: Node 24, Node 26 and Chrome laid the same room out differently,
// so the exported obstacles stopped matching what another machine draws.)
function shuffle(list, r) {
  const a = [...list]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}
function prng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}
// Free spots along one side of a room, away from doors and corners. side: 'N' | 'S' | 'E' | 'W'.
function wallSlots(room, side, doors, step, inset) {
  const xs = room.poly.map((p) => p[0])
  const ys = room.poly.map((p) => p[1])
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const horiz = side === 'N' || side === 'S'
  const lo = (horiz ? x0 : y0) + 0.8
  const hi = (horiz ? x1 : y1) - 0.8
  const out = []
  for (let t = lo + step / 2; t <= hi - step / 2; t += step) {
    const x = horiz ? t : side === 'W' ? x0 + inset : x1 - inset
    const y = horiz ? (side === 'S' ? y0 + inset : y1 - inset) : t
    if (doors.some((d) => Math.hypot(d.at[0] - x, d.at[1] - y) < 1.2 + step / 2)) continue
    out.push({ x, y, rot: side === 'N' ? N : side === 'S' ? S : side === 'W' ? W : E })
  }
  return out
}
function roomLayout(room, fp) {
  const kind = roomKind(room.name)
  if (kind === 'corridor') return []
  const xs = room.poly.map((p) => p[0])
  const ys = room.poly.map((p) => p[1])
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const r = prng(Math.round(x0 * 7 + y0 * 13 + x1 * 3 + y1 * 5) + 101)
  const doors = fp.doors ?? []
  const sides = shuffle(['N', 'E', 'S', 'W'], r)
  const items = []
  const take = (side, step, inset, n, make) => {
    const slots = wallSlots(room, side, doors, step, inset)
    for (let i = 0; i < n && slots.length; i++) {
      const s = slots.splice(Math.floor(r() * slots.length), 1)[0]
      items.push({ ...s, ...make(i) })
    }
  }
  const area = (x1 - x0) * (y1 - y0)
  if (kind === 'office') {
    take(sides[0], 1.8, 0.45, Math.max(1, Math.round(area / 30)), () => ({ kind: 'desk' }))
    take(sides[1], 0.7, 0.4, 2, () => ({ kind: 'filing' }))
    take(sides[2], 2.0, 0.3, 1, () => ({ kind: 'bookshelf', opts: { len: 1.6 } }))
    items.push({ x: (x0 + x1) / 2 + (r() - 0.5) * 2, y: (y0 + y1) / 2 + (r() - 0.5) * 2, rot: 0, kind: 'papers', opts: { n: 6, seed: Math.round(x0 * 11 + y0) } })
  } else if (kind === 'storage') {
    take(sides[0], 2.2, 0.42, Math.max(1, Math.round(area / 25)), (i) => ({ kind: 'shelving', opts: { seed: i * 7 + 31 } }))
    take(sides[1], 2.2, 0.42, Math.max(1, Math.round(area / 40)), (i) => ({ kind: 'shelving', opts: { seed: i * 11 + 61 } }))
    if (area > 80) take(sides[2], 3.0, 0.5, 1, () => ({ kind: 'palletRack', opts: { seed: 83 } }))
    else take(sides[2], 1.4, 0.5, 1, () => ({ kind: 'pallet', opts: { seed: 91 } }))
  } else if (kind === 'break') {
    take(sides[0], 3.2, 0.42, 1, () => ({ kind: 'counter', opts: { len: 2.8 } }))
    take(sides[1], 1.0, 0.45, 1, () => ({ kind: 'fridge' }))
    take(sides[2], 1.2, 0.5, 1, () => ({ kind: 'vending' }))
    take(sides[3], 0.8, 0.5, 2, (i) => ({ kind: 'chair', opts: { tipped: i === 0 } }))
  } else if (kind === 'plant') {
    take(sides[0], 3.4, 0.9, Math.max(1, Math.round(area / 60)), () => ({ kind: 'boiler' }))
    const len = Math.min(x1 - x0, y1 - y0) - 1.5
    items.push({ x: (x0 + x1) / 2, y: y0 + 0.3, rot: S, kind: 'pipeRun', opts: { len: Math.max(2, (x1 - x0) - 1.5) } })
    if (len > 3) items.push({ x: x0 + 0.25, y: (y0 + y1) / 2, rot: W, kind: 'pipeRun', opts: { len: (y1 - y0) - 1.5 } })
  } else {
    // unknown room: a desk, a shelf and a cabinet is enough to say "people used this"
    take(sides[0], 1.8, 0.45, 1, () => ({ kind: 'desk' }))
    take(sides[1], 2.2, 0.42, 1, () => ({ kind: 'shelving', opts: { seed: 47 } }))
    take(sides[2], 0.7, 0.4, 1, () => ({ kind: 'filing' }))
  }
  return items
}

// ------------------------------------------------------------------ the whole building
const distToPoly = ([px, py], poly) => {
  let best = Infinity
  for (let i = 0; i < poly.length; i++) {
    const [ax, ay] = poly[i]
    const [bx, by] = poly[(i + 1) % poly.length]
    const dx = bx - ax
    const dy = by - ay
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy || 1)))
    best = Math.min(best, Math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
  }
  return best
}
const inside = ([px, py], poly) => {
  let hit = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i]
    const [xj, yj] = poly[j]
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) hit = !hit
  }
  return hit
}

export const CLEAR_PEOPLE_M = 0.6   // no solid piece within this of a survivor or decoy
export const CLEAR_DOOR_M = 0.5     // ...or of a door opening (beyond its half width)

// Every piece of furniture in this building, solid ones with their footprint. If the floor plan
// carries exported `obstacles`, exactly those solid pieces are drawn, so the picture always
// matches what the sim treats as solid. Otherwise solid pieces that would sit on a survivor, a
// decoy or a doorway (a generated building without an export) are left out.
export function furnitureLayout(fp, { generic = false } = {}) {
  if (!fp) return []
  // key-N variants are the demo building with the people moved: same furniture, minus pieces on them
  const demo = !generic && /^collapse_01(_v\d+)?$/.test(fp.id ?? '')
  const raw = demo ? demoLayout(fp.id === 'collapse_01') : (fp.rooms ?? []).flatMap((room) => roomLayout(room, fp))
  const people = [...(fp.survivors ?? []), ...(fp.decoys ?? [])].map((p) => p.pos)
  const doors = fp.doors ?? []
  const [Wd, Hd] = fp.size ?? [Infinity, Infinity]
  const exported = Array.isArray(fp.obstacles) ? new Set(fp.obstacles.map((o) => o.id)) : null
  const out = []
  raw.forEach((item, i) => {
    const id = `F${i + 1}`
    if (!solidItem(item)) { out.push({ ...item, id, solid: false }); return }
    const f = footprint(item)
    const poly = f.poly.map(([x, y]) => [Math.min(Wd, Math.max(0, x)), Math.min(Hd, Math.max(0, y))])
    // an exported list is what the sim treats as solid: draw exactly that
    if (exported) { if (!exported.has(id)) return } else {
      const blocks = people.some((p) => inside(p, poly) || distToPoly(p, poly) < CLEAR_PEOPLE_M) ||
        doors.some((d) => inside(d.at, poly) || distToPoly(d.at, poly) < (d.width ?? 1.2) / 2 + CLEAR_DOOR_M)
      if (blocks) return
    }
    out.push({ ...item, id, solid: true, poly, height: f.height, material: f.material })
  })
  return out
}

// The floor plan `obstacles` entries for Aziz's DZ_OBSTACLES=1 (id, poly, material, height;
// kind and x/y/rot for anyone who wants to redraw them).
export function obstaclesFor(fp) {
  const r2 = (v) => Math.round(v * 100) / 100
  return furnitureLayout({ ...fp, obstacles: undefined }).filter((it) => it.solid).map((it) => ({
    id: it.id, kind: it.kind, poly: it.poly.map(([x, y]) => [r2(x), r2(y)]), material: it.material, height: it.height,
    x: r2(it.x), y: r2(it.y), rot: Math.round(it.rot * 1000) / 1000,
  }))
}
