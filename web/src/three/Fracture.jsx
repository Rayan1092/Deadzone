import { useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { Delaunay } from 'd3-delaunay'
import { WALL_H, w2t } from './util'
import { materials, tiledSet } from './textures'
import { WIN } from './Collapse'

// Earthquake-broken walls. Every wall stands exactly where the floorplan puts it (the
// robots, radio and demo guard see the same straight segment), but it is drawn as a
// fractured slab: the wall face is split into convex Voronoi cells, cells above a jagged
// break line, inside breaches and windows are removed, the cells along the break are
// pushed and tilted, bent rebar sticks out of the broken edge, a plaster skin has spalled
// off in patches to show the brick or concrete underneath, a few sections lean over, and
// the removed pieces lie at the foot of the wall. Each cell is a small prism, so the cut
// faces (fresh, lighter material) are separate from the wall faces. All walls merge into
// one mesh per material: about ten draw calls for the whole building.
// Deterministic from the wall geometry, so every client and reload agrees.

function rng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}
const hash = (...xs) => xs.reduce((h, x) => (h * 31 + Math.round(x * 100)) % 1000003, 7)

const THICK = { concrete: 0.3, brick: 0.2, drywall: 0.12 }
// how much of each wall type is left standing: mean height fraction, its spread, and how
// deep the occasional bite goes
const BREAK = {
  outer: { mean: 0.86, spread: 0.14, bite: 0.5 },
  concrete: { mean: 0.76, spread: 0.2, bite: 0.5 },
  brick: { mean: 0.68, spread: 0.26, bite: 0.5 },
  drywall: { mean: 0.56, spread: 0.3, bite: 0.4 },
}
const SKIN = 0.012      // plaster thickness
const MAX_FALLEN = 16   // pieces per wall lying at its foot
const MAX_REBAR = 28    // per wall

// --------------------------------------------------------------- break line
// Height of what is left of the wall at x (wall-local, centered). Coherent noise plus a
// few bites; the last 0.45 m before each end stands, so door jambs and corners hold.
function makeProfile(seed, L, spec) {
  const r = rng(seed)
  const n = Math.max(3, Math.round(L / 0.8) + 1)
  const pts = Array.from({ length: n }, () => spec.mean + (r() - 0.5) * 2 * spec.spread)
  const bites = Array.from({ length: Math.round(L / 3.5) }, () => ({
    x: (r() - 0.5) * Math.max(0.5, L - 1), w: 0.35 + r() * 0.6, d: spec.bite * (0.5 + r() * 0.5),
  }))
  return (x) => {
    const t = ((x + L / 2) / L) * (n - 1)
    const i = Math.max(0, Math.min(n - 2, Math.floor(t)))
    const f = t - i
    const s = f * f * (3 - 2 * f)
    let h = pts[i] * (1 - s) + pts[i + 1] * s
    for (const b of bites) { const d = (x - b.x) / b.w; h -= b.d * Math.exp(-d * d) }
    const end = Math.min(x + L / 2, L / 2 - x)
    if (end < 0.45) h = Math.max(h, 0.92 - (0.92 - h) * (end / 0.45))
    return WALL_H * Math.max(0.12, Math.min(1, h))
  }
}

// --------------------------------------------------------------- geometry
// Triangle soup with two groups: 0 = wall faces (textured like the wall), 1 = cut faces
// (the broken material inside).
class Soup {
  constructor() { this.face = { p: [], n: [], uv: [] }; this.cut = { p: [], n: [], uv: [] } }
  tri(g, a, b, c, nx, ny, nz, uva, uvb, uvc, m, nm) {
    const v = Soup.v
    for (const [pt, uv] of [[a, uva], [b, uvb], [c, uvc]]) {
      v.set(pt[0], pt[1], pt[2]).applyMatrix4(m)
      g.p.push(v.x, v.y, v.z)
      g.uv.push(uv[0], uv[1])
    }
    v.set(nx, ny, nz).applyMatrix3(nm).normalize()
    for (let k = 0; k < 3; k++) g.n.push(v.x, v.y, v.z)
  }
  // convex polygon (CCW in x/y), extruded from z0 to z1, transformed by m
  prism(poly, z0, z1, m) {
    const nm = Soup.nm.getNormalMatrix(m)
    const k = poly.length
    for (let i = 1; i < k - 1; i++) {
      const [a, b, c] = [poly[0], poly[i], poly[i + 1]]
      this.tri(this.face, [a[0], a[1], z1], [b[0], b[1], z1], [c[0], c[1], z1], 0, 0, 1, a, b, c, m, nm)
      this.tri(this.face, [a[0], a[1], z0], [c[0], c[1], z0], [b[0], b[1], z0], 0, 0, -1, a, c, b, m, nm)
    }
    let s = 0
    for (let i = 0; i < k; i++) {
      const a = poly[i]
      const b = poly[(i + 1) % k]
      const ex = b[0] - a[0]
      const ey = b[1] - a[1]
      const len = Math.hypot(ex, ey)
      const v0 = [a[0], a[1], z0], v1 = [b[0], b[1], z0], v2 = [b[0], b[1], z1], v3 = [a[0], a[1], z1]
      this.tri(this.cut, v0, v1, v2, ey, -ex, 0, [s, z0], [s + len, z0], [s + len, z1], m, nm)
      this.tri(this.cut, v0, v2, v3, ey, -ex, 0, [s, z0], [s + len, z1], [s, z1], m, nm)
      s += len
    }
  }
  geometry() {
    const g = new THREE.BufferGeometry()
    const p = new Float32Array(this.face.p.length + this.cut.p.length)
    p.set(this.face.p); p.set(this.cut.p, this.face.p.length)
    const n = new Float32Array(this.face.n.length + this.cut.n.length)
    n.set(this.face.n); n.set(this.cut.n, this.face.n.length)
    const uv = new Float32Array(this.face.uv.length + this.cut.uv.length)
    uv.set(this.face.uv); uv.set(this.cut.uv, this.face.uv.length)
    g.setAttribute('position', new THREE.BufferAttribute(p, 3))
    g.setAttribute('normal', new THREE.BufferAttribute(n, 3))
    g.setAttribute('uv', new THREE.BufferAttribute(uv, 2))
    const nf = this.face.p.length / 3
    g.addGroup(0, nf, 0)
    g.addGroup(nf, this.cut.p.length / 3, 1)
    g.computeBoundingSphere()
    return g
  }
  get empty() { return !this.face.p.length && !this.cut.p.length }
}
Soup.v = new THREE.Vector3()
Soup.nm = new THREE.Matrix3()

function ccw(poly) {
  let a = 0
  for (let i = 0; i < poly.length; i++) { const p = poly[i], q = poly[(i + 1) % poly.length]; a += p[0] * q[1] - q[0] * p[1] }
  return a >= 0 ? poly : poly.slice().reverse()
}
function centroid(poly) {
  let x = 0, y = 0
  for (const p of poly) { x += p[0]; y += p[1] }
  return [x / poly.length, y / poly.length]
}
function shrink(poly, c, f) { return poly.map(([x, y]) => [c[0] + (x - c[0]) * f, c[1] + (y - c[1]) * f]) }
function area(poly) {
  let a = 0
  for (let i = 0; i < poly.length; i++) { const p = poly[i], q = poly[(i + 1) % poly.length]; a += p[0] * q[1] - q[0] * p[1] }
  return Math.abs(a) / 2
}

// Voronoi cells of a jittered grid over the wall face, denser along the break line and
// around breaches so the torn edges have small pieces.
function cells(r, L, top, breaches, windows, sx, sy, fine) {
  const pts = []
  // intact panels are big: a coarse jittered grid
  for (let y = sy / 2; y < WALL_H + sy; y += sy) for (let x = -L / 2 + sx / 2; x < L / 2; x += sx) {
    pts.push([x + (r() - 0.5) * sx * 0.9, y + (r() - 0.5) * sy * 0.9])
  }
  // small pieces only where it broke: a band along the break line, rings around breaches,
  // a few around window edges
  for (let x = -L / 2 + 0.08; x < L / 2; x += fine) {
    pts.push([x + (r() - 0.5) * fine, top(x) + (r() - 0.5) * 0.45])
    if (r() < 0.5) pts.push([x + (r() - 0.5) * fine, top(x) - 0.3 - r() * 0.35])
  }
  for (const b of breaches) for (let k = 0; k < 22; k++) {
    const a = r() * Math.PI * 2
    const f = 0.75 + r() * 0.75
    pts.push([b.x + Math.cos(a) * b.rx * f, b.y + Math.sin(a) * b.ry * f])
  }
  for (const win of windows) for (let k = 0; k < 6; k++) {
    pts.push([win.x + (r() < 0.5 ? -1 : 1) * (WIN.w / 2 + 0.05 + r() * 0.25), WIN.y0 + r() * (WIN.y1 - WIN.y0)])
  }
  const vor = Delaunay.from(pts).voronoi([-L / 2, 0, L / 2, WALL_H])
  const out = []
  for (let i = 0; i < pts.length; i++) {
    const poly = vor.cellPolygon(i)
    if (!poly || poly.length < 4) continue
    poly.pop()
    out.push(ccw(poly))
  }
  return out
}

// --------------------------------------------------------------- one wall
const M4 = new THREE.Matrix4()
const Q = new THREE.Quaternion()
const E = new THREE.Euler()
const V = new THREE.Vector3()
const ONE = new THREE.Vector3(1, 1, 1)

function buildWall(w, dmg, size, soups, rebar) {
  const [ax, ay] = w.a
  const [bx, by] = w.b
  const L = Math.hypot(bx - ax, by - ay)
  if (L < 0.3) return
  const thick = THICK[w.material] ?? 0.2
  const [W, H] = size
  const outer = (ax === bx && (ax === 0 || ax === W)) || (ay === by && (ay === 0 || ay === H))
  const seed = hash(ax, ay, bx, by, 3)
  const r = rng(seed)
  const top = makeProfile(seed + 1, L, outer ? BREAK.outer : (BREAK[w.material] ?? BREAK.brick))
  // wall frame -> world
  const [px, , pz] = w2t((ax + bx) / 2, (ay + by) / 2, 0)
  const frame = new THREE.Matrix4().makeRotationY(Math.atan2(by - ay, bx - ax)).setPosition(px, 0, pz)
  const breaches = dmg?.breaches ?? []
  const windows = dmg?.windows ?? []
  const inBreach = (x, y, f = 1) => breaches.some((b) => ((x - b.x) / (b.rx * f)) ** 2 + ((y - b.y) / (b.ry * f)) ** 2 < 1)
  const inWindow = (x, y) => windows.some((win) => Math.abs(x - win.x) < WIN.w / 2 && y > WIN.y0 && y < WIN.y1)
  const nearEnd = (x) => Math.min(x + L / 2, L / 2 - x) < 0.35

  // a leaning section: cells above the hinge in this span tip over to one side
  const lean = !outer && L >= 4 && r() < 0.3
    ? { x0: -L / 2 + 0.8 + r() * (L - 2.8), w: 1.2 + r() * 0.8, side: r() < 0.5 ? 1 : -1, ang: 0.2 + r() * 0.2, hinge: 0.5 }
    : null
  const leanM = lean ? new THREE.Matrix4().makeTranslation(0, lean.hinge, lean.side * thick / 2)
    .multiply(new THREE.Matrix4().makeRotationX(-lean.side * lean.ang))
    .multiply(new THREE.Matrix4().makeTranslation(0, -lean.hinge, -lean.side * thick / 2)) : null

  const core = soups.core[w.material] ?? soups.core.brick
  const fallenSoup = soups.fallen[w.material] ?? soups.fallen.brick
  let fallen = 0
  let bars = 0

  for (const poly of cells(r, L, top, breaches, windows, 1.1, 0.85, 0.26)) {
    const c = centroid(poly)
    const removed = c[1] > top(c[0]) || inBreach(c[0], c[1]) || inWindow(c[0], c[1]) ||
      (nearEnd(c[0]) && c[1] > 1.5 && r() < 0.45) // spalled corners
    if (removed) {
      // the piece that fell: lies flat at the foot of the wall (never near the segment ends,
      // which is where the door openings are)
      if (fallen < MAX_FALLEN && c[1] < WALL_H - 0.15 && !inWindow(c[0], c[1]) && area(poly) > 0.03 && r() < 0.5 &&
          Math.min(c[0] + L / 2, L / 2 - c[0]) > 0.7) {
        const side = r() < 0.5 ? 1 : -1
        const local = shrink(poly, c, 0.96).map(([x, y]) => [x - c[0], y - c[1]])
        M4.compose(
          V.set(c[0] + (r() - 0.5) * 0.4, thick / 2 + 0.01 + (r() < 0.25 ? 0.12 : 0), side * (thick / 2 + 0.05 + r() * 0.3)),
          Q.setFromEuler(E.set((side > 0 ? 1 : -1) * (Math.PI / 2 + (r() - 0.5) * 0.35), (r() - 0.5) * 1.2, (r() - 0.5) * 0.3)), ONE)
        fallenSoup.prism(local, -thick / 2, thick / 2, frame.clone().multiply(M4))
        fallen++
      }
      continue
    }
    const edge = poly.some(([x, y]) => y > top(x) - 0.06 || inBreach(x, y, 1.08) || inWindow(x, y + 0.04) || inWindow(x, y - 0.04))
    // edge cells shift and tilt a little: the torn look
    M4.identity()
    if (edge) {
      M4.compose(V.set(0, -0.012 * r(), (r() - 0.5) * thick * 0.22), Q.setFromEuler(E.set((r() - 0.5) * 0.1, 0, (r() - 0.5) * 0.05)), ONE)
      // the shift pivots on the cell centre
      M4.multiply(new THREE.Matrix4().makeTranslation(-c[0], -c[1], 0)).premultiply(new THREE.Matrix4().makeTranslation(c[0], c[1], 0))
    }
    if (lean && c[0] > lean.x0 && c[0] < lean.x0 + lean.w && c[1] > lean.hinge) M4.premultiply(leanM)
    const m = frame.clone().multiply(M4)
    core.prism(shrink(poly, c, edge ? 0.965 : 0.996), -thick / 2 + (w.material === 'drywall' ? 0 : SKIN), thick / 2 - (w.material === 'drywall' ? 0 : SKIN), m)
    // rebar out of the torn edge
    if (edge && bars < MAX_REBAR && r() < 0.4) {
      const v = poly.reduce((best, p) => (p[1] > best[1] ? p : best), poly[0])
      const b = breaches.find((bb) => inBreach(v[0], v[1], 1.3))
      let tilt
      if (b) tilt = E.set(0, 0, -Math.atan2(v[0] - b.x, v[1] - b.y) + (r() - 0.5) * 0.4)
      else tilt = E.set((r() - 0.5) * 0.9, 0, (r() - 0.5) * 0.8)
      M4.compose(V.set(v[0], v[1] - 0.05, (r() - 0.5) * thick * 0.5), Q.setFromEuler(tilt), V.set(1, 0.6 + r() * 0.9, 1))
      rebar.push(m.clone().multiply(M4))
      bars++
    }
  }

  // plaster skin: coarser cells on each face, missing where the core is gone and in spalled
  // patches (more near the break and at the damp floor line); exterior faces are bare
  if (w.material === 'drywall') return
  const faces = outer ? [ax === 0 || ay === H ? -1 : 1] : [-1, 1]
  const skinR = rng(seed + 7)
  for (const side of faces) {
    for (const poly of cells(skinR, L, top, breaches, windows, 1.4, 1.0, 0.4)) {
      const c = centroid(poly)
      if (c[1] > top(c[0]) - 0.08 || inBreach(c[0], c[1], 1.15) || inWindow(c[0], c[1])) continue
      const nearBreak = top(c[0]) - c[1] < 0.5 || inBreach(c[0], c[1], 1.6)
      const spall = skinR() < (nearBreak ? 0.55 : c[1] < 0.35 ? 0.3 : 0.16)
      if (spall) continue
      const z = side * (thick / 2 - SKIN / 2)
      let m = frame
      if (lean && c[0] > lean.x0 && c[0] < lean.x0 + lean.w && c[1] > lean.hinge) m = frame.clone().multiply(leanM)
      soups.skin.prism(shrink(poly, c, 0.997), z - SKIN / 2, z + SKIN / 2, m)
    }
  }
}

// --------------------------------------------------------------- materials
let mats = null
function wallMats() {
  if (mats) return mats
  const t = materials()
  const std = (o) => new THREE.MeshStandardMaterial(o)
  mats = {
    face: {
      brick: std({ ...tiledSet(t.brick, 0.5, 0.5), color: '#d2c8bf', roughness: 0.92 }),
      concrete: std({ ...tiledSet(t.concrete, 0.5, 0.5), color: '#c9c6c0', roughness: 0.88 }),
      drywall: std({ ...tiledSet(t.plaster, 0.5, 0.5), color: '#e6e0d6', roughness: 0.9 }),
    },
    cut: {
      brick: std({ ...tiledSet(t.brick, 0.9, 0.9), color: '#8f7868', roughness: 1 }),
      concrete: std({ ...tiledSet(t.rubble, 0.7, 0.7), color: '#cdc7bd', roughness: 1 }),
      drywall: std({ color: '#e2dccf', roughness: 1 }),
    },
    skinFace: std({ ...tiledSet(t.plaster, 0.5, 0.5), color: '#bfb8ad', roughness: 0.92 }),
    skinCut: std({ color: '#ddd6cb', roughness: 1 }),
    rebar: std({ ...tiledSet(t.rust, 2, 2), color: '#8a5a3a', metalness: 0.5, roughness: 0.8 }),
  }
  return mats
}

// Bent rebar: a tube along a kinked curve, scaled per instance.
let rebarGeom = null
function rebarGeometry() {
  if (rebarGeom) return rebarGeom
  const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0.26, 0), new THREE.Vector3(0.06, 0.42, 0.03)])
  rebarGeom = new THREE.TubeGeometry(curve, 6, 0.011, 5, false)
  return rebarGeom
}

// --------------------------------------------------------------- component
// walls: fp.walls (metal walls are skipped: the cage stays a fence). damage: wallDamage(fp)
// (same index). size: fp.size. All geometry is built in world space, so one mesh per
// material covers every wall.
export default function FracturedWalls({ walls, damage, size }) {
  const built = useMemo(() => {
    const soups = {
      core: { brick: new Soup(), concrete: new Soup(), drywall: new Soup() },
      fallen: { brick: new Soup(), concrete: new Soup(), drywall: new Soup() },
      skin: new Soup(),
    }
    const rebar = []
    walls.forEach((w, i) => { if (w.material !== 'metal') buildWall(w, damage?.[i], size, soups, rebar) })
    const geo = (s) => (s.empty ? null : s.geometry())
    return {
      core: Object.fromEntries(Object.entries(soups.core).map(([k, s]) => [k, geo(s)])),
      fallen: Object.fromEntries(Object.entries(soups.fallen).map(([k, s]) => [k, geo(s)])),
      skin: geo(soups.skin),
      rebar,
    }
  }, [walls, damage, size])
  const M = wallMats()
  const bars = useRef()
  useLayoutEffect(() => {
    if (!bars.current) return
    built.rebar.forEach((m, i) => bars.current.setMatrixAt(i, m))
    bars.current.instanceMatrix.needsUpdate = true
    bars.current.computeBoundingSphere()
  }, [built])
  return (
    <group>
      {Object.entries(built.core).map(([k, g]) => g && (
        <mesh key={k} geometry={g} material={[M.face[k], M.cut[k]]} castShadow receiveShadow />
      ))}
      {Object.entries(built.fallen).map(([k, g]) => g && (
        <mesh key={`f${k}`} geometry={g} material={[M.face[k], M.cut[k]]} castShadow receiveShadow />
      ))}
      {built.skin && <mesh geometry={built.skin} material={[M.skinFace, M.skinCut]} receiveShadow />}
      {built.rebar.length > 0 && (
        <instancedMesh ref={bars} args={[rebarGeometry(), M.rebar, built.rebar.length]} castShadow />
      )}
    </group>
  )
}
