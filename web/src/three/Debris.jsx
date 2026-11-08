import { useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { w2t } from './util'
import { materials, tiledSet } from './textures'

// Collapse debris on each truth rubble footprint: a mound of broken concrete chunks
// (instanced), a few cracked slabs with rebar sticking out, a dust stain spreading past
// the edges, and on the tall piles a fallen steel beam. Deterministic per rubble id.

function rng(seed) {
  let s = seed % 2147483647
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}

// Chunk shapes: icosahedra with their vertices pushed in and out, flat shaded so the
// facets read as fractured concrete.
const VARIANTS = 5
let chunkGeoms = null
export function chunks() {
  if (chunkGeoms) return chunkGeoms
  chunkGeoms = Array.from({ length: VARIANTS }, (_, k) => {
    const g = new THREE.IcosahedronGeometry(1, 1)
    const r = rng(500 + k * 37)
    const pos = g.attributes.position
    const moved = new Map() // shared corners must move together or the mesh tears
    for (let i = 0; i < pos.count; i++) {
      const key = `${pos.getX(i).toFixed(3)},${pos.getY(i).toFixed(3)},${pos.getZ(i).toFixed(3)}`
      if (!moved.has(key)) moved.set(key, 0.7 + r() * 0.5)
      const f = moved.get(key)
      pos.setXYZ(i, pos.getX(i) * f, pos.getY(i) * f * 0.75, pos.getZ(i) * f)
    }
    g.computeVertexNormals()
    return g
  })
  return chunkGeoms
}

function bounds(poly) {
  const xs = poly.map((p) => p[0])
  const ys = poly.map((p) => p[1])
  return [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
}

function layout(rubble) {
  const rocks = Array.from({ length: VARIANTS }, () => [])
  const slabs = []
  const bars = []
  const beams = []
  const stains = []
  rubble.forEach((rb, k) => {
    const [x0, x1, y0, y1] = bounds(rb.poly)
    const cx = (x0 + x1) / 2
    const cy = (y0 + y1) / 2
    const hx = (x1 - x0) / 2
    const hy = (y1 - y0) / 2
    const top = rb.height || 1
    const r = rng(1000 + k * 77)
    stains.push({ pos: [cx, cy], size: [hx * 2 + 1.6, hy * 2 + 1.6] })
    // mound: the further from the centre, the lower and the smaller
    const n = Math.round(hx * hy * 4 * 6)
    for (let i = 0; i < n; i++) {
      const u = (r() * 2 - 1) * 1.05
      const v = (r() * 2 - 1) * 1.05
      const d = Math.min(1, Math.hypot(u, v) / 1.2)
      const s = (0.12 + r() * 0.3) * (1.15 - d * 0.5)
      const h = Math.max(s * 0.4, (1 - d * d) * top * (0.55 + r() * 0.45))
      rocks[i % VARIANTS].push({
        pos: w2t(cx + u * hx, cy + v * hy, h - s * 0.3),
        rot: [r() * 6, r() * 6, r() * 6],
        scale: [s * (0.8 + r() * 0.6), s, s * (0.8 + r() * 0.6)],
        shade: 0.62 + r() * 0.38,
      })
    }
    // slabs leaning on the mound
    const ns = 2 + Math.round(hx * hy)
    for (let i = 0; i < ns; i++) {
      const a = r() * Math.PI * 2
      const sx = 0.8 + r() * 0.9
      const sz = 0.6 + r() * 0.7
      const lean = 0.25 + r() * 0.6
      const px = cx + Math.cos(a) * hx * 0.45
      const py = cy + Math.sin(a) * hy * 0.45
      slabs.push({
        pos: w2t(px, py, top * 0.35 + r() * top * 0.3),
        rot: [lean * (r() > 0.5 ? 1 : -1), a, lean * 0.5 * (r() - 0.5)],
        size: [sx, 0.14, sz],
      })
      // rebar poking out of the slab's broken edge
      for (let b = 0; b < 3; b++) {
        bars.push({
          pos: w2t(px + Math.cos(a) * sx * 0.45, py + Math.sin(a) * sx * 0.45, top * 0.45 + r() * 0.3),
          rot: [r() * 1.2 - 0.6, a, Math.PI / 2 + r() * 0.8 - 0.4],
          len: 0.4 + r() * 0.6,
        })
      }
    }
    // the ceiling slab that came down here, one edge on the floor and one up on the pile
    const lean = 0.55 + r() * 0.25
    slabs.push({ pos: w2t(cx + (r() - 0.5) * hx * 0.6, cy + (r() - 0.5) * hy * 0.6, top * 0.5 + 0.15),
      rot: [lean * (r() > 0.5 ? 1 : -1), r() * Math.PI, (r() - 0.5) * 0.25],
      size: [Math.min(1.9, hx * 1.4 + 0.3), 0.18, Math.min(2.0, hy * 1.4 + 0.4)] })
    if (top >= 1.5) {
      beams.push({
        pos: w2t(cx - hx * 0.1, cy, top * 0.55),
        rot: [0, r() * Math.PI, 0.35 + r() * 0.15],
        len: Math.max(hx, hy) * 2 + 1.2,
      })
    }
  })
  return { rocks, slabs, bars, beams, stains }
}

function Chunks({ geom, items, material }) {
  const ref = useRef()
  useLayoutEffect(() => {
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const e = new THREE.Euler()
    const c = new THREE.Color()
    items.forEach((it, i) => {
      q.setFromEuler(e.set(...it.rot))
      m.compose(new THREE.Vector3(...it.pos), q, new THREE.Vector3(...it.scale))
      ref.current.setMatrixAt(i, m)
      ref.current.setColorAt(i, c.setRGB(it.shade, it.shade * 0.97, it.shade * 0.93))
    })
    ref.current.instanceMatrix.needsUpdate = true
    if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true
  }, [items])
  if (!items.length) return null
  return <instancedMesh ref={ref} args={[geom, material, items.length]} castShadow receiveShadow />
}

export default function Debris({ rubble, cold = false }) {
  const plan = useMemo(() => layout(rubble), [rubble])
  const mats = useMemo(() => {
    if (cold) {
      const m = new THREE.MeshStandardMaterial({ color: '#1e293b', emissive: '#0b1d5c', flatShading: true })
      return { rock: m, slab: m, steel: m, rust: m }
    }
    const t = materials()
    return {
      rock: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 0.6, 0.6), color: '#d6d0c6', roughness: 0.95, flatShading: true }),
      slab: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 0.5, 0.5), color: '#cfc9bf', roughness: 0.9 }),
      steel: new THREE.MeshStandardMaterial({ color: '#59606a', metalness: 0.75, roughness: 0.5 }),
      rust: new THREE.MeshStandardMaterial({ color: '#7c3f1d', metalness: 0.6, roughness: 0.75 }),
    }
  }, [cold])
  const geoms = chunks()
  return (
    <group>
      {!cold && plan.stains.map((s, i) => (
        <mesh key={`st${i}`} rotation={[-Math.PI / 2, 0, i]} position={w2t(s.pos[0], s.pos[1], 0.008)} renderOrder={0}>
          <planeGeometry args={s.size} />
          <meshStandardMaterial map={materials().dust} transparent depthWrite={false} roughness={1} />
        </mesh>
      ))}
      {plan.rocks.map((items, k) => <Chunks key={k} geom={geoms[k]} items={items} material={mats.rock} />)}
      {plan.slabs.map((s, i) => (
        <mesh key={`sl${i}`} position={s.pos} rotation={s.rot} material={mats.slab} castShadow receiveShadow>
          <boxGeometry args={s.size} />
        </mesh>
      ))}
      {plan.bars.map((b, i) => (
        <mesh key={`rb${i}`} position={b.pos} rotation={b.rot} material={mats.rust} castShadow>
          <cylinderGeometry args={[0.012, 0.012, b.len, 5]} />
        </mesh>
      ))}
      {plan.beams.map((b, i) => (
        // I-beam: web plus two flanges
        <group key={`bm${i}`} position={b.pos} rotation={b.rot}>
          <mesh material={mats.steel} castShadow><boxGeometry args={[b.len, 0.26, 0.03]} /></mesh>
          <mesh material={mats.steel} position={[0, 0.13, 0]} castShadow><boxGeometry args={[b.len, 0.03, 0.16]} /></mesh>
          <mesh material={mats.steel} position={[0, -0.13, 0]} castShadow><boxGeometry args={[b.len, 0.03, 0.16]} /></mesh>
        </group>
      ))}
    </group>
  )
}
