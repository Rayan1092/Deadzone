import { Component, Suspense, useLayoutEffect, useMemo, useRef } from 'react'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { mergeGeometries, mergeVertices } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { SimplifyModifier } from 'three/examples/jsm/modifiers/SimplifyModifier.js'
import { w2t } from './util'
import { materials, tiledSet } from './textures'
import { chunks } from './Debris'
import { wallDamage } from './Collapse'

// Debris everywhere, not just piles: concrete chunks of every size on every floor, glass
// under the blown-out windows, paper, fallen ceiling tiles, crushed and overturned furniture,
// heaved floor plates with cracks around them and dust along the walls; plus photo-scanned
// CC0 rocks, barriers, tyres and office furniture (Poly Haven) as instanced glTF meshes.
// Visual only and Reality only: the truth grid, radio and robots never see any of it. Inside
// the rooms everything is either low enough to drive over (<= 0.12 m), hugging a wall (its
// centre <= 0.6 m from the wall line) or inside a rubble/hazard polygon the robots never
// enter; door openings stay clear. Deterministic from the floorplan, nothing hardcoded.

function rng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}

const box = (poly) => {
  const xs = poly.map((p) => p[0])
  const ys = poly.map((p) => p[1])
  return [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
}

const THICK = { concrete: 0.3, brick: 0.2, drywall: 0.12, metal: 0.06 }
const TILE_M = 2.5 // one floor texture tile = 2.5 m (Building.jsx Slab repeats W / 2.5)

// Shared scratch matrix from position, Euler rotation (optional order as 4th entry) and scale.
// Callers that keep the result clone it.
const _m = new THREE.Matrix4()
const _t = new THREE.Matrix4()
const _q = new THREE.Quaternion()
const _e = new THREE.Euler()
const _p = new THREE.Vector3()
const _s = new THREE.Vector3()
function M(pos, rot = [0, 0, 0], scale = [1, 1, 1]) {
  _q.setFromEuler(_e.set(rot[0], rot[1], rot[2], rot[3] ?? 'XYZ'))
  return _m.compose(_p.set(pos[0], pos[1], pos[2]), _q, _s.set(scale[0], scale[1], scale[2]))
}

// --------------------------------------------------------------- templates
// Every template is non-indexed with position/normal/uv so copies merge into one geometry.
const nonIdx = (g) => (g.index ? g.toNonIndexed() : g)
const BOX = nonIdx(new THREE.BoxGeometry(1, 1, 1))
const CYL = nonIdx(new THREE.CylinderGeometry(1, 1, 1, 8))
const FLAT = nonIdx(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2)) // unit square on the floor

// Flat glass shard from a few points on the floor plane (a fan of triangles).
function shard(pts) {
  const tri = []
  for (let i = 1; i < pts.length - 1; i++) tri.push(pts[0], pts[i], pts[i + 1])
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(tri.flatMap(([x, z]) => [x, 0, z]), 3))
  g.setAttribute('normal', new THREE.Float32BufferAttribute(tri.flatMap(() => [0, 1, 0]), 3))
  g.setAttribute('uv', new THREE.Float32BufferAttribute(tri.flatMap(([x, z]) => [x, z]), 2))
  return g
}
const SHARDS = [
  shard([[0, 0], [1, 0], [0.35, 0.8]]),
  shard([[0, 0], [1, 0.2], [0.15, 0.9]]),
  shard([[0, 0], [1, 0], [0.9, 0.6], [0.1, 0.7]]),
  shard([[0, 0], [1, 0.05], [1, 0.3], [0.05, 0.2]]),
]

// Fallen ceiling tile: a 60 cm square with a corner knocked off (or half a tile with a torn
// edge), 15 mm thick, lying flat. Caps off-white, cut edges grey, through vertex colors.
function tileGeom(pts) {
  const g = new THREE.ExtrudeGeometry(new THREE.Shape(pts.map(([x, y]) => new THREE.Vector2(x, y))), { depth: 0.015, bevelEnabled: false })
  const n = g.attributes.position.count
  const col = new Float32Array(n * 3)
  const caps = g.groups[0]
  for (let i = 0; i < n; i++) col.set(i >= caps.start && i < caps.start + caps.count ? [0.86, 0.84, 0.78] : [0.55, 0.54, 0.5], i * 3)
  g.setAttribute('color', new THREE.BufferAttribute(col, 3))
  g.translate(-0.3, -0.3, -0.0075)
  g.rotateX(-Math.PI / 2)
  return g
}
const TILES = [
  tileGeom([[0, 0], [0.6, 0], [0.6, 0.48], [0.46, 0.5], [0.44, 0.6], [0, 0.6]]),
  tileGeom([[0, 0], [0.6, 0], [0.6, 0.6], [0.22, 0.6], [0.2, 0.44], [0.06, 0.42], [0, 0.3]]),
  tileGeom([[0, 0], [0.6, 0], [0.58, 0.14], [0.47, 0.2], [0.4, 0.3], [0.26, 0.26], [0.14, 0.33], [0, 0.28]]),
]

// Low-poly chunk for the thousands of small pieces (8 or 20 faces, pushed in and out like
// chunks() does); the medium pieces use the 5 chunks() geometries from Debris.jsx.
function lowChunk(base, seed) {
  const g = nonIdx(base)
  const r = rng(seed)
  const pos = g.attributes.position
  const moved = new Map() // shared corners move together or the mesh tears
  for (let i = 0; i < pos.count; i++) {
    const key = `${pos.getX(i).toFixed(3)},${pos.getY(i).toFixed(3)},${pos.getZ(i).toFixed(3)}`
    if (!moved.has(key)) moved.set(key, 0.65 + r() * 0.6)
    const f = moved.get(key)
    pos.setXYZ(i, pos.getX(i) * f, pos.getY(i) * f * 0.7, pos.getZ(i) * f)
  }
  g.computeVertexNormals()
  return g
}
const GRIT = lowChunk(new THREE.OctahedronGeometry(1, 0), 901)
const SMALL = [lowChunk(new THREE.IcosahedronGeometry(1, 0), 907), lowChunk(new THREE.IcosahedronGeometry(1, 0), 911)]

let shared = null
function mats() {
  if (shared) return shared
  const t = materials()
  shared = {
    chunk: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 0.6, 0.6), color: '#c9c3b9', roughness: 0.95, flatShading: true }),
    glass: new THREE.MeshStandardMaterial({ color: '#cfe3ea', metalness: 0.9, roughness: 0.05, transparent: true, opacity: 0.65, envMapIntensity: 1.5, side: THREE.DoubleSide, depthWrite: false }),
    // paper, paint and tiles are tinted per instance (tiles also carry cap/edge vertex colors)
    paper: new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.9, side: THREE.DoubleSide }),
    tile: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95 }),
    paint: new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.7, metalness: 0.15 }),
    metal: new THREE.MeshStandardMaterial({ color: '#2b2e33', metalness: 0.7, roughness: 0.45 }),
    plate: new THREE.MeshStandardMaterial({ ...tiledSet(t.floor, 1, 1), color: '#d9d8d4', roughness: 0.9, normalScale: new THREE.Vector2(0.9, 0.9) }),
    crack: new THREE.MeshStandardMaterial({ map: t.cracks, transparent: true, depthWrite: false, roughness: 1, polygonOffset: true, polygonOffsetFactor: -2 }),
    dust: new THREE.MeshStandardMaterial({ map: t.dust, transparent: true, depthWrite: false, roughness: 1, color: '#b8ab98' }),
  }
  return shared
}

// --------------------------------------------------------------- floorplan queries
function context(fp) {
  const [W, H] = fp.size
  const doors = (fp.doors ?? []).map((d) => ({ x: d.at[0], y: d.at[1], r: Math.max(1.0, d.width * 0.75) }))
  const rubble = (fp.rubble ?? []).map((rb) => box(rb.poly))
  const hazards = (fp.hazards ?? []).map((hz) => box(hz.poly))
  // `i` is the fp.walls index, which wallDamage() is keyed by
  const walls = fp.walls.map((w, i) => ({ w, i })).filter(({ w }) => Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]) > 0.01).map(({ w, i }) => {
    const [ax, ay] = w.a
    const [bx, by] = w.b
    const len = Math.hypot(bx - ax, by - ay)
    const ux = (bx - ax) / len
    const uy = (by - ay) / len
    return { i, ax, ay, bx, by, len, ux, uy, nx: -uy, ny: ux, half: (THICK[w.material] ?? 0.2) / 2, material: w.material,
      outer: (ax === bx && (ax === 0 || ax === W)) || (ay === by && (ay === 0 || ay === H)) }
  })
  const inB = (x, y, b, pad = 0) => x > b[0] + pad && x < b[1] - pad && y > b[2] + pad && y < b[3] - pad
  const rooms = (fp.rooms ?? []).map((room) => ({ room, b: box(room.poly) }))
  // a room drawn inside another (the cage inside the warehouse) is skipped when the outer
  // room is sampled, so that floor is not littered twice
  const area = (b) => (b[1] - b[0]) * (b[3] - b[2])
  for (const r of rooms) r.inner = rooms.filter((o) => o !== r && area(o.b) < area(r.b) && o.b[0] >= r.b[0] && o.b[1] <= r.b[1] && o.b[2] >= r.b[2] && o.b[3] <= r.b[3])
  return {
    W, H, doors, rubble, hazards, walls, rooms, inB, area,
    nearDoor: (x, y, extra = 0) => doors.some((d) => Math.hypot(x - d.x, y - d.y) < d.r + extra),
    onRubble: (x, y, pad = 0) => rubble.some((b) => inB(x, y, b, -pad)),
    inside: (x, y) => x > 0 && x < W && y > 0 && y < H,
    // the wall segment under (x, y) that also covers halfLen either side of it, or null
    wallAt: (x, y, halfLen = 0) => walls.find((w) => {
      const t = (x - w.ax) * w.ux + (y - w.ay) * w.uy
      return Math.abs((x - w.ax) * w.nx + (y - w.ay) * w.ny) < 0.05 && t >= halfLen && t <= w.len - halfLen
    }) ?? null,
  }
}

// Random spot on a room's open floor, off the doors, the rubble piles and any nested room;
// `pad` keeps away from the walls. Null after a few misses (keeps the rng sequence bounded).
function spot(room, C, r, pad = 0.3, tries = 6) {
  const [x0, x1, y0, y1] = room.b
  if (x1 - x0 < 2 * pad + 0.2 || y1 - y0 < 2 * pad + 0.2) return null
  for (let k = 0; k < tries; k++) {
    const x = x0 + pad + r() * (x1 - x0 - 2 * pad)
    const y = y0 + pad + r() * (y1 - y0 - 2 * pad)
    if (C.nearDoor(x, y) || C.onRubble(x, y) || room.inner.some((o) => C.inB(x, y, o.b))) continue
    return [x, y]
  }
  return null
}

// Spot `out` metres in from a random edge of the room (paper drifts to the walls).
function edgeSpot(room, C, r, out) {
  const [x0, x1, y0, y1] = room.b
  const e = Math.floor(r() * 4)
  const t = r()
  const x = e % 2 === 0 ? x0 + 0.3 + t * (x1 - x0 - 0.6) : e === 1 ? x1 - out : x0 + out
  const y = e % 2 === 1 ? y0 + 0.3 + t * (y1 - y0 - 0.6) : e === 2 ? y1 - out : y0 + out
  if (C.nearDoor(x, y) || C.onRubble(x, y) || room.inner.some((o) => C.inB(x, y, o.b))) return null
  return [x, y]
}

// Spot in the band hugging a wall face (either side, inside the building, off the doors),
// at most `maxOut` from the wall's centre line.
function wallSpot(w, C, r, maxOut = 0.5, margin = 0.3) {
  if (w.len < 2 * margin + 0.1) return null
  const t = margin + r() * (w.len - 2 * margin)
  const side = r() < 0.5 ? -1 : 1
  const out = w.half + 0.03 + r() ** 1.4 * Math.max(0.02, maxOut - w.half - 0.03)
  const x = w.ax + w.ux * t + w.nx * side * out
  const y = w.ay + w.uy * t + w.ny * side * out
  if (!C.inside(x, y) || C.nearDoor(x, y)) return null
  return { x, y, side, t }
}

// Concrete grey, the odd brick-red or plaster-white piece.
function chunkTint(r) {
  const k = r()
  const v = 0.6 + r() * 0.4
  if (k < 0.08) return [v, v * 0.74, v * 0.62]
  if (k < 0.2) return [1.05, 1.04, 1.0]
  return [v, v * 0.99, v * 0.97]
}

// A chunk `size` m across at (x, y). `low` keeps it flat (top <= 0.12 m: drive-over litter).
function chunk(x, y, size, r, low) {
  const sx = (size / 2) * (0.75 + r() * 0.5)
  const sz = (size / 2) * (0.75 + r() * 0.5)
  const sy = low ? Math.min((size / 2) * (0.45 + r() * 0.4), 0.05) : (size / 2) * (0.6 + r() * 0.5)
  const rot = low ? [(r() - 0.5) * 0.4, r() * 6.3, (r() - 0.5) * 0.4] : [r() * 6.3, r() * 6.3, r() * 6.3]
  return { pos: w2t(x, y, sy * 0.5), rot, scale: [sx, sy, sz], tint: chunkTint(r) }
}

// Placed copy of a template in a parent frame (furniture parts).
function P(list, frame, geom, pos, rot, scale, color) {
  list.push({ geom, m: new THREE.Matrix4().multiplyMatrices(frame, M(pos, rot || [0, 0, 0], scale)), color })
}

// --------------------------------------------------------------- furniture
// Built in a slot frame: origin on the wall face, x along the wall, z into the room.
// Dusty grey paints via instance colors (one material), dark metal parts in another.

// Desk flipped onto its top, legs up, monitor face down beside it.
function desk(S, r, L) {
  const paint = [0.72, 0.7, 0.66].map((c) => c * (0.85 + r() * 0.2))
  const z = 0.04 + 0.3
  P(L.paint, S, BOX, [0, 0.02, z], 0, [1.3, 0.04, 0.6], paint)
  for (const x of [-0.61, 0.61]) P(L.metal, S, BOX, [x, 0.4, z], 0, [0.05, 0.72, 0.54])
  P(L.metal, S, BOX, [0, 0.26, z - 0.26], 0, [1.2, 0.35, 0.02])
  P(L.metal, S, BOX, [0.9, 0.015, 0.45], [0, 0.4, 0], [0.5, 0.03, 0.3])
  P(L.metal, S, BOX, [-0.9, 0.01, 0.3], [0, -0.3, 0], [0.42, 0.02, 0.14])
}

// Office chair on its side, star base toward the room.
function chair(S, r, L) {
  const Q = new THREE.Matrix4().multiplyMatrices(S, M([-0.5 + (r() - 0.5) * 0.2, 0.27, 0.28], [0, 0, -Math.PI / 2]))
  const fabric = [0.33, 0.36, 0.42].map((c) => c * (0.8 + r() * 0.3))
  P(L.paint, Q, BOX, [0, 0.48, 0], 0, [0.48, 0.08, 0.46], fabric)
  P(L.paint, Q, BOX, [0, 0.8, 0.16], [0.12, 0, 0], [0.46, 0.5, 0.07], fabric)
  P(L.metal, Q, CYL, [0, 0.28, 0], 0, [0.025, 0.36, 0.025])
  for (let i = 0; i < 5; i++) {
    const a = (i * Math.PI * 2) / 5
    P(L.metal, Q, BOX, [Math.cos(a) * 0.15, 0.07, -Math.sin(a) * 0.15], [0, a, 0], [0.3, 0.03, 0.04])
  }
}

// Filing cabinet crushed from above: the top sections buckled into a wedge, a drawer sprung.
function cabinet(S, r, L) {
  const grey = [0.49, 0.5, 0.54].map((c) => c * (0.85 + r() * 0.25))
  const z = 0.04 + 0.22
  P(L.paint, S, BOX, [0, 0.31, z], 0, [0.46, 0.62, 0.44], grey)
  P(L.paint, S, BOX, [0.03, 0.74, z], [0, 0, 0.12], [0.46, 0.22, 0.44], grey)
  P(L.paint, S, BOX, [-0.04, 0.92, z + 0.02], [0, 0, -0.22], [0.47, 0.16, 0.42], grey)
  P(L.paint, S, BOX, [0.02, 1.03, z], [0, 0, 0.32], [0.48, 0.08, 0.44], grey)
  P(L.paint, S, BOX, [0, 0.45, z + 0.14], [0.05, 0, 0], [0.4, 0.16, 0.4], grey)
  for (const y of [0.2, 0.45]) P(L.metal, S, BOX, [0, y, z + 0.23], 0, [0.2, 0.03, 0.02])
}

// Shelf unit (1.2 x 1.8 x 0.32) toppled onto its side along the wall, contents spilled low.
function shelf(S, r, L) {
  const wood = [0.45, 0.38, 0.31].map((c) => c * (0.85 + r() * 0.25))
  const Q = new THREE.Matrix4().multiplyMatrices(S, M([0.9, 0.6, 0.2], [0, 0, Math.PI / 2]))
  P(L.paint, Q, BOX, [0, 0.9, -0.14], 0, [1.2, 1.8, 0.04], wood)
  for (const x of [-0.6, 0.6]) P(L.paint, Q, BOX, [x, 0.9, 0], 0, [0.03, 1.8, 0.32], wood)
  for (const y of [0.02, 0.6, 1.2, 1.78]) P(L.paint, Q, BOX, [0, y, 0], 0, [1.2, 0.03, 0.32], wood)
  for (let i = 0; i < 6; i++) {
    P(L.paint, S, BOX, [(r() - 0.5) * 2.0, 0.025 + (i % 2) * 0.03, 0.42 + r() * 0.35], [0, r() * 6.3, 0],
      [0.22 + r() * 0.1, 0.05, 0.3], i % 2 ? [0.55, 0.42, 0.28] : [0.3, 0.33, 0.4])
  }
}
const BUILD = { desk, chair, cabinet, shelf }
// the gltf kinds are filled by ScannedDebris from the same slot list, so they never overlap
const KINDS = ['desk', 'chair', 'cabinet', 'shelf', 'gltfDesk', 'gltfChair']

// Slot frame on a wall: origin on the face, x along the wall, z into the room.
function slotFrame(w, x, y, side, jitter = 0) {
  const ang = Math.atan2(w.uy, w.ux) + (side > 0 ? Math.PI : 0) + jitter
  return M(w2t(x + w.nx * side * w.half, y + w.ny * side * w.half, 0), [0, ang, 0]).clone()
}

// Furniture slots along a room's edges: on a real (non-fence) wall, 1 m clear of doors
// with room for the piece, off the rubble, spaced apart.
function slots(room, C, r, want) {
  const [x0, x1, y0, y1] = room.b
  const edges = [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]]
  const out = []
  for (let k = 0; k < want * 8 && out.length < want; k++) {
    const e = edges[Math.floor(r() * 4)]
    const len = Math.hypot(e[2] - e[0], e[3] - e[1])
    if (len < 3.4) continue
    const t = 1.2 + r() * (len - 2.4)
    const x = e[0] + ((e[2] - e[0]) / len) * t
    const y = e[1] + ((e[3] - e[1]) / len) * t
    const w = C.wallAt(x, y, 1.0)
    if (!w || w.material === 'metal' || C.nearDoor(x, y, 1.8) || C.onRubble(x, y, 1.2)) continue
    if (out.some((o) => Math.hypot(o.x - x, o.y - y) < 2.8)) continue
    const side = Math.sign(((x0 + x1) / 2 - x) * w.nx + ((y0 + y1) / 2 - y) * w.ny) || 1
    if (room.inner.some((o) => C.inB(x + w.nx * side * 0.6, y + w.ny * side * 0.6, o.b))) continue
    out.push({ x, y, w, side })
  }
  return out
}

// --------------------------------------------------------------- layout
// Everything placed, computed once per floorplan and shared by both components (the
// furniture slots decide which pieces are procedural and which are scanned models).
const layouts = new WeakMap()
export function litterLayout(fp) {
  if (!layouts.has(fp)) layouts.set(fp, layout(fp))
  return layouts.get(fp)
}

// Distance from (x, y) to the segment a-b (the command post's approach to the entry).
function segDist(x, y, a, b) {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / ((dx * dx + dy * dy) || 1)))
  return Math.hypot(x - a[0] - dx * t, y - a[1] - dy * t)
}

function layout(fp) {
  const C = context(fp)
  const { W, H } = C
  const r = rng(3301)
  const L = {
    grit: [], small: [[], []], medium: [[], [], [], [], []], glass: [[], [], [], []], paper: [],
    tiles: [[], [], []], paint: [], metal: [], plates: [], cracks: [], dust: [], furniture: [],
    rocks: [[], [], [], []], barriers: [], tyres: [],
  }
  const put = (list, pos, rot, scale, color) => list.push({ m: M(pos, rot, scale).clone(), color })
  const putChunk = (list, c) => put(list, c.pos, c.rot, c.scale, c.tint)
  const pick = (lists) => lists[Math.floor(r() * lists.length)]
  const yawOf = (w) => Math.atan2(w.uy, w.ux)
  const shade = (lo, hi) => { const v = lo + r() * (hi - lo); return [v, v, v] }
  // scanned model placement: world (x, z) or a slot frame with local offsets, yaw, a small
  // tilt and a size factor (ScannedDebris scales each model so f = 1 is its largest size)
  const rock = (x, y, h, f, tilt = 0.3) => pick(L.rocks).push({ x, z: -y, h, yaw: r() * 6.3, tx: (r() - 0.5) * tilt, tz: (r() - 0.5) * tilt, f })

  // ---- rooms: chunks, paper, ceiling tiles, furniture, heaved floor plates
  for (const room of C.rooms) {
    const [x0, x1, y0, y1] = room.b
    const area = C.area(room.b) - room.inner.reduce((a, o) => a + C.area(o.b), 0)
    // grit and small flat pieces across the whole floor (drive-over)
    for (let i = 0; i < area * 4; i++) {
      const p = spot(room, C, r, 0.15, 2)
      if (p) putChunk(L.grit, chunk(p[0], p[1], 0.03 + r() * 0.05, r, true))
    }
    for (let i = 0; i < area * 1.5; i++) {
      const p = spot(room, C, r, 0.15, 2)
      if (p) putChunk(pick(L.small), chunk(p[0], p[1], 0.08 + r() * 0.04, r, true))
    }
    // medium pieces in the open stay flat; the full-size ones come with the walls below
    for (let i = 0; i < area * 0.25; i++) {
      const p = spot(room, C, r, 0.3, 3)
      if (p) putChunk(pick(L.medium), chunk(p[0], p[1], 0.12 + r() * 0.23, r, true))
    }
    // paper: most of it drifted to the walls, a few manila folders
    const sheets = 10 + Math.floor(r() * 21)
    for (let i = 0; i < sheets + 2 + Math.floor(r() * 3); i++) {
      const folder = i >= sheets
      const p = r() < 0.6 ? edgeSpot(room, C, r, 0.25 + r() ** 2 * 1.2) : spot(room, C, r, 0.3, 3)
      if (!p) continue
      const crumpled = !folder && r() < 0.2
      const v = 0.85 + r() * 0.15
      put(L.paper, w2t(p[0], p[1], 0.012 + r() * 0.012), [(r() - 0.5) * 0.08, r() * 6.3, (r() - 0.5) * 0.08],
        folder ? [0.24, 1, 0.32] : crumpled ? [0.12, 1, 0.14] : [0.21, 1, 0.3],
        folder ? [0.82 * v, 0.68 * v, 0.42 * v] : [0.93 * v, 0.92 * v, 0.88 * v])
    }
    // ceiling tiles: flat on the floor, or leaning against a wall
    for (let i = 0, n = 3 + Math.floor(r() * 8); i < n; i++) {
      const geom = pick(L.tiles)
      if (r() < 0.3) {
        const e = Math.floor(r() * 4)
        const t = r()
        const x = e % 2 === 0 ? x0 + 0.5 + t * (x1 - x0 - 1) : e === 1 ? x1 : x0
        const y = e % 2 === 1 ? y0 + 0.5 + t * (y1 - y0 - 1) : e === 2 ? y1 : y0
        const w = C.wallAt(x, y, 0.4)
        if (!w || w.material === 'metal' || C.nearDoor(x, y, 0.6) || C.onRubble(x, y, 0.6)) continue
        const side = Math.sign(((x0 + x1) / 2 - x) * w.nx + ((y0 + y1) / 2 - y) * w.ny) || 1
        if (room.inner.some((o) => C.inB(x + w.nx * side * 0.4, y + w.ny * side * 0.4, o.b))) continue
        const th = 1.0 + r() * 0.3 // angle from the floor: the top edge rests on the wall
        const S = slotFrame(w, x, y, side, (r() - 0.5) * 0.3)
        geom.push({ m: S.multiply(M([0, 0.3 * Math.sin(th), 0.3 * Math.cos(th) + 0.02], [th, 0, 0])), color: shade(0.8, 1) })
      } else {
        const p = spot(room, C, r, 0.4, 3)
        if (p) put(geom, w2t(p[0], p[1], 0.02), [(r() - 0.5) * 0.1, r() * 6.3, (r() - 0.5) * 0.1], [1, 1, 1], shade(0.8, 1))
      }
    }
    // furniture against the walls
    for (const s of slots(room, C, r, 1 + (r() < 0.45 ? 1 : 0))) {
      const kind = KINDS[Math.floor(r() * KINDS.length)]
      const frame = slotFrame(s.w, s.x, s.y, s.side, (r() - 0.5) * 0.25)
      L.furniture.push({ kind, frame, x: s.x, y: s.y })
      if (BUILD[kind]) BUILD[kind](frame, rng(Math.floor(r() * 1e6)), L)
      L.dust.push({ m: frame.clone().multiply(M([0, 0.006, 0.55], [0, 0, 0], [2.8 + r(), 1, 1.6])) })
    }
    // heaved floor plates with cracks and dust around them
    for (let i = 0, n = 2 + Math.floor(r() * 3); i < n; i++) {
      const p = spot(room, C, r, 1.3, 4)
      if (!p || C.nearDoor(p[0], p[1], 1.2) || L.plates.some((o) => Math.hypot(o.x - p[0], o.y - p[1]) < 2.4)) continue
      const pl = { x: p[0], y: p[1], len: 1 + r(), wid: 0.8 + r() * 0.7, rise: 0.05 + r() * 0.055, ang: r() * 6.3 }
      L.plates.push(pl)
      put(L.cracks, w2t(pl.x, pl.y, 0.011), [0, r() * 6.3, 0], [pl.len + 1.4, 1, pl.wid + 1.4])
      put(L.dust, w2t(pl.x, pl.y, 0.006), [0, pl.ang, 0], [pl.len + 1.2, 1, pl.wid + 1.2])
    }
  }

  // ---- walls: full-size chunks hugging them, dust along the bases, glass under the windows
  const dmg = wallDamage(fp)
  let glass = 0
  const dropGlass = (x, y, w, spread, n) => {
    for (let k = 0; k < n && glass < 900; k++) {
      const side = r() < 0.5 ? -1 : 1
      const out = w.half + 0.05 + r() ** 0.8 * 1.45
      const px = x + w.nx * side * out + w.ux * (r() - 0.5) * spread
      const py = y + w.ny * side * out + w.uy * (r() - 0.5) * spread
      if (C.nearDoor(px, py)) continue
      const s = 0.03 + r() ** 1.5 * 0.12
      put(pick(L.glass), w2t(px, py, 0.012 + r() * 0.004), [(r() - 0.5) * 0.04, r() * 6.3, (r() - 0.5) * 0.04], [s, 1, s * (0.6 + r() * 0.4)], shade(0.85, 1))
      glass++
    }
  }
  const outer = C.walls.filter((w) => w.outer)
  for (const w of C.walls) {
    if (w.material === 'metal') continue
    for (let k = 0, n = Math.round(w.len * 0.5); k < n; k++) {
      const s = wallSpot(w, C, r, 0.42)
      if (s) putChunk(pick(L.medium), chunk(s.x, s.y, 0.12 + r() * 0.23, r, false))
    }
    for (let k = 0, n = Math.round(w.len * 0.12); k < n; k++) {
      const s = wallSpot(w, C, r, 0.5, 0.5)
      if (s) rock(s.x, s.y, 0, 0.35 + r() * 0.35)
    }
    for (let t = 1.0; t < w.len - 1.0; t += 2.4 + r() * 1.2) {
      for (const side of [-1, 1]) {
        if (r() > 0.55) continue
        const x = w.ax + w.ux * t + w.nx * side * (w.half + 0.5)
        const y = w.ay + w.uy * t + w.ny * side * (w.half + 0.5)
        if (!C.inside(x, y) || C.nearDoor(x, y, 0.5)) continue
        put(L.dust, w2t(x, y, 0.006), [0, yawOf(w), 0], [1.8 + r() * 1.6, 1, 0.9 + r() * 0.6])
      }
    }
    if (!w.outer || !dmg[w.i]) continue
    const mx = (w.ax + w.bx) / 2
    const my = (w.ay + w.by) / 2
    for (const win of dmg[w.i].windows) dropGlass(mx + w.ux * win.x, my + w.uy * win.x, w, 1.6, 18 + Math.floor(r() * 12))
    for (const b of dmg[w.i].breaches) dropGlass(mx + w.ux * b.x, my + w.uy * b.x, w, 2.2, 10)
  }
  // a plan with few windows still gets a scatter of glass along its facade
  for (let k = 0; glass < 400 && k < 2000 && outer.length; k++) {
    const w = outer[Math.floor(r() * outer.length)]
    const t = 0.5 + r() * (w.len - 1)
    dropGlass(w.ax + w.ux * t, w.ay + w.uy * t, w, 1, 1)
  }

  // ---- rubble piles and hazard zones: the biggest pieces, scanned rocks among them
  C.rubble.forEach((b, k) => {
    const cx = (b[0] + b[1]) / 2
    const cy = (b[2] + b[3]) / 2
    const top = fp.rubble[k].height || 1
    for (let i = 0, n = 3 + Math.floor(r() * 3); i < n; i++) {
      const a = r() * Math.PI * 2
      const d = 0.55 + r() * 0.4 // on the mound's lower slopes, half buried
      rock(cx + Math.cos(a) * d * (b[1] - b[0]) / 2, cy + Math.sin(a) * d * (b[3] - b[2]) / 2, Math.max(0, (1 - d * d) * top * 0.45) - 0.06, 0.6 + r() * 0.4, 6)
    }
  })
  for (const b of C.hazards) {
    const n = Math.min(120, Math.round(C.area(b) * 0.5))
    for (let i = 0; i < n; i++) {
      putChunk(pick(L.medium), chunk(b[0] + 0.25 + r() * (b[1] - b[0] - 0.5), b[2] + 0.25 + r() * (b[3] - b[2] - 0.5), 0.1 + r() * 0.25, r, false))
    }
    for (let i = 0, m = Math.min(14, Math.round(C.area(b) * 0.08)); i < m; i++) {
      rock(b[0] + 0.4 + r() * (b[1] - b[0] - 0.8), b[2] + 0.4 + r() * (b[3] - b[2] - 0.8), 0, 0.5 + r() * 0.5)
    }
    for (let i = 0; i < 6; i++) {
      put(pick(L.tiles), w2t(b[0] + 0.4 + r() * (b[1] - b[0] - 0.8), b[2] + 0.4 + r() * (b[3] - b[2] - 0.8), 0.05 + r() * 0.2), [r() * 1.2 - 0.6, r() * 6.3, r() * 1.2 - 0.6], [1, 1, 1], shade(0.7, 0.95))
    }
  }

  // ---- outside: rocks thrown around the footprint, barriers and tyres on the lot, all
  // clear of the command post truck and the approach to the entry
  const cp = fp.command_post?.pos
  const entry = fp.entry ?? cp
  const clear = (x, y) => !cp || ((Math.abs(x - cp[0]) >= 7 || Math.abs(y - cp[1]) >= 7) && segDist(x, y, cp, entry) >= 2.5)
  const ring = (lo, hi) => {
    const e = Math.floor(r() * 4)
    const t = r()
    const off = lo + r() ** 1.3 * (hi - lo)
    return e === 0 ? [t * W, -off] : e === 1 ? [W + off, t * H] : e === 2 ? [t * W, H + off] : [-off, t * H]
  }
  for (let i = 0; i < 32; i++) {
    const [x, y] = ring(0.8, 8)
    if (clear(x, y)) rock(x, y, 0, 0.35 + r() * 0.65)
  }
  if (cp) {
    const dl = Math.hypot(cp[0] - entry[0], cp[1] - entry[1]) || 1
    const dx = (cp[0] - entry[0]) / dl // away from the building
    const dy = (cp[1] - entry[1]) / dl
    for (const off of [6.8, -4.6, -9.0]) {
      const x = cp[0] + dx * 4.6 - dy * off
      const y = cp[1] + dy * 4.6 + dx * off
      // long axis along the lot edge (the perpendicular to the approach)
      L.barriers.push({ x, z: -y, h: 0, yaw: Math.atan2(dx, -dy) + (r() - 0.5) * 0.2, f: 1 })
    }
  }
  for (let k = 0; k < 40 && L.tyres.length < 3; k++) {
    const [x, y] = ring(1.5, 6)
    if (!clear(x, y) || L.tyres.some((o) => Math.hypot(o.x - x, -o.z - y) < 4) || L.barriers.some((o) => Math.hypot(o.x - x, -o.z - y) < 3)) continue
    L.tyres.push({ x, z: -y, h: 0, yaw: r() * 6.3, tx: (r() - 0.5) * 0.1, tz: (r() - 0.5) * 0.1, f: 1 })
  }
  return L
}

// Heaved plates as one merged geometry: boxes pitched up at one edge, their UVs taken from
// world position so the slab's own texture runs straight across them.
function platesGeometry(plates) {
  if (!plates.length) return null
  const parts = plates.map((p) => {
    const g = new THREE.BoxGeometry(p.len, 0.06, p.wid)
    g.applyMatrix4(M(w2t(p.x, p.y, p.rise / 2 - 0.015), [Math.atan2(p.rise, p.wid), p.ang, 0, 'YXZ']))
    const pos = g.attributes.position
    const uv = g.attributes.uv
    for (let i = 0; i < pos.count; i++) uv.setXY(i, pos.getX(i) / TILE_M, -pos.getZ(i) / TILE_M)
    return g
  })
  return mergeGeometries(parts, false)
}

// One instanced mesh per (geometry, material) bucket: thousands of pieces, a few draw calls.
function Instances({ geom, material, items, shadow = false }) {
  const ref = useRef()
  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const c = new THREE.Color()
    items.forEach((it, i) => {
      mesh.setMatrixAt(i, it.m)
      if (it.color) mesh.setColorAt(i, c.setRGB(it.color[0], it.color[1], it.color[2]))
    })
    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    mesh.computeBoundingSphere() // instance-aware, so the mesh is not culled while in view
  }, [items])
  if (!items.length) return null
  return <instancedMesh ref={ref} args={[geom, material, items.length]} castShadow={shadow} receiveShadow />
}

const half = (arr) => arr.filter((_, i) => i % 2 === 0)

// Procedural litter. `perf` halves the loose chunks and glass (the bulk of the triangles).
export function LitterStatic({ fp, perf = false }) {
  const L = litterLayout(fp)
  const m = mats()
  const geoms = chunks()
  const S = useMemo(() => (perf
    ? { grit: half(L.grit), small: L.small.map(half), medium: L.medium.map(half), glass: L.glass.map(half) }
    : L), [L, perf])
  const [metalBox, metalCyl] = useMemo(() => [L.metal.filter((e) => e.geom === BOX), L.metal.filter((e) => e.geom === CYL)], [L])
  const plateGeom = useMemo(() => platesGeometry(L.plates), [L])
  return (
    <group>
      <Instances geom={GRIT} material={m.chunk} items={S.grit} />
      {S.small.map((items, k) => <Instances key={`s${k}`} geom={SMALL[k]} material={m.chunk} items={items} />)}
      {S.medium.map((items, k) => <Instances key={`m${k}`} geom={geoms[k]} material={m.chunk} items={items} shadow />)}
      {S.glass.map((items, k) => <Instances key={`g${k}`} geom={SHARDS[k]} material={m.glass} items={items} />)}
      <Instances geom={FLAT} material={m.paper} items={L.paper} />
      {L.tiles.map((items, k) => <Instances key={`t${k}`} geom={TILES[k]} material={m.tile} items={items} shadow />)}
      <Instances geom={BOX} material={m.paint} items={L.paint} shadow />
      <Instances geom={BOX} material={m.metal} items={metalBox} shadow />
      <Instances geom={CYL} material={m.metal} items={metalCyl} shadow />
      {plateGeom && <mesh geometry={plateGeom} material={m.plate} castShadow receiveShadow />}
      <Instances geom={FLAT} material={m.crack} items={L.cracks} />
      <Instances geom={FLAT} material={m.dust} items={L.dust} />
    </group>
  )
}

// --------------------------------------------------------------- scanned models
// Poly Haven CC0 scans under web/public/assets/models/<id>/<id>_1k.gltf. Each is reduced to
// one geometry (coarsest LOD, parts merged) and decimated once to a few hundred triangles,
// then drawn as a single InstancedMesh. A missing or broken file renders nothing.
const url = (id) => `/assets/models/${id}/${id}_1k.gltf`
const ROCKS = ['moon_rock_01', 'moon_rock_03', 'moon_rock_05', 'moon_rock_07']
const SPEC = {
  moon_rock_01: { tint: '#b9b4ab', tris: 800, fit: 0.6 },
  moon_rock_03: { tint: '#b9b4ab', tris: 800, fit: 0.6 },
  moon_rock_05: { tint: '#b9b4ab', tris: 800, fit: 0.6 },
  moon_rock_07: { tint: '#b9b4ab', tris: 800, fit: 0.6 },
  concrete_road_barrier_02: { tint: '#c4c0b8', tris: 2400 },
  metal_office_desk: { tint: '#bdb9b2', tris: 2400 },
  SchoolChair_01: { tint: '#c9c5bf', tris: 1500 },
  old_tyre: { tint: '#8a8a8a', tris: 1000 },
}
// how each model lies before its yaw: the desk on its back (top toward the room), the
// chair fallen along the wall, the tyre flat
const ROT = {
  desk: new THREE.Matrix4().makeRotationX(Math.PI / 2),
  chair: new THREE.Matrix4().makeRotationZ(Math.PI / 2),
  tyre: new THREE.Matrix4().makeRotationX(Math.PI / 2),
}

// Vertex clustering: snap every vertex to a grid, average each cell, drop the collapsed
// triangles. O(n) and blocky, for the big scans (edge collapse below is O(n^2)).
function cluster(geom, cell) {
  const pos = geom.attributes.position
  const uv = geom.attributes.uv
  const cells = new Map()
  const ids = new Uint32Array(pos.count)
  const sum = []
  const firstUv = []
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i)
    const y = pos.getY(i)
    const z = pos.getZ(i)
    const key = `${Math.round(x / cell)},${Math.round(y / cell)},${Math.round(z / cell)}`
    let id = cells.get(key)
    if (id === undefined) {
      id = sum.length
      cells.set(key, id)
      sum.push([0, 0, 0, 0])
      if (uv) firstUv.push(uv.getX(i), uv.getY(i))
    }
    const s = sum[id]
    s[0] += x; s[1] += y; s[2] += z; s[3]++
    ids[i] = id
  }
  const index = []
  for (let i = 0; i < pos.count; i += 3) {
    const a = ids[i]; const b = ids[i + 1]; const c = ids[i + 2]
    if (a !== b && b !== c && a !== c) index.push(a, b, c)
  }
  const out = new THREE.BufferGeometry()
  out.setAttribute('position', new THREE.Float32BufferAttribute(sum.flatMap(([x, y, z, n]) => [x / n, y / n, z / n]), 3))
  if (uv) out.setAttribute('uv', new THREE.Float32BufferAttribute(firstUv, 2))
  out.setIndex(index)
  out.computeVertexNormals()
  return out
}

function decimate(geom, targetTris) {
  const tris = geom.attributes.position.count / 3
  if (tris <= targetTris * 1.25) return geom
  try {
    if (tris > 12000) {
      // cell size from the target: a closed surface has ~2 triangles per vertex
      geom.computeBoundingBox()
      const size = geom.boundingBox.getSize(_p)
      const area = 2 * (size.x * size.y + size.y * size.z + size.x * size.z)
      return cluster(geom, Math.sqrt(area / (targetTris * 0.5)))
    }
    const merged = mergeVertices(geom)
    const keep = Math.ceil(targetTris * 0.52)
    const n = merged.attributes.position.count
    if (n <= keep) return geom
    const out = new SimplifyModifier().modify(merged, n - keep)
    if (!out?.attributes?.position?.count || !out.attributes.uv) return geom
    out.computeVertexNormals()
    return out
  } catch (e) {
    return geom
  }
}

const prepared = new Map()
// Exported so the reduction can be checked outside the browser; the components use it.
export function prepareModel(id, scene) {
  if (prepared.has(id)) return prepared.get(id)
  scene.updateMatrixWorld(true)
  const meshes = []
  scene.traverse((o) => { if (o.isMesh && o.geometry?.attributes?.position) meshes.push(o) })
  // LOD chains (the rocks): keep only the coarsest level
  const lod = (o) => { const m = /LOD(\d+)/i.exec(o.name); return m ? +m[1] : -1 }
  const top = Math.max(...meshes.map(lod))
  const picked = top >= 0 ? meshes.filter((o) => lod(o) === top) : meshes
  const parts = picked.map((o) => {
    const g = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone()
    for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k)
    return g.applyMatrix4(o.matrixWorld)
  })
  const spec = SPEC[id] ?? { tint: '#ffffff', tris: 2000 }
  const geom = decimate((parts.length > 1 && mergeGeometries(parts, false)) || parts[0], spec.tris)
  geom.computeBoundingBox()
  const material = (Array.isArray(picked[0].material) ? picked[0].material[0] : picked[0].material).clone()
  material.color.set(spec.tint)
  const size = geom.boundingBox.getSize(new THREE.Vector3())
  const out = { geom, material, box: geom.boundingBox, unit: spec.fit ? spec.fit / Math.max(size.x, size.z) : 1 }
  prepared.set(id, out)
  return out
}

// Height of the model's lowest corner once rotated by `base`, so it sits on the floor.
function liftOf(box, base) {
  let min = Infinity
  for (let k = 0; k < 8; k++) {
    _p.set(k & 1 ? box.max.x : box.min.x, k & 2 ? box.max.y : box.min.y, k & 4 ? box.max.z : box.min.z)
    if (base) _p.applyMatrix4(base)
    min = Math.min(min, _p.y)
  }
  return -min
}

// Instance matrix: world (x, z) or a slot frame with local offsets, then yaw and tilt, the
// model's resting rotation and its scale.
function place(it, base, s, lift) {
  const out = it.frame ? _m.copy(it.frame) : _m.identity()
  out.multiply(_t.makeTranslation(it.x, it.h + lift * s, it.z))
  out.multiply(_t.makeRotationFromEuler(_e.set(it.tx || 0, it.yaw, it.tz || 0, 'YXZ')))
  if (base) out.multiply(base)
  return out.multiply(_t.makeScale(s, s, s)).clone()
}

function Scanned({ id, items, base = null, shadow = true }) {
  const { scene } = useGLTF(url(id), false, false)
  const P = useMemo(() => prepareModel(id, scene), [id, scene])
  const placed = useMemo(() => {
    const lift = liftOf(P.box, base)
    return items.map((it) => ({ m: place(it, base, P.unit * (it.f ?? 1), lift) }))
  }, [items, P, base])
  return <Instances geom={P.geom} material={P.material} items={placed} shadow={shadow} />
}

// A model that fails to load (file not there yet, bad path) just disappears.
class Quiet extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(err) { console.warn('[litter] scanned model skipped:', err?.message ?? err) }
  render() { return this.state.failed ? null : this.props.children }
}

function Model(props) {
  if (!props.items.length) return null
  return (
    <Quiet>
      <Suspense fallback={null}>
        <Scanned {...props} />
      </Suspense>
    </Quiet>
  )
}

// Scanned debris. `outside` drops the lot pieces (the robot camera's indoor copy); `perf`
// skips the barriers and halves the rocks.
export function ScannedDebris({ fp, perf = false, outside = true }) {
  const L = litterLayout(fp)
  const [W, H] = fp.size
  const S = useMemo(() => {
    const inside = (it) => it.x > 0 && it.x < W && -it.z > 0 && -it.z < H
    const rocks = L.rocks.map((items) => (perf ? half(items) : items).filter((it) => outside || inside(it)))
    const slot = (kind, z) => L.furniture.filter((f) => f.kind === kind).map((f) => ({ frame: f.frame, x: 0, z, h: 0, yaw: 0, f: 1 }))
    return { rocks, desks: slot('gltfDesk', 0.03), chairs: slot('gltfChair', 0.4), barriers: outside && !perf ? L.barriers : [], tyres: outside ? L.tyres : [] }
  }, [L, perf, outside, W, H])
  return (
    <group>
      {ROCKS.map((id, k) => <Model key={id} id={id} items={S.rocks[k]} />)}
      <Model id="metal_office_desk" items={S.desks} base={ROT.desk} />
      <Model id="SchoolChair_01" items={S.chairs} base={ROT.chair} />
      <Model id="concrete_road_barrier_02" items={S.barriers} />
      <Model id="old_tyre" items={S.tyres} base={ROT.tyre} />
    </group>
  )
}
