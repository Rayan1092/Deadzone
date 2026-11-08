import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { WALL_H, w2t } from './util'
import { useSim } from '../store'
import { LightBeam } from './NightLights'
import { materials, tiledSet } from './textures'

// Collapse damage on the Reality world, all derived from the floorplan so a generated
// building gets it too: windows (mostly blown out) in the outer walls, jagged breaches
// through some interior walls, cracks, a surviving piece of roof over the no-go hazard
// zone with rebar hanging off its broken edge, beams across rooms (some sagging, with a
// light fitting dangling on its cable) and dust hanging in the air. Visual only: the
// truth grid, radio and robots never see any of it, so nothing here may block a path
// (breaches start above the floor, debris hugs the walls).

function rng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}
const hash = (...xs) => xs.reduce((h, x) => (h * 31 + Math.round(x * 100)) % 1000003, 7)

// --------------------------------------------------------------- walls
export const WIN = { w: 1.3, y0: 1.0, y1: 1.85, step: 3.6, margin: 1.6 }

function isOuter(w, W, H) {
  const [ax, ay] = w.a
  const [bx, by] = w.b
  return (ax === bx && (ax === 0 || ax === W)) || (ay === by && (ay === 0 || ay === H))
}

// Per wall (same order as fp.walls): window and breach holes in wall-local x (centered,
// along the wall) and y (up), plus an optional crack decal.
export function wallDamage(fp) {
  const [W, H] = fp.size
  return fp.walls.map((w, i) => {
    if (w.material === 'metal') return null
    const len = Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1])
    const r = rng(hash(i, w.a[0], w.a[1], w.b[0], w.b[1]))
    const out = { windows: [], breaches: [], crack: null }
    if (isOuter(w, W, H)) {
      const n = Math.floor((len - 2 * WIN.margin) / WIN.step) + 1
      const span = (n - 1) * WIN.step
      for (let k = 0; k < n && n > 0; k++) {
        const x = -span / 2 + k * WIN.step
        // one window in four on the long walls became a ragged breach in the facade
        if (len > 20 && k % 4 === 2) out.breaches.push({ x, y: 1.35, rx: 1.0, ry: 0.75, seed: hash(i, k) })
        else out.windows.push({ x, broken: r() < 0.75, seed: hash(i, k, 3) })
      }
    } else if (len >= 6 && r() < 0.45) {
      out.breaches.push({ x: (r() - 0.5) * (len - 3), y: 1.3 + r() * 0.2, rx: 0.6 + r() * 0.35, ry: 0.45 + r() * 0.25, seed: hash(i, 9) })
    }
    if (len >= 3 && r() < 0.6) out.crack = { x: (r() - 0.5) * (len - 1.5), y: 0.7 + r() * 0.9, face: r() < 0.5 ? 1 : -1, rot: r() * 6, s: 1.2 + r() * 0.8 }
    return out
  })
}

// Jagged outline around (x, y): an irregular polygon, deterministic per seed.
function jagged({ x, y, rx, ry, seed }) {
  const r = rng(seed)
  const n = 14
  return Array.from({ length: n }, (_, k) => {
    const a = (k / n) * Math.PI * 2
    const f = 0.65 + r() * 0.5
    return new THREE.Vector2(x + Math.cos(a) * rx * f, y + Math.sin(a) * ry * f)
  })
}

// Extruded wall with holes. Shape x runs along the wall (centered), y up; UVs come out in
// meters, so the textures get repeat = 1 / tile size.
export function holedWallGeometry(L, thick, damage) {
  const shape = new THREE.Shape()
  shape.moveTo(-L / 2, 0)
  shape.lineTo(L / 2, 0)
  shape.lineTo(L / 2, WALL_H)
  shape.lineTo(-L / 2, WALL_H)
  shape.lineTo(-L / 2, 0)
  for (const win of damage.windows) {
    const h = new THREE.Path()
    h.moveTo(win.x - WIN.w / 2, WIN.y0)
    h.lineTo(win.x - WIN.w / 2, WIN.y1)
    h.lineTo(win.x + WIN.w / 2, WIN.y1)
    h.lineTo(win.x + WIN.w / 2, WIN.y0)
    h.lineTo(win.x - WIN.w / 2, WIN.y0)
    shape.holes.push(h)
  }
  for (const b of damage.breaches) shape.holes.push(new THREE.Path(jagged(b).reverse()))
  const g = new THREE.ExtrudeGeometry(shape, { depth: thick, bevelEnabled: false, curveSegments: 1 })
  g.translate(0, 0, -thick / 2)
  return g
}

let shared = null
function mats() {
  if (shared) return shared
  const t = materials()
  shared = {
    frame: new THREE.MeshStandardMaterial({ color: '#2b3036', metalness: 0.6, roughness: 0.45 }),
    glass: new THREE.MeshStandardMaterial({ color: '#16222c', metalness: 0.9, roughness: 0.06, transparent: true, opacity: 0.55 }),
    shard: new THREE.MeshStandardMaterial({ color: '#9fb4c0', metalness: 0.8, roughness: 0.1, transparent: true, opacity: 0.7, side: THREE.DoubleSide }),
    rock: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 0.6, 0.6), color: '#b0a89d', roughness: 0.95, flatShading: true }),
    crack: new THREE.MeshStandardMaterial({ map: t.cracks, transparent: true, depthWrite: false, roughness: 1, polygonOffset: true, polygonOffsetFactor: -2 }),
    rebar: new THREE.MeshStandardMaterial({ color: '#7c3f1d', metalness: 0.6, roughness: 0.75 }),
    steel: new THREE.MeshStandardMaterial({ color: '#5b626b', metalness: 0.75, roughness: 0.5 }),
    cable: new THREE.MeshStandardMaterial({ color: '#111315', roughness: 0.6 }),
    lamp: new THREE.MeshStandardMaterial({ color: '#f1f5f9', emissive: '#e0f2fe', emissiveIntensity: 1.6, toneMapped: false }),
    lampOff: new THREE.MeshStandardMaterial({ color: '#cbd5e1', roughness: 0.4 }),
    slab: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 3, 3), color: '#a8a39b', roughness: 0.92 }),
    slabUnder: new THREE.MeshStandardMaterial({ color: '#77736d', roughness: 0.95 }),
  }
  return shared
}

const SHARD = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0.3, 1, 0], 3))
SHARD.computeVertexNormals()

// Frames, glass, shards and breach rubble for one wall, in its local frame.
export function WallDetails({ damage, thick }) {
  const M = mats()
  const items = useMemo(() => {
    const out = []
    for (const win of damage.windows) {
      const r = rng(win.seed)
      const cx = win.x
      const cy = (WIN.y0 + WIN.y1) / 2
      out.push({ k: `f${cx}`, m: M.frame, box: [WIN.w + 0.08, 0.06, thick + 0.04], p: [cx, WIN.y0, 0] })
      out.push({ k: `t${cx}`, m: M.frame, box: [WIN.w + 0.08, 0.05, thick + 0.02], p: [cx, WIN.y1, 0] })
      out.push({ k: `m${cx}`, m: M.frame, box: [0.04, WIN.y1 - WIN.y0, 0.05], p: [cx, cy, 0] })
      if (!win.broken) {
        out.push({ k: `g${cx}`, m: M.glass, box: [WIN.w, WIN.y1 - WIN.y0, 0.01], p: [cx, cy, 0] })
      } else {
        // what is left of the pane: shards still stuck in the frame corners
        for (let s = 0; s < 4; s++) {
          const left = s % 2 === 0
          const top = s > 1
          out.push({ k: `s${cx}${s}`, m: M.shard, shard: true,
            p: [cx + (left ? -WIN.w / 2 : WIN.w / 2), top ? WIN.y1 : WIN.y0, 0],
            r: [0, 0, (left ? 0 : Math.PI) * (top ? -1 : 1) + (top ? -Math.PI / 2 : 0) + (r() - 0.5) * 0.4],
            sc: [0.25 + r() * 0.3, 0.2 + r() * 0.35, 1] })
        }
      }
    }
    for (const b of damage.breaches) {
      // broken blocks that fell out of the hole, piled against both faces
      const r = rng(b.seed + 1)
      for (let k = 0; k < 10; k++) {
        const side = k % 2 ? 1 : -1
        const s = 0.08 + r() * 0.14
        out.push({ k: `b${b.x}${k}`, m: M.rock, box: [s * 1.6, s, s * 1.2],
          p: [b.x + (r() - 0.5) * b.rx * 1.6, s / 2 + (k > 6 ? s : 0), side * (thick / 2 + 0.06 + r() * 0.35)],
          r: [r(), r() * 3, r()] })
      }
    }
    return out
  }, [damage, thick, M])
  return (
    <group>
      {items.map((it) => (
        <mesh key={it.k} position={it.p} rotation={it.r} scale={it.sc} material={it.m} castShadow={!it.shard} receiveShadow
              geometry={it.shard ? SHARD : undefined}>
          {!it.shard && <boxGeometry args={it.box} />}
        </mesh>
      ))}
      {damage.crack && (
        <mesh position={[damage.crack.x, damage.crack.y, damage.crack.face * (thick / 2 + 0.004)]}
              rotation={[0, damage.crack.face > 0 ? 0 : Math.PI, damage.crack.rot]} material={M.crack}>
          <planeGeometry args={[damage.crack.s, damage.crack.s]} />
        </mesh>
      )}
    </group>
  )
}

// --------------------------------------------------------------- roof and beams
// A slab of roof still standing over each hazard zone (robots never go there, so it can't
// hide anything they do), broken off along a ragged edge with rebar hanging out of it.
function RoofPiece({ hazard }) {
  const M = mats()
  const xs = hazard.poly.map((p) => p[0])
  const ys = hazard.poly.map((p) => p[1])
  const [x0, x1, y0, y1] = [Math.min(...xs) - 0.3, Math.max(...xs) + 0.3, Math.min(...ys) - 0.3, Math.max(...ys) + 0.3]
  const { geom, bars } = useMemo(() => {
    const r = rng(hash(x0, y0, x1, y1))
    const reach = (y1 - y0) * 0.4 // the roof survives over the southern 40 %
    const shape = new THREE.Shape()
    shape.moveTo(x0, y0)
    shape.lineTo(x1, y0)
    // broken edge: a wandering line with the odd bite taken out of it
    const edge = []
    const n = 46
    let wander = 0
    for (let k = 0; k <= n; k++) {
      const x = x1 - (k / n) * (x1 - x0)
      wander = Math.max(-0.3, Math.min(0.3, wander + (r() - 0.5) * 0.18))
      const bite = r() < 0.08 ? -0.25 - r() * 0.2 : 0
      const y = y0 + reach * (0.85 + wander + bite) + (r() - 0.5) * 0.12
      edge.push([x, y])
      shape.lineTo(x, y)
    }
    shape.lineTo(x0, y0)
    const g = new THREE.ExtrudeGeometry(shape, { depth: 0.24, bevelEnabled: false })
    g.rotateX(-Math.PI / 2) // shape (x, y) -> world (x, -z); extrusion goes up
    const bars = []
    for (let k = 0; k < edge.length - 1; k++) {
      const [ex, ey] = edge[k]
      for (let b = 0; b < (k % 2 ? 1 : 0) + (r() < 0.5 ? 1 : 0); b++) {
        bars.push({ p: [ex + (r() - 0.5) * 0.4, WALL_H - 0.25 - r() * 0.2, -(ey + 0.05)],
          r: [(r() - 0.5) * 0.6, 0, (r() - 0.5) * 0.6], len: 0.4 + r() * 0.7 })
      }
    }
    return { geom: g, bars }
  }, [x0, x1, y0, y1])
  return (
    <group>
      <mesh geometry={geom} position={[0, WALL_H + 0.024, 0]} material={M.slab} castShadow receiveShadow />
      {bars.map((b, i) => (
        <mesh key={i} position={b.p} rotation={b.r} material={M.rebar}>
          <cylinderGeometry args={[0.012, 0.012, b.len, 5]} />
        </mesh>
      ))}
    </group>
  )
}

// I-beam between two points (world coords, three.js frame).
function Beam({ a, b, M }) {
  const A = new THREE.Vector3(...a)
  const B = new THREE.Vector3(...b)
  const mid = A.clone().add(B).multiplyScalar(0.5)
  const len = A.distanceTo(B)
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(1, 0, 0), B.clone().sub(A).normalize())
  return (
    <group position={mid} quaternion={q}>
      <mesh material={M.steel} castShadow><boxGeometry args={[len, 0.22, 0.025]} /></mesh>
      <mesh material={M.steel} position={[0, 0.11, 0]} castShadow><boxGeometry args={[len, 0.025, 0.14]} /></mesh>
      <mesh material={M.steel} position={[0, -0.11, 0]} castShadow><boxGeometry args={[len, 0.025, 0.14]} /></mesh>
    </group>
  )
}

// One beam across the short side of every other room; some sag in the middle with a light
// fitting dangling from a cable (still lit on some, dead on others).
function Beams({ rooms }) {
  const M = mats()
  const beams = useMemo(() => rooms.filter((_, i) => i % 2 === 0).map((room) => {
    const xs = room.poly.map((p) => p[0])
    const ys = room.poly.map((p) => p[1])
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
    const r = rng(hash(x0, y0, x1, y1, 5))
    const alongX = x1 - x0 < y1 - y0 // span the short way
    const t = 0.35 + r() * 0.3
    const top = WALL_H - 0.12
    const a = alongX ? [x0, y0 + (y1 - y0) * t] : [x0 + (x1 - x0) * t, y0]
    const b = alongX ? [x1, a[1]] : [a[0], y1]
    const sag = r() < 0.55 ? 0.45 + r() * 0.4 : 0
    const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
    return { a, b, m, sag, top, lit: r() < 0.5, swing: r() * 6, key: room.id }
  }), [rooms])
  return beams.map((bm) => {
    const A = w2t(bm.a[0], bm.a[1], bm.top)
    const B = w2t(bm.b[0], bm.b[1], bm.top)
    const Mid = w2t(bm.m[0], bm.m[1], bm.top - bm.sag)
    return (
      <group key={bm.key}>
        {bm.sag ? (<><Beam a={A} b={Mid} M={M} /><Beam a={Mid} b={B} M={M} /></>) : <Beam a={A} b={B} M={M} />}
        {bm.sag > 0 && <Fixture at={Mid} lit={bm.lit} phase={bm.swing} M={M} />}
      </group>
    )
  })
}

// Fluorescent fitting hanging on its cable, swinging a little; a lit one flickers.
function Fixture({ at, lit, phase, M }) {
  const g = useRef()
  const lamp = useRef()
  const glow = useRef()
  const night = useSim((s) => s.night)
  useFrame(({ clock }) => {
    const t = clock.elapsedTime + phase
    if (g.current) g.current.rotation.z = Math.sin(t * 0.9) * 0.08
    const off = Math.sin(t * 23) > 0.85 || Math.sin(t * 3.1) > 0.97
    if (lamp.current && lit) lamp.current.material.emissiveIntensity = off ? 0.2 : 1.6
    if (glow.current) glow.current.intensity = off ? 0.3 : 6
  })
  const drop = 0.9
  return (
    <group ref={g} position={at}>
      <mesh position={[0, -drop / 2, 0]} material={M.cable}><cylinderGeometry args={[0.008, 0.008, drop, 5]} /></mesh>
      <group position={[0, -drop - 0.03, 0]} rotation={[0.5, 0.2, 0.9]}>
        <mesh material={M.frame}><boxGeometry args={[1.2, 0.05, 0.18]} /></mesh>
        <mesh ref={lamp} position={[0, -0.035, 0]} material={lit ? M.lamp.clone() : M.lampOff}>
          <cylinderGeometry args={[0.025, 0.025, 1.12, 8]} />
        </mesh>
      </group>
      {night && lit && (
        <>
          <pointLight ref={glow} position={[0, -drop - 0.2, 0]} color="#e6f4ff" distance={6} decay={1.6} />
          <group position={[0, -drop - 0.05, 0]}><LightBeam length={WALL_H - 0.4} radius={1.1} color="#e8f6ff" opacity={0.1} /></group>
        </>
      )}
    </group>
  )
}

// --------------------------------------------------------------- floor cracks and dust
function FloorCracks({ rooms }) {
  const M = mats()
  const items = useMemo(() => rooms.flatMap((room) => {
    const xs = room.poly.map((p) => p[0])
    const ys = room.poly.map((p) => p[1])
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
    const r = rng(hash(x0, y0, 11))
    const n = Math.max(1, Math.round(((x1 - x0) * (y1 - y0)) / 50))
    return Array.from({ length: n }, (_, k) => ({ key: `${room.id}${k}`,
      p: [x0 + 1 + r() * (x1 - x0 - 2), y0 + 1 + r() * (y1 - y0 - 2)], rot: r() * 6, s: 1.8 + r() * 1.6 }))
  }), [rooms])
  return items.map((c) => (
    <mesh key={c.key} rotation={[-Math.PI / 2, 0, c.rot]} position={w2t(c.p[0], c.p[1], 0.009)} material={M.crack}>
      <planeGeometry args={[c.s, c.s]} />
    </mesh>
  ))
}

// Dust hanging in the air after the collapse, drifting slowly.
function AirborneDust({ W, H, count = 700 }) {
  const ref = useRef()
  const { geom, seeds } = useMemo(() => {
    const r = rng(77)
    const pos = new Float32Array(count * 3)
    const seeds = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      pos[i * 3] = r() * W
      pos[i * 3 + 1] = 0.2 + r() * (WALL_H + 0.4)
      pos[i * 3 + 2] = -r() * H
      seeds[i] = r() * 100
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    return { geom: g, seeds }
  }, [W, H, count])
  useFrame((_, dt) => {
    const p = geom.attributes.position
    const t = performance.now() / 1000
    for (let i = 0; i < count; i++) {
      const s = seeds[i]
      p.array[i * 3] += Math.sin(t * 0.13 + s) * dt * 0.05
      p.array[i * 3 + 1] += Math.cos(t * 0.17 + s) * dt * 0.03
      p.array[i * 3 + 2] += Math.sin(t * 0.11 + s * 1.3) * dt * 0.05
    }
    p.needsUpdate = true
  })
  return (
    <points ref={ref} geometry={geom}>
      <pointsMaterial map={materials().puff} color="#d6cbb8" size={0.07} sizeAttenuation transparent opacity={0.4}
                      depthWrite={false} />
    </points>
  )
}

// Static damage (merged with the other props) and the moving parts.
export function CollapseStatic({ fp }) {
  return (
    <group>
      {(fp.hazards ?? []).map((hz) => <RoofPiece key={hz.id} hazard={hz} />)}
      <FloorCracks rooms={fp.rooms ?? []} />
    </group>
  )
}

export function CollapseLive({ fp, dust = true }) {
  const [W, H] = fp.size
  return (
    <group>
      <Beams rooms={fp.rooms ?? []} />
      {dust && <AirborneDust W={W} H={H} />}
    </group>
  )
}
