import { useLayoutEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { WALL_H, w2t } from './util'
import { materials, tiledSet } from './textures'

// The ceiling came down. Everything here hangs off the wall tops (the roof itself is cut
// away so the camera can look in): pancaked slabs leaning along a wall with their broken
// edge down on the floor, I-beams snapped in the middle folding into a V, T-bar grid
// fragments still holding a tile or two, a duct run torn open with one section hanging,
// and cables and conduit dangling. All of it is derived from the floorplan with a seeded
// rng, so every client agrees and a generated map gets it too. Visual only, Reality panes
// only: the truth grid, the radio model and the robots never see any of it, so nothing
// here may sit where a path goes: slabs and grids hug a wall (<= 25 % of a room, never
// its middle, clear of the doors), beams and ducts stay above 1.6 m, cables end >= 0.6 m
// up. Hazard rooms are no-go for robots, so they get the worst of it. Even-index rooms
// already carry Collapse.jsx beams, so the snapped ones go across the odd rooms.

function rng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}
const hash = (...xs) => xs.reduce((h, x) => (h * 31 + Math.round(x * 100)) % 1000003, 7)
const shuffle = (xs, rr) => {
  const a = xs.slice()
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rr() * (i + 1)); [a[i], a[j]] = [a[j], a[i]] }
  return a
}

const box = (poly) => {
  const xs = poly.map((p) => p[0])
  const ys = poly.map((p) => p[1])
  return [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
}
const overlaps = (a, b) => a[0] < b[1] && a[1] > b[0] && a[2] < b[3] && a[3] > b[2]
const grow = ([x0, x1, y0, y1], p) => [x0 - p, x1 + p, y0 - p, y1 + p]
const contains = (a, b) => b[0] >= a[0] && b[1] <= a[1] && b[2] >= a[2] && b[3] <= a[3]
const distToRect = (x, y, r) => Math.hypot(Math.max(r[0] - x, 0, x - r[1]), Math.max(r[2] - y, 0, y - r[3]))
const area = (r) => Math.max(0, r[1] - r[0]) * Math.max(0, r[3] - r[2])
const overlapArea = (a, b) => area([Math.max(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.min(a[3], b[3])])

// --------------------------------------------------------------- where things may go
// The four sides of a room: `axis` is the coordinate that runs along the wall, `fixed` the
// other one, `inward` the sign toward the room's inside.
function edges([x0, x1, y0, y1]) {
  return [
    { axis: 'x', fixed: y0, lo: x0, hi: x1, inward: 1 },
    { axis: 'x', fixed: y1, lo: x0, hi: x1, inward: -1 },
    { axis: 'y', fixed: x0, lo: y0, hi: y1, inward: 1 },
    { axis: 'y', fixed: x1, lo: y0, hi: y1, inward: -1 },
  ]
}
// Sim point `t` along an edge, `d` meters into the room from the wall line.
const onEdge = (e, t, d) => (e.axis === 'x' ? [t, e.fixed + d * e.inward] : [e.fixed + d * e.inward, t])
// Footprint of a strip along the edge: t in [t0, t1], reaching `d` into the room.
function strip(e, t0, t1, d) {
  const a = onEdge(e, t0, 0)
  const b = onEdge(e, t1, d)
  return [Math.min(a[0], b[0]), Math.max(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[1], b[1])]
}
// The wall segment covering [t0, t1] of this edge, or null where the edge is open (the
// warehouse's side onto the corridor) or made of several pieces.
function wallOn(walls, e, t0, t1) {
  const near = (v) => Math.abs(v - e.fixed) < 0.05
  return walls.find((w) => {
    const [p, q] = e.axis === 'x' ? [[w.a[1], w.b[1]], [w.a[0], w.b[0]]] : [[w.a[0], w.b[0]], [w.a[1], w.b[1]]]
    return near(p[0]) && near(p[1]) && Math.min(...q) <= t0 + 0.05 && Math.max(...q) >= t1 - 0.05
  }) ?? null
}
const solidOn = (walls, e, t0, t1) => {
  const w = wallOn(walls, e, t0, t1)
  return w && w.material !== 'metal' ? w : null
}
const doorOn = (doors, e) => doors.some(([x, y]) => (e.axis === 'x'
  ? Math.abs(y - e.fixed) < 0.3 && x > e.lo && x < e.hi
  : Math.abs(x - e.fixed) < 0.3 && y > e.lo && y < e.hi))

// Everything a placement must keep clear of, computed once per floorplan.
function site(fp) {
  const rooms = (fp.rooms ?? []).map((room, i) => ({ room, i, rect: box(room.poly) }))
  const hazards = (fp.hazards ?? []).map((h) => box(h.poly))
  // Collapse.jsx keeps a piece of roof over the southern 40 % of each hazard zone (grown
  // 0.3 m), its broken edge wandering up to 15 % past that
  const roofs = hazards.map(([x0, x1, y0, y1]) => {
    const reach = (y1 - y0 + 0.6) * 0.4
    return [x0 - 0.3, x1 + 0.3, y0 - 0.3, y0 - 0.3 + reach * 1.2 + 0.1]
  })
  for (const r of rooms) {
    r.area = area(r.rect)
    r.short = Math.min(r.rect[1] - r.rect[0], r.rect[3] - r.rect[2])
    r.hazard = hazards.some((h) => overlapArea(h, r.rect) > r.area * 0.5)
    r.inner = rooms.filter((o) => o !== r && contains(r.rect, o.rect)).map((o) => o.rect) // the cage inside the warehouse
    r.taken = []
    r.budget = r.area * 0.25 // rule: at most a quarter of a room hidden from above
  }
  return { rooms, roofs, doors: (fp.doors ?? []).map((d) => d.at), entry: fp.entry ?? null, walls: fp.walls ?? [] }
}

// Can a thing with footprint `f` go in room `r`? Nothing stacks on something already
// placed, nothing goes under the surviving roof piece or into a nested room, and things
// that reach the floor keep `doorGap` from every door and well clear of the entry.
function fits(S, r, f, doorGap) {
  if (!contains(grow(r.rect, 0.05), f)) return false
  if (area(f) > r.budget) return false
  if (r.inner.some((o) => overlaps(o, f))) return false
  if (S.roofs.some((o) => overlaps(o, f))) return false
  if (r.taken.some((o) => overlaps(grow(o, 0.3), f))) return false
  if (doorGap && S.doors.some(([x, y]) => distToRect(x, y, f) < doorGap)) return false
  if (doorGap && S.entry && distToRect(S.entry[0], S.entry[1], f) < 2) return false
  return true
}

// Try a few spots along the room's walls for a strip `a` long (along the wall) reaching
// `d` into the room; walls with doors in them are tried last. Returns where it went.
function place(S, r, rr, a, d, doorGap, tries = 16) {
  const es = edges(r.rect)
  const order = [...es.filter((e) => !doorOn(S.doors, e)), ...es.filter((e) => doorOn(S.doors, e))]
  for (let k = 0; k < tries; k++) {
    const e = order[Math.min(order.length - 1, Math.floor(rr() * rr() * order.length))]
    const len = e.hi - e.lo
    if (len < a + 1.2) continue
    const t0 = e.lo + 0.6 + rr() * (len - a - 1.2)
    if (!solidOn(S.walls, e, t0, t0 + a)) continue
    const f = strip(e, t0, t0 + a, d)
    if (!fits(S, r, f, doorGap)) continue
    r.taken.push(f)
    r.budget -= area(f)
    return { e, t0, t1: t0 + a }
  }
  return null
}

// Where a beam meets the walls. Collapse.jsx spans the even rooms the short way at a seed
// it derives from the room, so the same seed and first draw land us in the same place; the
// odd rooms get our snapped beams, kept off nested rooms and on solid wall at both ends.
function planBeam(S, r) {
  const [x0, x1, y0, y1] = r.rect
  const alongX = x1 - x0 < y1 - y0
  const es = edges(r.rect)
  const ends = alongX ? [es[2], es[3]] : [es[0], es[1]]
  const span = (t) => {
    const a = alongX ? [x0, y0 + (y1 - y0) * t] : [x0 + (x1 - x0) * t, y0]
    return { a, b: alongX ? [x1, a[1]] : [a[0], y1] }
  }
  const ok = ({ a, b }) => {
    const f = grow([Math.min(a[0], b[0]), Math.max(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[1], b[1])], 0.3)
    if (r.inner.some((o) => overlaps(o, f))) return false
    const t = alongX ? a[1] : a[0]
    return ends.every((e) => wallOn(S.walls, e, t - 0.2, t + 0.2))
  }
  const rr = rng(hash(x0, y0, x1, y1, 5))
  let t = 0.35 + rr() * 0.3
  if (r.i % 2 === 0) return { alongX, ...span(t), ours: false }
  for (let k = 0; k < 10; k++) {
    const s = span(t)
    if (ok(s)) return { alongX, ...s, ours: true }
    t = 0.3 + rr() * 0.4
  }
  return null
}

// --------------------------------------------------------------- geometry helpers
const V3 = (x, y, z) => new THREE.Vector3(x, y, z)
const UP = V3(0, 1, 0)
const X = V3(1, 0, 0)
const Q0 = new THREE.Quaternion()
const ONE = V3(1, 1, 1)
const at = (p, h) => V3(...w2t(p[0], p[1], h))
// Unit vectors along an edge and into its room, in three.js coordinates (sim y is -z).
const alongOf = (e) => (e.axis === 'x' ? V3(1, 0, 0) : V3(0, 0, -1))
const inwardOf = (e) => (e.axis === 'x' ? V3(0, 0, -e.inward) : V3(e.inward, 0, 0))
// Right-handed frame with x along `ex` and y along `ey` (unit, orthogonal), z kept pointing
// up-ish by flipping x when needed (everything laid out in it is symmetric along x).
function frame(o, ex, ey) {
  const ez = ex.clone().cross(ey)
  if (ez.y < 0) { ex = ex.clone().negate(); ez.negate() }
  return new THREE.Matrix4().makeBasis(ex, ey, ez).setPosition(o)
}
const compose = (p, q, s) => new THREE.Matrix4().compose(p, q, s)
// Quaternion turning +y into `dir` (cylinders) or +x into `dir` (beams).
const yTo = (dir) => new THREE.Quaternion().setFromUnitVectors(UP, dir.clone().normalize())
const xTo = (dir) => new THREE.Quaternion().setFromUnitVectors(X, dir.clone().normalize())
const roll = (a) => new THREE.Quaternion().setFromAxisAngle(X, a)
const merge = (gs) => {
  if (!gs.length) return null
  const g = mergeGeometries(gs, false)
  gs.forEach((x) => x.dispose())
  return g
}

const BOX = new THREE.BoxGeometry(1, 1, 1)
const CYL = new THREE.CylinderGeometry(1, 1, 1, 5)

// I-beam along x: web plus two flanges. Box UVs run 0..1 per face, so the long faces get
// theirs stretched back to meters for the rust map (verts 0-7 are the +-x ends).
function ibeam(len) {
  const parts = [
    new THREE.BoxGeometry(len, 0.22, 0.025),
    new THREE.BoxGeometry(len, 0.025, 0.14).translate(0, 0.11, 0),
    new THREE.BoxGeometry(len, 0.025, 0.14).translate(0, -0.11, 0),
  ]
  for (const b of parts) {
    const uv = b.attributes.uv
    for (let i = 8; i < uv.count; i++) uv.setX(i, uv.getX(i) * len)
  }
  return merge(parts)
}

// Rectangular duct: a box without its end faces, so a torn end shows the inside.
function openBox(len, h, w) {
  const g = new THREE.BoxGeometry(len, h, w).toNonIndexed()
  const out = new THREE.BufferGeometry()
  for (const k of ['position', 'normal', 'uv']) {
    const a = g.attributes[k]
    out.setAttribute(k, new THREE.BufferAttribute(a.array.slice(12 * a.itemSize), a.itemSize)) // first 4 tris are the +-x caps
  }
  g.dispose()
  return out
}

// Split a placed (non-indexed) geometry into the faces that look up and the ones that look
// down, so a slab's underside can take a darker material.
function splitUnder(g) {
  const n = g.attributes.normal
  const tris = [[], []]
  for (let t = 0; t < n.count; t += 3) tris[(n.getY(t) + n.getY(t + 1) + n.getY(t + 2)) < -1 ? 1 : 0].push(t)
  return tris.map((list) => {
    const out = new THREE.BufferGeometry()
    for (const k of ['position', 'normal', 'uv']) {
      const a = g.attributes[k]
      const arr = new Float32Array(list.length * 3 * a.itemSize)
      list.forEach((t, i) => {
        for (let v = 0; v < 3; v++) for (let c = 0; c < a.itemSize; c++) arr[(i * 3 + v) * a.itemSize + c] = a.array[(t + v) * a.itemSize + c]
      })
      out.setAttribute(k, new THREE.BufferAttribute(arr, a.itemSize))
    }
    return out
  })
}

// Outline of a broken slab in its own plane: u along the wall, v up the slope. The edge
// that stayed on the wall (v = L) is nearly straight; the fracture at the bottom and the
// sides wander, with the odd bite taken out. Nothing goes below v = 0: that line is the
// foot, and the foot's height is what keeps the slab off the floor.
function slabShape(a, L, rr) {
  const wob = (k) => (rr() - 0.5) * k
  const pts = []
  const n = Math.max(4, Math.round(a * 3))
  for (let i = 0; i <= n; i++) pts.push([-a / 2 + (i / n) * a + (i && i < n ? wob(0.12) : 0), rr() * 0.35 + (rr() < 0.15 ? 0.22 : 0)])
  const m = Math.max(3, Math.round(L * 2))
  for (let j = 1; j < m; j++) pts.push([a / 2 + wob(0.3), (j / m) * L + wob(0.1)])
  pts.push([a / 2 + wob(0.06), L], [-a / 2 + wob(0.06), L])
  for (let j = m - 1; j >= 1; j--) pts.push([-a / 2 + wob(0.3), (j / m) * L + wob(0.1)])
  const s = new THREE.Shape()
  pts.forEach(([x, y], i) => (i ? s.lineTo(x, y) : s.moveTo(x, y)))
  s.closePath()
  return s
}

// A cable or pipe along a quadratic curve (points in three.js coordinates).
const tube = (p0, p1, p2, radius) =>
  new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(p0, p1, p2), 10, radius, radius > 0.016 ? 7 : 5, false)

// A cable hanging from `a`, leaning out toward `lean`, its end 0.6-1.2 m off the floor.
function cable(a, lean, rr) {
  const e = V3(a.x, 0.6 + rr() * 0.6, a.z).addScaledVector(lean, 0.2 + rr() * 0.4)
  const c = a.clone().lerp(e, 0.4).addScaledVector(lean, 0.15 + rr() * 0.15)
  return { a, c, e, r: 0.008 + rr() * 0.007, f: 0.5 + rr() * 0.4, phase: rr() * 6, live: false }
}

// --------------------------------------------------------------- the pieces
const HINGE = WALL_H + 0.03 // on the wall cap

// A slab hinged on the wall top (`inset` in from the wall line), its top face running down
// to a foot `d` further into the room; the body is extruded behind that face, toward the
// wall, so the foot is exactly where the footprint says. Steep leaners rest their foot on
// the heap at the wall's foot (inside the 0.5 m band robots keep off anyway); in a hazard
// room the slab comes right down onto the floor.
function buildSlab(p, a, d, inset, pancake, rr, out) {
  const thick = 0.18 + rr() * 0.07
  const lift = (thick * d) / Math.hypot(d, HINGE - 0.2) // how far the underside hangs below the top face at the foot
  const h0 = lift + (pancake ? 0.02 + rr() * 0.3 : 0.15 + rr() * 0.12)
  const L = Math.hypot(d, HINGE - h0)
  const ey = inwardOf(p.e).multiplyScalar(-d).addScaledVector(UP, HINGE - h0).normalize() // foot to wall top
  const F = frame(at(onEdge(p.e, (p.t0 + p.t1) / 2, inset), HINGE), alongOf(p.e), ey)
  const g = new THREE.ExtrudeGeometry(slabShape(a, L, rr), { depth: thick, bevelEnabled: false, curveSegments: 1 })
  g.translate(0, -L, -thick) // top edge at the origin, on the wall; foot at -L; body behind the face
  g.applyMatrix4(F)
  const [top, under] = splitUnder(g)
  g.dispose()
  out.slabs.push({ top, under })
  // rebar stubs out of the fracture, bent and kept off the floor
  for (let i = 0, n = Math.round(a * 2.5); i < n; i++) {
    const p0 = V3(-a / 2 + 0.15 + rr() * (a - 0.3), -L + 0.03, -thick / 2).applyMatrix4(F)
    const dir = (pancake
      ? V3((rr() - 0.5) * 0.6, -1, (rr() - 0.5) * 0.8)
      : V3((rr() < 0.5 ? -1 : 1) * (0.5 + rr() * 0.6), -0.35 * rr(), (rr() - 0.5) * 0.25)).transformDirection(F)
    let len = 0.2 + rr() * 0.25
    if (dir.y < 0) len = Math.min(len, Math.max(0.08, (p0.y - 0.05) / -dir.y))
    out.rebar.push(compose(p0.addScaledVector(dir, len / 2), yTo(dir), V3(0.012, len, 0.012)))
  }
}

const GRID = { cell: 0.6, bar: 0.025, barH: 0.03, top: WALL_H + 0.02 }

// A T-bar grid fragment hanging off the wall top, tilted so its low edge sits between 1.67
// and 2.05 m (1.6 m plus the live sway) and it reaches no further than `dCap` into the room.
// Bars and tiles are kept in the fragment's own frame so the live one can swing on its top edge.
function buildGrid(S, r, rr, out) {
  const cols = 2 + Math.floor(rr() * 3)
  const w = cols * GRID.cell
  const dCap = Math.min(2.0, r.short * 0.3)
  let rows = rr() < 0.5 ? 3 : 2
  let s = null
  for (; rows >= 2 && s == null; rows--) {
    const h = rows * GRID.cell
    const sinMax = Math.min(1, (GRID.top - 1.67) / h)
    const sinMin = Math.max((GRID.top - 2.05) / h, h > dCap ? Math.sqrt(1 - (dCap / h) ** 2) : 0)
    if (sinMin <= sinMax) s = { h, rows, sin: sinMin + rr() * (sinMax - sinMin) }
  }
  if (!s) return
  const th = Math.asin(s.sin)
  const p = place(S, r, rr, w, s.h * Math.cos(th) + 0.1, 0)
  if (!p) return
  const ey = inwardOf(p.e).multiplyScalar(Math.cos(th)).addScaledVector(UP, -Math.sin(th)) // down the slope
  const F = frame(at(onEdge(p.e, (p.t0 + p.t1) / 2, 0), GRID.top), alongOf(p.e), ey)
  const local = []
  const tiles = []
  for (let j = 0; j <= cols; j++) local.push(compose(V3(-w / 2 + j * GRID.cell, s.h / 2, 0), Q0, V3(GRID.bar, s.h, GRID.barH)))
  for (let i = 0; i <= s.rows; i++) local.push(compose(V3(0, i * GRID.cell, 0), Q0, V3(w, GRID.bar, GRID.barH)))
  for (let j = 0; j < cols; j++) {
    for (let i = 0; i < s.rows; i++) {
      if (rr() < 0.4) tiles.push(compose(V3(-w / 2 + (j + 0.5) * GRID.cell, (i + 0.5) * GRID.cell, GRID.barH / 2 + 0.006), Q0, V3(GRID.cell - 0.03, GRID.cell - 0.03, 0.012)))
    }
  }
  out.grids.push({ F, local, tiles, live: false, phase: rr() * 6, area: r.area, hazard: r.hazard })
  // a cable off the low edge
  const low = V3(-w / 2 + 0.2 + rr() * (w - 0.4), s.h, 0).applyMatrix4(F)
  out.gridCables.push(cable(low, inwardOf(p.e).multiplyScalar(0.5).addScaledVector(alongOf(p.e), rr() - 0.5).normalize(), rr))
}

const DUCT = { h: 0.28, w: 0.36, y: 1.88, off: 0.32, seg: 1.5 }

// A galvanized duct run along edge `e`, 1.5 m sections with a flange at each joint. One
// section came loose: it hangs from the joint it is still bolted to, swung down flat
// against the wall (so it stays in the 0.5 m band), and the ends either side are torn open.
function buildDuct(S, r, e, t0, t1, rr, out) {
  const along = alongOf(e)
  const normal = along.clone().cross(UP)
  const q = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(along, UP, normal))
  const n = Math.floor((t1 - t0) / DUCT.seg)
  const len = (t1 - t0) / n
  const center = (i) => at(onEdge(e, t0 + (i + 0.5) * len, DUCT.off), DUCT.y)
  let drop = -1
  for (let k = 0; k < 12 && drop < 0; k++) {
    const i = 1 + Math.floor(rr() * (n - 2))
    const f = strip(e, t0 + i * len, t0 + (i + 1) * len, 0.6)
    if (fits(S, r, f, 1.2)) { drop = i; r.taken.push(f) }
  }
  const dir = rr() < 0.5 ? 1 : -1 // which way the loose piece swung
  for (let i = 0; i < n; i++) {
    if (i === drop) continue
    if (drop >= 0 && Math.abs(i - drop) === 1) {
      // torn ends either side of the gap, the one it tore away from crushed flat
      const crush = i === drop - dir ? 0.55 : 0.85
      const g = openBox(len - 0.02, DUCT.h * crush, DUCT.w)
      g.applyMatrix4(compose(center(i), q.clone().multiply(roll((rr() - 0.5) * 0.4)), ONE))
      out.ductOpen.push(g)
    } else {
      out.ductBoxes.push(compose(center(i), q, V3(len - 0.02, DUCT.h, DUCT.w)))
    }
  }
  for (let i = 0; i <= n; i++) {
    if (drop >= 0 && (i === drop || i === drop + 1)) continue
    out.flanges.push(compose(at(onEdge(e, t0 + i * len, DUCT.off), DUCT.y), q, V3(0.03, DUCT.h + 0.05, DUCT.w + 0.05)))
  }
  if (drop < 0) return
  const phi = 0.95 + rr() * 0.35 // 55-75 degrees down
  const d = along.clone().multiplyScalar(dir * Math.cos(phi)).addScaledVector(UP, -Math.sin(phi))
  const hinge = at(onEdge(e, t0 + (drop + (dir > 0 ? 0 : 1)) * len, DUCT.off), DUCT.y)
  const g = openBox(len, DUCT.h * 0.8, DUCT.w)
  g.applyMatrix4(new THREE.Matrix4().makeBasis(d, normal.clone().cross(d), normal).setPosition(hinge.clone().addScaledVector(d, len / 2)))
  out.ductOpen.push(g)
  // the cable that was clipped to it, hanging down the wall
  out.ductCables.push(cable(hinge.clone().addScaledVector(UP, 0.1), along.clone().multiplyScalar(-dir), rr))
}

// Both halves of a snapped I-beam hinge down from the wall tops into a V, the broken ends
// slid past each other, with bent rebar bridging the snap and cables hanging off each end.
function buildBeam(b, rr, out) {
  const top = WALL_H - 0.12
  const A = at(b.a, top)
  const B = at(b.b, top)
  const dir = B.clone().sub(A).normalize()
  const side = dir.clone().cross(UP)
  const S0 = A.clone().lerp(B, 0.5 + (rr() - 0.5) * 0.2)
  S0.y = 1.74 + rr() * 0.08 // bottom flange stays above 1.6 m
  const S1 = S0.clone().addScaledVector(dir, -0.1).addScaledVector(side, 0.06)
  const S2 = S0.clone().addScaledVector(dir, 0.12).addScaledVector(side, -0.05)
  const rust = rr() < 0.5
  for (const [P, Q] of [[A, S1], [B, S2]]) {
    out.beams.push({ geom: ibeam(P.distanceTo(Q)), pos: P.clone().lerp(Q, 0.5), q: xTo(Q.clone().sub(P)).multiply(roll((rr() - 0.5) * 0.5)), rust })
  }
  for (let k = 0, n = 3 + Math.floor(rr() * 3); k < n; k++) {
    const jit = () => V3((rr() - 0.5) * 0.1, (rr() - 0.5) * 0.2, (rr() - 0.5) * 0.1)
    const p0 = S1.clone().add(jit())
    const p2 = S2.clone().add(jit())
    const c = p0.clone().lerp(p2, 0.5).addScaledVector(UP, -(0.1 + rr() * 0.12)).addScaledVector(side, (rr() - 0.5) * 0.3)
    c.y = Math.max(c.y, 1.72) // the sag stays inside the 1.6 m line mid-room
    out.scraps.push(tube(p0, c, p2, 0.012))
  }
  const flip = rr() < 0.5 ? 1 : -1
  out.cables.push(cable(S1.clone().addScaledVector(dir, -0.2).addScaledVector(UP, -0.11), side.clone().multiplyScalar(flip), rr))
  out.cables.push(cable(S2.clone().addScaledVector(dir, 0.25).addScaledVector(UP, -0.11), side.clone().multiplyScalar(-flip), rr))
}

// Conduit torn off its clips: sagging between two points on a wall top, or (the last one)
// with a loose end hanging down the wall.
function buildConduit(S, r, rr, loose, out) {
  for (const e of shuffle(edges(r.rect), rr)) {
    const len = e.hi - e.lo
    if (len < 5) continue
    for (let k = 0; k < 6; k++) {
      const a = 2.5 + rr() * 1.5
      const t0 = e.lo + 0.5 + rr() * (len - a - 1)
      if (!solidOn(S.walls, e, t0, t0 + a)) continue
      if (r.taken.some((o) => overlaps(o, strip(e, t0, t0 + a, 0.5)))) continue
      const p0 = at(onEdge(e, t0, 0.22), HINGE)
      if (loose) {
        const end = at(onEdge(e, t0 + 0.4 + rr() * 0.3, 0.3), 0.9 + rr() * 0.3)
        const c = p0.clone().lerp(end, 0.5).addScaledVector(inwardOf(e), 0.15)
        out.conduits.push(tube(p0, c, end, 0.02))
      } else {
        const p2 = at(onEdge(e, t0 + a, 0.22), HINGE)
        const c = p0.clone().lerp(p2, 0.5)
        c.y = 1.15 + rr() * 0.3 // the middle sags to 1.68-1.83 m
        out.conduits.push(tube(p0, c, p2, 0.02))
      }
      return true
    }
  }
  return false
}

// --------------------------------------------------------------- layout
function layout(fp) {
  const S = site(fp)
  const [W, H] = fp.size
  const rr = rng(hash(W, H, S.rooms.length, 13))
  const out = { slabs: [], rebar: [], beams: [], scraps: [], grids: [], ductBoxes: [], flanges: [], ductOpen: [],
    cables: [], ductCables: [], gridCables: [], conduits: [] }
  // beams first: slabs and grids keep off the wall tops where a beam lands
  for (const r of S.rooms) {
    r.beam = planBeam(S, r)
    if (r.beam) for (const p of [r.beam.a, r.beam.b]) r.taken.push([p[0] - 0.35, p[0] + 0.35, p[1] - 0.35, p[1] + 0.35])
  }
  // a duct run along one wall of two or three rooms, parallel to the room's beam so the
  // two never cross; the whole run is claimed so nothing leans through it
  let ducts = 2 + (rr() < 0.5 ? 1 : 0)
  for (const r of shuffle(S.rooms.filter((o) => !o.hazard && o.area >= 30), rr)) {
    if (!ducts) break
    const es = edges(r.rect).filter((e) => !r.beam || e.axis === (r.beam.alongX ? 'x' : 'y'))
    const order = [...es.filter((e) => !doorOn(S.doors, e)), ...es.filter((e) => doorOn(S.doors, e))]
    for (const e of order) {
      const t0 = e.lo + 0.5
      const t1 = e.hi - 0.5
      if (t1 - t0 < 6 || !solidOn(S.walls, e, t0, t1)) continue
      const run = strip(e, t0, t1, 0.6)
      if (r.taken.some((o) => overlaps(o, run)) || S.roofs.some((o) => overlaps(o, run))) continue
      buildDuct(S, r, e, t0, t1, rr, out)
      r.taken.push(run)
      ducts--
      break
    }
  }
  for (const r of S.rooms) {
    if (r.area < 12) continue
    const n = r.hazard ? 2 : 1 + (r.area > 100 && rr() < 0.6 ? 1 : 0)
    for (let k = 0; k < n; k++) {
      // hinged on the inner half of the cap so the body behind the face stays in the wall;
      // a leaner's foot ends 0.42-0.48 m from the wall line, the heap's width
      const a = r.hazard ? 2.6 + rr() * 1.8 : 1.5 + rr() * 1.5
      const inset = 0.12
      const d = r.hazard ? Math.min(1.6 + rr() * 1.0, r.short * 0.3) : 0.3 + rr() * 0.06
      // 1.25 m door gap: the outline wanders 0.15 m past the footprint
      const p = place(S, r, rr, a, inset + d + 0.1, 1.25)
      if (p) buildSlab(p, a, d, inset, r.hazard, rr, out)
    }
  }
  for (const r of S.rooms) {
    if (r.area < 15) continue
    for (let k = 0, n = 1 + (r.area > 120 && rr() < 0.5 ? 1 : 0); k < n; k++) buildGrid(S, r, rr, out)
  }
  for (const r of S.rooms) if (r.beam?.ours) buildBeam(r.beam, rr, out)
  let conds = 2 + (rr() < 0.5 ? 1 : 0)
  for (const r of shuffle(S.rooms.filter((o) => o.area >= 30), rr)) {
    if (conds && buildConduit(S, r, rr, conds === 1, out)) conds--
  }
  // 8-16 cables: the beam ones first (they hang in the open, where a sway shows), three of
  // them live; the swinging grid is the one in the biggest ordinary room
  out.cables = [...out.cables, ...out.ductCables, ...out.gridCables].slice(0, 16)
  out.cables.slice(0, 3).forEach((c) => { c.live = true })
  const swing = out.grids.filter((g) => !g.hazard).sort((p, q) => q.area - p.area)[0] ?? out.grids[0]
  if (swing) swing.live = true
  out.cableGeom = merge(out.cables.filter((c) => !c.live).map((c) => tube(c.a, c.c, c.e, c.r)))
  out.scrapGeom = merge(out.scraps)
  out.conduitGeom = merge(out.conduits)
  return out
}

const cache = new WeakMap()
const layoutFor = (fp) => {
  if (!cache.has(fp)) cache.set(fp, layout(fp))
  return cache.get(fp)
}

// --------------------------------------------------------------- materials
let shared = null
function mats() {
  if (shared) return shared
  const t = materials()
  shared = {
    slab: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 0.5, 0.5), color: '#a9a49c', roughness: 0.92 }),
    slabUnder: new THREE.MeshStandardMaterial({ color: '#66625c', roughness: 0.96 }),
    rebar: new THREE.MeshStandardMaterial({ color: '#7c3f1d', metalness: 0.6, roughness: 0.75 }),
    steel: new THREE.MeshStandardMaterial({ color: '#4a5058', metalness: 0.75, roughness: 0.5 }),
    rust: new THREE.MeshStandardMaterial({ ...tiledSet(t.rust, 1, 1), color: '#8c7a68', metalness: 0.6, roughness: 0.6 }),
    tbar: new THREE.MeshStandardMaterial({ color: '#6b7076', metalness: 0.55, roughness: 0.55 }), // dusty aluminium, not chrome
    tile: new THREE.MeshStandardMaterial({ color: '#b9b3a6', roughness: 0.96 }),
    duct: new THREE.MeshStandardMaterial({ color: '#9ea7ad', metalness: 0.85, roughness: 0.35, side: THREE.DoubleSide }),
    cable: new THREE.MeshStandardMaterial({ color: '#0c0d0f', roughness: 0.65 }),
    conduit: new THREE.MeshStandardMaterial({ color: '#868c92', metalness: 0.6, roughness: 0.45 }),
  }
  return shared
}

// --------------------------------------------------------------- components
// One instanced mesh from a list of matrices. Never frustum culled: the unit geometry's
// bounds say nothing about where the instances went.
function Instanced({ geom, material, mats: list, shadow = false }) {
  const ref = useRef()
  useLayoutEffect(() => {
    if (!ref.current) return
    list.forEach((m, i) => ref.current.setMatrixAt(i, m))
    ref.current.instanceMatrix.needsUpdate = true
  }, [list])
  if (!list.length) return null
  return <instancedMesh ref={ref} args={[geom, material, list.length]} castShadow={shadow} receiveShadow frustumCulled={false} />
}

// Everything that does not move: mount inside <Baked>, which merges the plain meshes per
// material and leaves the instanced ones alone.
export function CeilingStatic({ fp }) {
  const L = layoutFor(fp)
  const M = mats()
  const grid = useMemo(() => {
    const still = L.grids.filter((g) => !g.live)
    return { bars: still.flatMap((g) => g.local.map((m) => g.F.clone().multiply(m))), tiles: still.flatMap((g) => g.tiles.map((m) => g.F.clone().multiply(m))) }
  }, [L])
  return (
    <group>
      {L.slabs.map((s, i) => (
        <group key={i}>
          <mesh geometry={s.top} material={M.slab} castShadow receiveShadow />
          {s.under.attributes.position.count > 0 && <mesh geometry={s.under} material={M.slabUnder} receiveShadow />}
        </group>
      ))}
      <Instanced geom={CYL} material={M.rebar} mats={L.rebar} />
      {L.beams.map((b, i) => <mesh key={i} geometry={b.geom} position={b.pos} quaternion={b.q} material={b.rust ? M.rust : M.steel} castShadow />)}
      {L.scrapGeom && <mesh geometry={L.scrapGeom} material={M.rebar} />}
      <Instanced geom={BOX} material={M.tbar} mats={grid.bars} shadow />
      <Instanced geom={BOX} material={M.tile} mats={grid.tiles} shadow />
      <Instanced geom={BOX} material={M.duct} mats={L.ductBoxes} shadow />
      <Instanced geom={BOX} material={M.steel} mats={L.flanges} />
      {L.ductOpen.map((g, i) => <mesh key={i} geometry={g} material={M.duct} castShadow />)}
      {L.cableGeom && <mesh geometry={L.cableGeom} material={M.cable} />}
      {L.conduitGeom && <mesh geometry={L.conduitGeom} material={M.conduit} />}
    </group>
  )
}

const SWAY = 0.035 // radians, about 2 degrees

// Three cables and one grid fragment swinging slowly on their anchors. With `perf` they
// still render (so the scene is the same) but nothing moves.
export function CeilingLive({ fp, perf = false }) {
  const L = layoutFor(fp)
  const M = mats()
  const live = useMemo(() => {
    const grid = L.grids.find((g) => g.live) ?? null
    const pose = { p: new THREE.Vector3(), q: new THREE.Quaternion() }
    if (grid) grid.F.decompose(pose.p, pose.q, new THREE.Vector3())
    return {
      cables: L.cables.filter((c) => c.live).map((c) => ({ ...c, geom: tube(V3(0, 0, 0), c.c.clone().sub(c.a), c.e.clone().sub(c.a), c.r) })),
      grid, pose,
    }
  }, [L])
  const cableRefs = useRef([])
  const gridRef = useRef()
  useFrame(({ clock }) => {
    if (perf) return
    const t = clock.elapsedTime
    for (let i = 0; i < live.cables.length; i++) {
      const g = cableRefs.current[i]
      const c = live.cables[i]
      if (!g) continue
      g.rotation.x = Math.sin(t * c.f + c.phase) * SWAY
      g.rotation.z = Math.cos(t * c.f * 0.8 + c.phase) * SWAY
    }
    if (gridRef.current && live.grid) gridRef.current.rotation.x = Math.sin(t * 0.45 + live.grid.phase) * SWAY
  })
  return (
    <group>
      {live.cables.map((c, i) => (
        <group key={i} position={c.a} ref={(el) => { cableRefs.current[i] = el }}>
          <mesh geometry={c.geom} material={M.cable} />
        </group>
      ))}
      {live.grid && (
        <group position={live.pose.p} quaternion={live.pose.q}>
          <group ref={gridRef}>
            <Instanced geom={BOX} material={M.tbar} mats={live.grid.local} shadow />
            <Instanced geom={BOX} material={M.tile} mats={live.grid.tiles} shadow />
          </group>
        </group>
      )}
    </group>
  )
}
