import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line } from '@react-three/drei'
import * as THREE from 'three'
import { useSim } from '../store'
import { COLORS, MAST_H, w2t } from './util'

const NONE = []
const OFF = '#4b5563'

// --------------------------------------------------------------- relay node
// Reality knows power state and queue; Command only knows an announced position.
// Calm by default: the halo only pulses while the relay is carrying bundles, and only
// relay phones (the audience's own devices) or switched-off relays get a label.
function RelayNode({ pos, label, on = true, phone = false, known = true, busy = false }) {
  const halo = useRef()
  const phase = useRef(Math.random())
  useFrame(({ clock }) => {
    if (!halo.current) return
    const k = (clock.elapsedTime * 0.8 + phase.current) % 1
    halo.current.scale.setScalar(1 + k * 2.5)
    halo.current.material.opacity = 0.45 * (1 - k)
  })
  const lamp = !known ? '#6b7280' : on ? COLORS.teal : OFF
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
            <meshStandardMaterial color={known ? '#b7791f' : '#6b5b3e'} roughness={0.7} />
          </mesh>
          <mesh position={[0, 0.35, 0]}>
            <cylinderGeometry args={[0.015, 0.015, 0.45, 6]} />
            <meshStandardMaterial color="#6b7280" />
          </mesh>
        </>
      )}
      <mesh position={[0, top, 0]}>
        <sphereGeometry args={[0.07, 12, 12]} />
        <meshStandardMaterial color={lamp} emissive={lamp} emissiveIntensity={known && on ? 1.6 : 0} />
      </mesh>
      {known && on && busy && (
        <mesh ref={halo} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
          <ringGeometry args={[0.3, 0.36, 32]} />
          <meshBasicMaterial color={COLORS.teal} transparent side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      {label && (
        <Html position={[0, top + 0.35, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
          <div className={`tag relay${known && !on ? ' off' : ''}`}><b>{label}</b></div>
        </Html>
      )}
    </group>
  )
}

export function RealityRelays() {
  const relays = useSim((s) => s.tick?.reality.relays) ?? NONE
  return relays.map((r) => (
    <RelayNode key={r.id} pos={r.pos} on={r.on} phone={r.phone} busy={r.queue > 0}
               label={r.phone ? `${r.id} phone${r.on ? '' : ' · off'}` : r.on ? null : `${r.id} off`} />
  ))
}

export function CommandRelays() {
  const relays = useSim((s) => s.tick?.command.relays) ?? NONE
  return relays.map((r) => <RelayNode key={r.id} pos={r.pos} known={false} />)
}

// --------------------------------------------------------------- links
// Every radio link is drawn faint; only each robot's current path home to CMD is bright,
// in the robot's color. Same rules as the server: robots never forward for each other,
// and a hop costs 1 + (-60 - rssi) / 10.
function pathHome(start, edges, robots) {
  const dist = { [start]: 0 }
  const prev = {}
  const todo = new Set([start])
  while (todo.size) {
    let n = null
    for (const m of todo) if (n === null || dist[m] < dist[n]) n = m
    todo.delete(n)
    if (n === 'CMD') break
    if (n !== start && robots.has(n)) continue // robots are endpoints
    for (const [m, cost] of edges[n] ?? []) {
      const d = dist[n] + cost
      if (dist[m] === undefined || d < dist[m]) { dist[m] = d; prev[m] = n; todo.add(m) }
    }
  }
  if (dist.CMD === undefined) return null
  const out = ['CMD']
  while (out[0] !== start) out.unshift(prev[out[0]])
  return out
}

export function RealityLinks() {
  const tick = useSim((s) => s.tick)
  const fp = useSim((s) => s.floorplan)
  if (!tick || !fp) return null
  const [cx, cy] = fp.command_post.pos
  const at = { CMD: w2t(cx, cy, MAST_H) }
  const robots = new Set()
  for (const r of tick.reality.robots) { at[r.id] = w2t(r.pose[0], r.pose[1], 0.5); robots.add(r.id) }
  for (const r of tick.reality.relays) at[r.id] = w2t(r.pos[0], r.pos[1], 0.62)
  const up = tick.reality.links.filter((l) => l.up && at[l.a] && at[l.b] && !(robots.has(l.a) && robots.has(l.b)))
  const edges = {}
  for (const l of up) {
    const cost = 1 + Math.max(0, (-60 - l.rssi) / 10)
    ;(edges[l.a] ??= []).push([l.b, cost])
    ;(edges[l.b] ??= []).push([l.a, cost])
  }
  const home = []
  for (const r of tick.reality.robots) {
    const route = r.link.up ? pathHome(r.id, edges, robots) : null
    if (route) home.push({ id: r.id, color: r.color, points: route.map((n) => at[n]) })
  }
  return (
    <group>
      {up.map((l) => (
        <Line key={`${l.a}-${l.b}`} points={[at[l.a], at[l.b]]} color={l.fec ? COLORS.amber : '#cbd5e1'}
              lineWidth={1} transparent opacity={l.fec ? 0.28 : 0.16} />
      ))}
      {home.map((h) => (
        <Line key={`home-${h.id}`} points={h.points} color={h.color} lineWidth={2.5} transparent opacity={0.9} />
      ))}
      {tick.reality.robots.filter((r) => !r.link.up).map((r) => (
        <Line key={`dark-${r.id}`} points={[at[r.id], at.CMD]} color={COLORS.red} lineWidth={1}
              transparent opacity={0.3} dashed dashSize={0.4} gapSize={0.3} />
      ))}
    </group>
  )
}

// --------------------------------------------------------------- antenna pulse
// A ring leaves the command post antenna when a report that matters reaches CMD.
export function AntennaPulse() {
  const fp = useSim((s) => s.floorplan)
  const ring = useRef()
  const last = useRef(null)
  const start = useRef(-10)
  useFrame(({ clock }) => {
    const delivered = useSim.getState().bigDeliveries // survivor / route / fault reports, not telemetry
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
    <mesh ref={ring} position={w2t(cx, cy, MAST_H + 0.05)} rotation={[-Math.PI / 2, 0, 0]} visible={false}>
      <ringGeometry args={[0.25, 0.32, 32]} />
      <meshBasicMaterial color={COLORS.amber} transparent side={THREE.DoubleSide} depthWrite={false} />
    </mesh>
  )
}
