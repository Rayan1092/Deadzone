import { useMemo } from 'react'
import * as THREE from 'three'
import { WALL_H, w2t } from './util'
import { materials, tiledSet } from './textures'

// The exterior shell: what tells you this was a bigger building. On top of the ground
// floor's outer walls stand the stubs of an upper storey (jagged brick and concrete, tallest
// at the far corners so the camera's view into the rooms from the south-west stays open), a
// floor slab lip where the upper floor sheared off, one pancaked upper slab hanging off the
// north-west corner onto the ruins outside, window frames still in the stubs, and a street
// west of the lot. Visual only, outside the footprint or above WALL_H: the simulated ground
// floor never changes. Derived from fp.size, so generated buildings get it too.

function rng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}

let M = null
function mats() {
  if (M) return M
  const t = materials()
  M = {
    brick: new THREE.MeshStandardMaterial({ ...tiledSet(t.brick, 0.5, 0.5), color: '#c4b8ae', roughness: 0.93 }),
    concrete: new THREE.MeshStandardMaterial({ ...tiledSet(t.concrete, 0.5, 0.5), color: '#b9b6b0', roughness: 0.9 }),
    cut: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 0.7, 0.7), color: '#c6c0b6', roughness: 1 }),
    slab: new THREE.MeshStandardMaterial({ ...tiledSet(t.rubble, 0.4, 0.4), color: '#cbc5bb', roughness: 0.93 }),
    frame: new THREE.MeshStandardMaterial({ color: '#2b3036', metalness: 0.6, roughness: 0.45 }),
    rebar: new THREE.MeshStandardMaterial({ color: '#7c3f1d', metalness: 0.6, roughness: 0.75 }),
    line: new THREE.MeshStandardMaterial({ color: '#d9d9d4', roughness: 0.8 }),
    kerb: new THREE.MeshStandardMaterial({ color: '#8d8f90', roughness: 0.9 }),
  }
  return M
}

// A storey stub: an extruded wall with a jagged top, in a wall-local frame (x along, y up).
function stubGeometry(len, hMin, hMax, thick, seed) {
  const r = rng(seed)
  const s = new THREE.Shape()
  s.moveTo(-len / 2, 0)
  s.lineTo(len / 2, 0)
  const n = Math.max(3, Math.round(len * 1.5))
  let h = hMin + r() * (hMax - hMin)
  for (let k = 0; k <= n; k++) {
    const x = len / 2 - (k / n) * len
    h = Math.max(hMin * 0.4, Math.min(hMax, h + (r() - 0.5) * 0.5))
    s.lineTo(x, k === 0 || k === n ? Math.min(h, hMin * 0.6) : h)
  }
  s.lineTo(-len / 2, 0)
  const g = new THREE.ExtrudeGeometry(s, { depth: thick, bevelEnabled: false })
  g.translate(0, 0, -thick / 2)
  return g
}

// Stub runs along each outer wall. Far sides (north, east) stand tall; the near sides keep low
// so the overview still looks into the rooms.
function stubRuns(W, H) {
  const sides = [
    { a: [0, H], b: [W, H], hMin: 0.9, hMax: 2.0, seed: 1 },   // north
    { a: [W, 0], b: [W, H], hMin: 0.8, hMax: 1.8, seed: 2 },   // east
    { a: [0, 0], b: [W, 0], hMin: 0.2, hMax: 0.7, seed: 3 },   // south, low
    { a: [0, 0], b: [0, H], hMin: 0.2, hMax: 0.6, seed: 4 },   // west, low
  ]
  const runs = []
  for (const sd of sides) {
    const r = rng(sd.seed * 977)
    const len = Math.hypot(sd.b[0] - sd.a[0], sd.b[1] - sd.a[1])
    const ang = Math.atan2(sd.b[1] - sd.a[1], sd.b[0] - sd.a[0])
    let t = 0.4 + r() * 1.5
    while (t < len - 1) {
      const seg = Math.min(len - 1 - t, 2 + r() * 4)
      const gap = 0.6 + r() * 2.4
      const corner = Math.min(t, len - (t + seg)) < 3 // corners survive taller
      runs.push({ pos: w2t(sd.a[0] + (sd.b[0] - sd.a[0]) * ((t + seg / 2) / len), sd.a[1] + (sd.b[1] - sd.a[1]) * ((t + seg / 2) / len), WALL_H + 0.024),
        ang, len: seg, hMin: sd.hMin * (corner ? 1.4 : 1), hMax: sd.hMax * (corner ? 1.4 : 1), brick: r() < 0.5, seed: Math.round(t * 100) + sd.seed })
      t += seg + gap
    }
  }
  return runs
}

export default function ExteriorShell({ fp }) {
  const [W, H] = fp.size
  const m = mats()
  const runs = useMemo(() => stubRuns(W, H), [W, H])
  const geoms = useMemo(() => runs.map((s) => stubGeometry(s.len, s.hMin, s.hMax, 0.26, s.seed)), [runs])
  const r = useMemo(() => rng(W * 31 + H), [W, H])
  // the pancaked upper slab: its inner edge on the north-west corner wall top, sloping down
  // outward onto the ruins north of the building
  const slabLen = 7
  const slabAng = 0.55
  return (
    <group>
      {/* floor-slab lip: where the upper floor sheared off, a thick edge all round */}
      {[[W / 2, H, W + 0.6, 0], [W / 2, 0, W + 0.6, 0], [0, H / 2, H, Math.PI / 2], [W, H / 2, H, Math.PI / 2]].map(([x, y, len, rot], i) => (
        <mesh key={i} position={w2t(x, y, WALL_H + 0.06)} rotation={[0, rot, 0]} material={m.slab} receiveShadow>
          <boxGeometry args={[len, 0.09, 0.34]} />
        </mesh>
      ))}
      {runs.map((s, i) => (
        <group key={i} position={s.pos} rotation={[0, s.ang, 0]}>
          <mesh geometry={geoms[i]} material={s.brick ? m.brick : m.concrete} castShadow receiveShadow />
          {/* rebar out of the broken top */}
          {[-0.3, 0.25].map((dx, k) => (
            <mesh key={k} position={[dx * s.len, s.hMin * 0.8 + k * 0.2, 0]} rotation={[0.3 * (k ? -1 : 1), 0, 0.5 * (k ? 1 : -1)]} material={m.rebar}>
              <cylinderGeometry args={[0.012, 0.012, 0.6, 5]} />
            </mesh>
          ))}
          {/* a window frame that survived in the taller stubs */}
          {s.hMax > 1.5 && s.len > 3 && (
            <group position={[0, 0.5, 0]}>
              {[-0.6, 0.6].map((dx) => <mesh key={dx} position={[dx, 0.45, 0]} material={m.frame}><boxGeometry args={[0.06, 0.9, 0.3]} /></mesh>)}
              <mesh position={[0, 0, 0]} material={m.frame}><boxGeometry args={[1.26, 0.06, 0.3]} /></mesh>
            </group>
          )}
        </group>
      ))}
      {/* pancaked upper slab off the north-west corner */}
      <group position={w2t(3.5, H - 0.2, WALL_H + 0.9)} rotation={[-slabAng, 0, 0]}>
        <mesh position={[0, 0, slabLen / 2 - 0.6]} material={m.slab} castShadow receiveShadow>
          <boxGeometry args={[6.5, 0.26, slabLen]} />
        </mesh>
        {[-2.6, -1.1, 0.4, 1.9].map((dx, i) => (
          <mesh key={i} position={[dx, -0.05, slabLen - 0.3]} rotation={[0.4 + i * 0.2, 0, (i % 2 ? 1 : -1) * 0.4]} material={m.rebar}>
            <cylinderGeometry args={[0.012, 0.012, 0.8, 5]} />
          </mesh>
        ))}
      </group>
      {/* the street west of the lot: kerbs and a dashed centre line */}
      {[-13.2, -21.2].map((x) => (
        <mesh key={x} position={w2t(x, H / 2, 0.06)} material={m.kerb} receiveShadow>
          <boxGeometry args={[0.3, 0.12, H + 40]} />
        </mesh>
      ))}
      {Array.from({ length: Math.round((H + 36) / 3) }, (_, i) => (
        <mesh key={i} position={w2t(-17.2, -18 + i * 3 + (r() - 0.5) * 0.1, 0.004)} rotation={[-Math.PI / 2, 0, 0]} material={m.line}>
          <planeGeometry args={[0.14, 1.5]} />
        </mesh>
      ))}
    </group>
  )
}
