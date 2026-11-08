import { useLayoutEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { w2t } from './util'
import { materials, tiledSet } from './textures'
import { chunks } from './Debris'

// The whole site as a disaster zone, not a tidy building with a few piles:
//  - every floor is littered with broken concrete, ceiling-tile fragments and dust
//  - debris is heaped against the walls, with fallen ceiling boards leaning on them
//  - outside: the neighbouring buildings came down (wall stubs, a rubble mound, pancaked
//    slabs, beams), the lot is cracked and heaved with debris thrown across it, cars are
//    crushed, a utility pole is down, and smoke rises from the ruins with a fire in one.
// Visual only and Reality only: the truth grid, radio and robots never see any of it. Inside
// the building it stays low (robots drive over litter) or hugs the walls, so it never sits
// where a robot's path goes. Deterministic from the floorplan.

function rng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}

const box = (poly) => {
  const xs = poly.map((p) => p[0])
  const ys = poly.map((p) => p[1])
  return [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
}

let M = null
function mats() {
  if (M) return M
  const t = materials()
  M = {
    rock: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 0.6, 0.6), color: '#b3aca2', roughness: 0.95, flatShading: true }),
    darkRock: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 0.6, 0.6), color: '#7d766d', roughness: 0.97, flatShading: true }),
    brick: new THREE.MeshStandardMaterial({ ...tiledSet(t.brick, 0.5, 0.5), color: '#c9a99a', roughness: 0.92, flatShading: true }),
    tile: new THREE.MeshStandardMaterial({ color: '#8f8a80', roughness: 0.95 }),
    board: new THREE.MeshStandardMaterial({ color: '#cfc9bd', roughness: 0.92 }),
    slab: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 2, 2), color: '#a39d94', roughness: 0.93 }),
    steel: new THREE.MeshStandardMaterial({ color: '#4f565e', metalness: 0.75, roughness: 0.55 }),
    rust: new THREE.MeshStandardMaterial({ color: '#7c3f1d', metalness: 0.55, roughness: 0.8 }),
    asphalt: new THREE.MeshStandardMaterial({ ...tiledSet(t.asphalt, 1, 1), color: '#6d7177', roughness: 0.95 }),
    dust: new THREE.MeshStandardMaterial({ map: t.dust, transparent: true, depthWrite: false, roughness: 1, color: '#b8ab98' }),
    crack: new THREE.MeshStandardMaterial({ map: t.cracks, transparent: true, depthWrite: false, roughness: 1, polygonOffset: true, polygonOffsetFactor: -2 }),
    carRed: new THREE.MeshStandardMaterial({ color: '#7f1d1d', metalness: 0.6, roughness: 0.4 }),
    carGrey: new THREE.MeshStandardMaterial({ color: '#52606d', metalness: 0.6, roughness: 0.45 }),
    glass: new THREE.MeshStandardMaterial({ color: '#0d151c', metalness: 0.9, roughness: 0.1 }),
    tyre: new THREE.MeshStandardMaterial({ color: '#111214', roughness: 0.85 }),
    wood: new THREE.MeshStandardMaterial({ color: '#5b4632', roughness: 0.85 }),
    cable: new THREE.MeshStandardMaterial({ color: '#0d0e10', roughness: 0.7 }),
  }
  return M
}

// One instanced mesh per (geometry, material) bucket: thousands of pieces, a few draw calls.
function Instances({ geom, material, items, shadow = false }) {
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
      if (it.shade != null) ref.current.setColorAt(i, c.setScalar(it.shade))
    })
    ref.current.instanceMatrix.needsUpdate = true
    if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true
  }, [items])
  if (!items.length) return null
  return <instancedMesh ref={ref} args={[geom, material, items.length]} castShadow={shadow} receiveShadow />
}

const BOX = new THREE.BoxGeometry(1, 1, 1)

// --------------------------------------------------------------- inside
function layoutInside(fp) {
  const rocks = [[], [], [], [], []]
  const tiles = []
  const boards = []
  const dust = []
  const r = rng(9001)
  const push = (x, y, s, h, shade = 0.65 + r() * 0.35) => rocks[Math.floor(r() * 5)].push({
    pos: w2t(x, y, h), rot: [r() * 6, r() * 6, r() * 6], scale: [s * (0.7 + r() * 0.6), s * (0.5 + r() * 0.5), s * (0.7 + r() * 0.6)], shade,
  })
  // litter across every room floor: low enough to drive over
  for (const room of fp.rooms ?? []) {
    const [x0, x1, y0, y1] = box(room.poly)
    const area = (x1 - x0) * (y1 - y0)
    for (let i = 0; i < area * 5; i++) {
      const s = 0.025 + r() ** 2 * 0.08
      push(x0 + 0.2 + r() * (x1 - x0 - 0.4), y0 + 0.2 + r() * (y1 - y0 - 0.4), s, s * 0.25)
    }
    for (let i = 0; i < area * 0.25; i++) {
      const w = 0.1 + r() * 0.22
      tiles.push({ pos: w2t(x0 + 0.3 + r() * (x1 - x0 - 0.6), y0 + 0.3 + r() * (y1 - y0 - 0.6), 0.012 + r() * 0.02),
        rot: [(r() - 0.5) * 0.3, r() * 6, (r() - 0.5) * 0.3], scale: [w, 0.012, w * (0.5 + r() * 0.5)], shade: 0.75 + r() * 0.25 })
    }
    for (let i = 0; i < Math.max(2, area / 25); i++) {
      dust.push({ x: x0 + 1 + r() * (x1 - x0 - 2), y: y0 + 1 + r() * (y1 - y0 - 2), s: 2 + r() * 3, rot: r() * 6 })
    }
  }
  // the no-go hazard zones took the worst of it (robots never enter, so they can be full):
  // a mound under the missing part of the roof, slabs and boards thrown on top
  for (const hz of fp.hazards ?? []) {
    const [x0, x1, y0, y1] = box(hz.poly)
    const cy = y0 + (y1 - y0) * 0.72
    const hx = (x1 - x0) / 2 - 0.4
    const hy = (y1 - y0) * 0.25
    const cx = (x0 + x1) / 2
    for (let i = 0; i < hx * hy * 40; i++) {
      const u = (r() * 2 - 1)
      const v = (r() * 2 - 1)
      const d = Math.min(1, Math.hypot(u, v * 0.8))
      const s = (0.08 + r() * 0.3) * (1.1 - d * 0.6)
      push(cx + u * hx, cy + v * hy, s, Math.max(s * 0.3, (1 - d * d) * 1.4 * (0.4 + r() * 0.6)))
    }
    for (let i = 0; i < 6; i++) {
      boards.push({ pos: w2t(cx + (r() - 0.5) * hx * 1.6, cy + (r() - 0.5) * hy * 1.4, 0.5 + r() * 0.6),
        rot: [0, r() * 6, 0], lean: (r() - 0.5) * 1.2, scale: [1.4 + r(), 1.1, 0.12], shade: 0.7 })
    }
  }
  // heaps against the walls, and ceiling boards leaning on them
  fp.walls.forEach((w) => {
    if (w.material === 'metal') return
    const [ax, ay] = w.a
    const [bx, by] = w.b
    const len = Math.hypot(bx - ax, by - ay)
    const ux = (bx - ax) / len
    const uy = (by - ay) / len
    const half = { concrete: 0.15, brick: 0.1, drywall: 0.06 }[w.material] ?? 0.1
    for (const side of [-1, 1]) {
      const nx = -uy * side
      const ny = ux * side
      for (let t = 0.7; t < len - 0.7; t += 1.6) {
        if (r() > 0.42) continue
        const cx = ax + ux * t
        const cy = ay + uy * t
        const n = 10 + Math.floor(r() * 14)
        for (let k = 0; k < n; k++) {
          const d = r() * 0.42 // out from the wall face
          const along = (r() - 0.5) * 1.3
          const s = (0.05 + r() * 0.13) * (1 - d * 0.9)
          const px = cx + ux * along + nx * (half + 0.03 + d)
          const py = cy + uy * along + ny * (half + 0.03 + d)
          push(px, py, s, Math.max(s * 0.3, (0.42 - d) * 0.55 * r()))
        }
        if (r() < 0.22) {
          const lean = 0.25 + r() * 0.25
          boards.push({ pos: w2t(cx + nx * (half + 0.22), cy + ny * (half + 0.22), 0.62),
            rot: [0, Math.atan2(uy, ux), 0], lean: lean * side, scale: [0.9 + r() * 0.5, 1.3, 0.02], shade: 0.8 + r() * 0.2 })
        }
      }
    }
  })
  return { rocks, tiles, boards, dust }
}

function Inside({ fp }) {
  const L = useMemo(() => layoutInside(fp), [fp])
  const m = mats()
  const geoms = chunks()
  return (
    <group>
      {L.rocks.map((items, k) => <Instances key={k} geom={geoms[k]} material={k % 2 ? m.darkRock : m.rock} items={items} />)}
      <Instances geom={BOX} material={m.tile} items={L.tiles} />
      {L.boards.map((b, i) => (
        // a ceiling board leaning against the wall
        <group key={i} position={b.pos} rotation={b.rot}>
          <mesh rotation={[b.lean, 0, 0]} scale={b.scale} geometry={BOX} material={m.board} castShadow receiveShadow />
        </group>
      ))}
      {L.dust.map((d, i) => (
        <mesh key={i} rotation={[-Math.PI / 2, 0, d.rot]} position={w2t(d.x, d.y, 0.007)} material={m.dust}>
          <planeGeometry args={[d.s, d.s]} />
        </mesh>
      ))}
    </group>
  )
}

// --------------------------------------------------------------- outside
// Footprints for collapsed neighbours, placed off the building's north and east sides.
function neighbours(W, H) {
  return [
    { x0: 3, x1: 27, y0: H + 4, y1: H + 13, top: 2.6 },
    { x0: W + 5, x1: W + 13, y0: 2, y1: 22, top: 2.2 },
  ]
}

function jaggedWall(len, h, seed) {
  const r = rng(seed)
  const s = new THREE.Shape()
  s.moveTo(-len / 2, 0)
  s.lineTo(len / 2, 0)
  const n = Math.max(4, Math.round(len * 1.6))
  for (let k = 0; k <= n; k++) {
    const x = len / 2 - (k / n) * len
    s.lineTo(x, Math.max(0.3, h * (0.35 + r() * 0.65)))
  }
  s.lineTo(-len / 2, 0)
  return new THREE.ExtrudeGeometry(s, { depth: 0.3, bevelEnabled: false })
}

function layoutOutside(fp) {
  const [W, H] = fp.size
  const r = rng(424242)
  const rocks = [[], [], [], [], []]
  const slabs = []
  const beams = []
  const stubs = []
  const plates = []
  const cracks = []
  const smoke = []
  const push = (x, y, s, h, shade = 0.55 + r() * 0.4) => rocks[Math.floor(r() * 5)].push({
    pos: w2t(x, y, h), rot: [r() * 6, r() * 6, r() * 6], scale: [s * (0.7 + r() * 0.6), s * (0.6 + r() * 0.5), s * (0.7 + r() * 0.6)], shade,
  })
  for (const nb of neighbours(W, H)) {
    const cx = (nb.x0 + nb.x1) / 2
    const cy = (nb.y0 + nb.y1) / 2
    const hx = (nb.x1 - nb.x0) / 2
    const hy = (nb.y1 - nb.y0) / 2
    // the mound: high in the middle, spilling past the old footprint
    const n = Math.round(hx * hy * 9)
    for (let i = 0; i < n; i++) {
      const u = (r() * 2 - 1) * 1.15
      const v = (r() * 2 - 1) * 1.15
      const d = Math.min(1, Math.hypot(u, v) / 1.3)
      const s = (0.15 + r() * 0.55) * (1.1 - d * 0.6)
      push(cx + u * hx, cy + v * hy, s, Math.max(s * 0.3, (1 - d * d) * nb.top * (0.4 + r() * 0.6)))
    }
    // pancaked floor slabs
    for (let i = 0; i < 9; i++) {
      slabs.push({ pos: w2t(cx + (r() - 0.5) * hx * 1.5, cy + (r() - 0.5) * hy * 1.5, 0.4 + r() * nb.top * 0.7),
        rot: [(r() - 0.5) * 0.9, r() * 6, (r() - 0.5) * 0.9], scale: [2 + r() * 2.5, 0.22, 1.5 + r() * 2] })
    }
    for (let i = 0; i < 5; i++) {
      beams.push({ pos: w2t(cx + (r() - 0.5) * hx * 1.4, cy + (r() - 0.5) * hy * 1.4, 0.6 + r() * nb.top * 0.6),
        rot: [(r() - 0.5) * 0.5, r() * 6, (r() - 0.5) * 0.8], len: 3 + r() * 4 })
    }
    // what is left of the walls: jagged stubs along the old footprint edges
    const edges = [[[nb.x0, nb.y0], [nb.x1, nb.y0]], [[nb.x1, nb.y0], [nb.x1, nb.y1]], [[nb.x1, nb.y1], [nb.x0, nb.y1]], [[nb.x0, nb.y1], [nb.x0, nb.y0]]]
    edges.forEach(([a, b], k) => {
      const len = Math.hypot(b[0] - a[0], b[1] - a[1])
      for (let t = 0; t < len; t += 3 + r() * 3) {
        if (r() < 0.35) continue
        const seg = 1.5 + r() * 3
        const f = (t + seg / 2) / len
        if (f > 1) break
        stubs.push({ pos: w2t(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, 0), ang: Math.atan2(b[1] - a[1], b[0] - a[0]),
          len: seg, h: 1 + r() * 3.2, seed: Math.floor(r() * 1e6) + k })
      }
    })
    smoke.push({ x: cx + (r() - 0.5) * hx, y: cy + (r() - 0.5) * hy, h: nb.top, fire: smoke.length === 0 })
  }
  // debris thrown across the lot and the street, clear of the truck and the entrance
  const [tcx, tcy] = fp.command_post.pos
  const truck = (x, y) => Math.abs(x - tcx) < 6 && Math.abs(y - tcy) < 6
  for (let i = 0; i < 900; i++) {
    const x = -16 + r() * (W + 30)
    const y = -6 + r() * (H + 10)
    const inside = x > -0.5 && x < W + 0.5 && y > -0.5 && y < H + 0.5
    if (inside || truck(x, y)) continue
    const s = 0.04 + r() ** 2.5 * 0.35
    push(x, y, s, s * 0.25)
  }
  // heaved asphalt along a fissure across the lot, and big ground cracks
  for (let i = 0; i < 9; i++) {
    const t = i / 8
    const x = -14 + t * 10
    const y = -4 + t * 6 + (r() - 0.5)
    plates.push({ pos: w2t(x, y, 0.08), rot: [(r() - 0.5) * 0.35, r() * 0.6, (r() - 0.5) * 0.35], scale: [1.6 + r(), 0.12, 1.1 + r() * 0.6] })
  }
  for (let i = 0; i < 14; i++) {
    let x
    let y
    do { x = -15 + r() * (W + 28); y = -6 + r() * (H + 10) } while ((x > -1 && x < W + 1 && y > -1 && y < H + 1) || truck(x, y))
    cracks.push({ x, y, s: 3 + r() * 4, rot: r() * 6 })
  }
  return { rocks, slabs, beams, stubs, plates, cracks, smoke }
}

function Car({ pos, rot, M: m, paint, crushed = 0 }) {
  return (
    <group position={pos} rotation={rot}>
      <mesh material={paint} position={[0, 0.55, 0]} castShadow receiveShadow><boxGeometry args={[4.2, 0.6, 1.75]} /></mesh>
      <mesh material={paint} position={[-0.2, 1.05 - crushed, 0]} rotation={[0, 0, crushed * 0.3]} castShadow><boxGeometry args={[2.2, 0.5 - crushed * 0.4, 1.6]} /></mesh>
      <mesh material={m.glass} position={[0.95, 1.0 - crushed * 0.6, 0]} rotation={[0, 0, -0.6]}><boxGeometry args={[0.04, 0.5, 1.5]} /></mesh>
      {[[-1.35, 0.85], [1.35, 0.85], [-1.35, -0.85], [1.35, -0.85]].map(([x, z]) => (
        <mesh key={`${x}${z}`} material={m.tyre} position={[x, 0.33, z]} rotation={[Math.PI / 2, 0, 0]} castShadow>
          <cylinderGeometry args={[0.33, 0.33, 0.24, 14]} />
        </mesh>
      ))}
    </group>
  )
}

function Outside({ fp }) {
  const L = useMemo(() => layoutOutside(fp), [fp])
  const m = mats()
  const geoms = chunks()
  const stubGeoms = useMemo(() => L.stubs.map((s) => jaggedWall(s.len, s.h, s.seed)), [L])
  const [W, H] = fp.size
  return (
    <group>
      {L.rocks.map((items, k) => <Instances key={k} geom={geoms[k]} material={[m.rock, m.darkRock, m.brick, m.rock, m.darkRock][k]} items={items} shadow />)}
      <Instances geom={BOX} material={m.slab} items={L.slabs} shadow />
      <Instances geom={BOX} material={m.asphalt} items={L.plates} shadow />
      {L.beams.map((b, i) => (
        <group key={i} position={b.pos} rotation={b.rot}>
          <mesh material={m.steel} castShadow><boxGeometry args={[b.len, 0.3, 0.03]} /></mesh>
          <mesh material={m.steel} position={[0, 0.15, 0]}><boxGeometry args={[b.len, 0.03, 0.18]} /></mesh>
          <mesh material={m.steel} position={[0, -0.15, 0]}><boxGeometry args={[b.len, 0.03, 0.18]} /></mesh>
        </group>
      ))}
      {L.stubs.map((s, i) => (
        <group key={i} position={s.pos} rotation={[0, s.ang, 0]}>
          <mesh geometry={stubGeoms[i]} position={[0, 0, -0.15]} material={i % 3 ? m.slab : m.brick} castShadow receiveShadow />
        </group>
      ))}
      {L.cracks.map((c, i) => (
        <mesh key={i} rotation={[-Math.PI / 2, 0, c.rot]} position={w2t(c.x, c.y, 0.004)} material={m.crack}>
          <planeGeometry args={[c.s, c.s]} />
        </mesh>
      ))}
      <Car pos={w2t(-11, 3.5, 0)} rot={[0, 0.5, 0]} M={m} paint={m.carRed} crushed={0.35} />
      <Car pos={w2t(-10.5, 27, 0.05)} rot={[0.08, -0.3, 0.12]} M={m} paint={m.carGrey} crushed={0.1} />
      <Car pos={w2t(W + 3.2, H + 2.5, 0)} rot={[0, 2.2, 0]} M={m} paint={m.carGrey} crushed={0.45} />
      {/* utility pole down across the street, wires trailing */}
      <group position={w2t(-13.5, 31, 0.2)} rotation={[0, 0.55, Math.PI / 2 - 0.06]}>
        <mesh material={m.wood} position={[0, -4.5, 0]} castShadow><cylinderGeometry args={[0.13, 0.17, 9, 10]} /></mesh>
        <mesh material={m.wood} position={[0, -8.6, 0]}><boxGeometry args={[0.12, 0.12, 1.8]} /></mesh>
      </group>
      {[0.6, -0.6].map((z) => (
        <mesh key={z} material={m.cable} position={w2t(-7.5, 28.5 + z, 0.05)} rotation={[Math.PI / 2, 0, 0.6]}>
          <cylinderGeometry args={[0.012, 0.012, 9, 4]} />
        </mesh>
      ))}
      {/* dust thrown over everything around the walls */}
      {[[W / 2, -2.5, 14], [-2.5, H / 2, 10], [W + 2.5, H / 2, 12], [W / 2, H + 2.5, 14]].map(([x, y, s], i) => (
        <mesh key={i} rotation={[-Math.PI / 2, 0, i]} position={w2t(x, y, 0.006)} material={m.dust}>
          <planeGeometry args={[s, s * 0.6]} />
        </mesh>
      ))}
    </group>
  )
}

// --------------------------------------------------------------- smoke and fire
function Plume({ x, y, h, fire }) {
  const group = useRef()
  const light = useRef()
  const N = 14
  const seeds = useMemo(() => Array.from({ length: N }, (_, i) => ({ ph: i / N, dx: (Math.sin(i * 12.9) * 0.5), s: 2 + (i % 4) * 0.6 })), [])
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    group.current?.children.forEach((sp, i) => {
      const p = seeds[i]
      const k = (t * 0.06 + p.ph) % 1
      sp.position.set(x + p.dx + k * 3, h + k * 14, -(y + k * 1.5))
      sp.scale.setScalar(p.s * (0.6 + k * 2.4))
      sp.material.opacity = 0.22 * Math.sin(Math.PI * k)
    })
    if (light.current) light.current.intensity = 12 + Math.sin(t * 13) * 3 + Math.sin(t * 7.3) * 4
  })
  return (
    <group>
      <group ref={group}>
        {seeds.map((p, i) => (
          <sprite key={i}>
            <spriteMaterial map={materials().puff} color={fire ? '#3b3632' : '#6b6560'} transparent opacity={0} depthWrite={false} />
          </sprite>
        ))}
      </group>
      {fire && (
        <>
          <pointLight ref={light} position={w2t(x, y, h + 0.8)} color="#ff7a1a" distance={16} decay={1.5} />
          {[0, 1, 2, 3, 4].map((i) => (
            <sprite key={i} position={w2t(x + (i - 2) * 0.35, y + ((i * 7) % 3 - 1) * 0.3, h + 0.3 + (i % 2) * 0.3)} scale={[1.1, 1.5, 1]}>
              <spriteMaterial map={materials().puff} color="#ff8a24" transparent opacity={0.85} depthWrite={false}
                              blending={THREE.AdditiveBlending} toneMapped={false} />
            </sprite>
          ))}
        </>
      )}
    </group>
  )
}

export function DisasterStatic({ fp }) {
  return (
    <group>
      <Inside fp={fp} />
      <Outside fp={fp} />
    </group>
  )
}

export function DisasterLive({ fp }) {
  const [W, H] = fp.size
  return neighbours(W, H).map((nb, i) => (
    <Plume key={i} x={(nb.x0 + nb.x1) / 2 + (i ? 1 : -3)} y={(nb.y0 + nb.y1) / 2} h={nb.top} fire={i === 0} />
  ))
}

