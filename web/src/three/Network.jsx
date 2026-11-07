import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line } from '@react-three/drei'
import * as THREE from 'three'
import { useSim } from '../store'
import { COLORS, w2t } from './util'

const NONE = []
const OFF = '#4b5563'

// --------------------------------------------------------------- relay node
// Reality knows power state and queue; Command only knows an announced position.
function RelayNode({ pos, label, sub, on = true, phone = false, known = true }) {
  const halo = useRef()
  const phase = useRef(Math.random())
  useFrame(({ clock }) => {
    if (!halo.current) return
    const k = (clock.elapsedTime * 0.8 + phase.current) % 1
    halo.current.scale.setScalar(1 + k * 2.5)
    halo.current.material.opacity = 0.45 * (1 - k)
  })
  const lamp = !known ? '#9ca3af' : on ? COLORS.green : OFF
  const top = phone ? 0.5 : 0.62
  return (
    <group position={w2t(pos[0], pos[1], 0)}>
      {phone ? (
        <mesh position={[0, 0.22, 0]} castShadow>
          <boxGeometry args={[0.22, 0.42, 0.05]} />
          <meshStandardMaterial color="#e5e7eb" roughness={0.4} />
        </mesh>
      ) : (
        <>
          <mesh position={[0, 0.07, 0]} castShadow>
            <cylinderGeometry args={[0.18, 0.22, 0.14, 16]} />
            <meshStandardMaterial color={COLORS.amber} roughness={0.6} />
          </mesh>
          <mesh position={[0, 0.35, 0]}>
            <cylinderGeometry args={[0.015, 0.015, 0.45, 6]} />
            <meshStandardMaterial color="#9ca3af" />
          </mesh>
        </>
      )}
      <mesh position={[0, top, 0]}>
        <sphereGeometry args={[0.07, 12, 12]} />
        <meshStandardMaterial color={lamp} emissive={lamp} emissiveIntensity={known && on ? 2 : 0} />
      </mesh>
      {known && on && (
        <mesh ref={halo} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
          <ringGeometry args={[0.3, 0.36, 32]} />
          <meshBasicMaterial color={COLORS.green} transparent side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      <Html position={[0, top + 0.35, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
        <div className={`tag relay${known && !on ? ' off' : ''}`}>
          <b>{label}</b>{sub ? <span>{sub}</span> : null}
        </div>
      </Html>
    </group>
  )
}

export function RealityRelays() {
  const relays = useSim((s) => s.tick?.reality.relays) ?? NONE
  return relays.map((r) => (
    <RelayNode key={r.id} pos={r.pos} on={r.on} phone={r.phone} label={r.phone ? `${r.id} phone` : r.id}
               sub={!r.on ? 'OFF' : r.queue ? `${r.queue} queued` : null} />
  ))
}

export function CommandRelays() {
  const relays = useSim((s) => s.tick?.command.relays) ?? NONE
  return relays.map((r) => <RelayNode key={r.id} pos={r.pos} label={r.id} known={false} />)
}

// --------------------------------------------------------------- links
// Actual radio edges. Robot-to-robot links are skipped: robots never forward for
// each other (team rule), so those edges are not routes.
export function RealityLinks() {
  const tick = useSim((s) => s.tick)
  const fp = useSim((s) => s.floorplan)
  if (!tick || !fp) return null
  const [cx, cy] = fp.command_post.pos
  const at = { CMD: w2t(cx, cy, 2.4) }
  const robots = new Set()
  for (const r of tick.reality.robots) { at[r.id] = w2t(r.pose[0], r.pose[1], 0.5); robots.add(r.id) }
  for (const r of tick.reality.relays) at[r.id] = w2t(r.pos[0], r.pos[1], 0.62)
  const up = tick.reality.links.filter((l) => l.up && at[l.a] && at[l.b] && !(robots.has(l.a) && robots.has(l.b)))
  return (
    <group>
      {up.map((l) => (
        <Line key={`${l.a}-${l.b}`} points={[at[l.a], at[l.b]]} color={l.fec ? COLORS.amber : COLORS.green}
              lineWidth={l.fec ? 1.5 : 2} transparent opacity={0.75} />
      ))}
      {tick.reality.robots.filter((r) => !r.link.up).map((r) => (
        <Line key={`dark-${r.id}`} points={[at[r.id], at.CMD]} color={COLORS.red} lineWidth={1}
              transparent opacity={0.35} dashed dashSize={0.4} gapSize={0.3} />
      ))}
    </group>
  )
}

// --------------------------------------------------------------- antenna pulse
// A ring leaves the command post antenna each time a bundle is delivered to CMD.
export function AntennaPulse() {
  const fp = useSim((s) => s.floorplan)
  const ring = useRef()
  const last = useRef(null)
  const start = useRef(-10)
  useFrame(({ clock }) => {
    const delivered = useSim.getState().tick?.stats.delivered ?? 0
    if (last.current !== null && delivered > last.current) start.current = clock.elapsedTime
    last.current = delivered
    const k = (clock.elapsedTime - start.current) / 0.7
    if (!ring.current) return
    ring.current.visible = k < 1
    ring.current.scale.setScalar(1 + k * 3)
    ring.current.material.opacity = 0.8 * (1 - k)
  })
  if (!fp) return null
  const [cx, cy] = fp.command_post.pos
  return (
    <mesh ref={ring} position={w2t(cx, cy, 2.45)} rotation={[-Math.PI / 2, 0, 0]} visible={false}>
      <ringGeometry args={[0.25, 0.32, 32]} />
      <meshBasicMaterial color={COLORS.amber} transparent side={THREE.DoubleSide} depthWrite={false} />
    </mesh>
  )
}
