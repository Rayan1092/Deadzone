import { useMemo } from 'react'
import * as THREE from 'three'
import { useSim } from '../store'
import { COLORS, WALL_H, w2t } from './util'

// Deterministic pseudo random so rubble looks the same on every client and reload
function rng(seed) {
  let s = seed % 2147483647
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}

// Thermal palette for the robot's-eye view: everything cold reads as deep blue.
const COLD = { floor: '#070b1f', wall: '#1d3a8a', wallGlow: '#0b1d5c', rubble: '#1e293b' }
// Blueprint palette for the Command inset: the public floorplan only, no truth rubble.
const PRINT = { floor: '#0a1830', wall: '#7fb2ff', wallGlow: '#1e40af' }

function Walls({ walls, thermal, blueprint }) {
  return walls.map((w, i) => {
    const [ax, ay] = w.a
    const [bx, by] = w.b
    const len = Math.hypot(bx - ax, by - ay)
    const ang = Math.atan2(by - ay, bx - ax)
    const thick = w.material === 'concrete' ? 0.3 : w.material === 'metal' ? 0.12 : 0.2
    const col = blueprint ? PRINT.wall : thermal ? COLD.wall : w.material === 'metal' ? '#4b5563' : COLORS.wall
    return (
      <mesh key={i} position={w2t((ax + bx) / 2, (ay + by) / 2, WALL_H / 2)} rotation={[0, ang, 0]}
            castShadow receiveShadow>
        <boxGeometry args={[len + thick, WALL_H, thick]} />
        <meshStandardMaterial color={col} roughness={0.9}
                              emissive={blueprint ? PRINT.wallGlow : thermal ? COLD.wallGlow : '#000000'} />
      </mesh>
    )
  })
}

function Rubble({ rubble, thermal }) {
  const rocks = useMemo(() => {
    const out = []
    rubble.forEach((rb, k) => {
      const xs = rb.poly.map((p) => p[0])
      const ys = rb.poly.map((p) => p[1])
      const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
      const r = rng(1000 + k * 77)
      const n = Math.max(6, Math.round((x1 - x0) * (y1 - y0) * 3))
      for (let i = 0; i < n; i++) {
        const s = 0.25 + r() * 0.5
        out.push({
          key: `${k}-${i}`,
          pos: w2t(x0 + r() * (x1 - x0), y0 + r() * (y1 - y0), s * 0.5 + r() * (rb.height || 1) * 0.5),
          rot: [r() * 3, r() * 3, r() * 3],
          s,
          shade: 0.7 + r() * 0.3,
        })
      }
    })
    return out
  }, [rubble])
  return rocks.map((k) => (
    <mesh key={k.key} position={k.pos} rotation={k.rot} castShadow>
      <dodecahedronGeometry args={[k.s, 0]} />
      <meshStandardMaterial color={new THREE.Color(thermal ? COLD.rubble : COLORS.rubble).multiplyScalar(k.shade)} flatShading roughness={1} />
    </mesh>
  ))
}

function Hazards({ hazards }) {
  return hazards.map((hz) => {
    const shape = new THREE.Shape(hz.poly.map(([x, y]) => new THREE.Vector2(x, y)))
    return (
      <mesh key={hz.id} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
        <shapeGeometry args={[shape]} />
        <meshBasicMaterial color={COLORS.hazard} transparent opacity={0.16} depthWrite={false} />
      </mesh>
    )
  })
}

export default function Building({ thermal = false, blueprint = false }) {
  const fp = useSim((s) => s.floorplan)
  if (!fp) return null
  const [W, H] = fp.size
  const [cx, cy] = fp.command_post.pos
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, 0)} receiveShadow>
        <planeGeometry args={[W + 8, H + 8]} />
        <meshStandardMaterial color={blueprint ? PRINT.floor : thermal ? COLD.floor : COLORS.floor} roughness={1} />
      </mesh>
      {!thermal && !blueprint && <gridHelper args={[Math.max(W, H) + 8, Math.max(W, H) + 8, '#22292f', '#1e2429']}
                                             position={w2t(W / 2, H / 2, 0.005)} />}
      <Walls walls={fp.walls} thermal={thermal} blueprint={blueprint} />
      {!blueprint && <Rubble rubble={fp.rubble || []} thermal={thermal} />}
      {!thermal && <Hazards hazards={fp.hazards || []} />}
      {/* command post antenna */}
      <group position={w2t(cx, cy, 0)}>
        <mesh position={[0, 1.2, 0]}>
          <cylinderGeometry args={[0.06, 0.1, 2.4, 8]} />
          <meshStandardMaterial color="#9ca3af" />
        </mesh>
        <mesh position={[0, 2.45, 0]}>
          <sphereGeometry args={[0.18, 16, 16]} />
          <meshStandardMaterial color={COLORS.amber} emissive={COLORS.amber} emissiveIntensity={1.5} />
        </mesh>
      </group>
    </group>
  )
}
