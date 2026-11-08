import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import Line from './FastLine' // drei's Line relinks its shader on every new points array
import { drainHops, linkRate } from '../net/traffic'
import { useSim, useStable } from '../store'
import { COLORS, MAST_H, w2t } from './util'

const NONE = []
const OFF = '#4b5563'

// --------------------------------------------------------------- relay node
// Reality knows power state and queue; Command only knows an announced position.
// Calm by default: the halo only pulses while the relay is carrying bundles, and only
// relay phones (the audience's own devices) or switched-off relays get a label.
// A rugged field relay: a yellow hard case (ribs, latches, carry handle) with a folding
// antenna mast, two whips and a status LED that blinks while it is on. A phone relay is the
// audience's phone in a rubber case on a small stand. Same model crushed when destroyed.
let caseMats = null
function relayMats() {
  caseMats ??= {
    shell: new THREE.MeshStandardMaterial({ color: '#d29a14', roughness: 0.55, metalness: 0.05 }),
    shellDim: new THREE.MeshStandardMaterial({ color: '#7a6332', roughness: 0.7 }),
    dark: new THREE.MeshStandardMaterial({ color: '#1c1f23', roughness: 0.6, metalness: 0.2 }),
    metal: new THREE.MeshStandardMaterial({ color: '#b9c0c8', metalness: 0.9, roughness: 0.3 }),
    rubber: new THREE.MeshStandardMaterial({ color: '#111315', roughness: 0.85 }),
    screen: new THREE.MeshStandardMaterial({ color: '#0b1220', emissive: '#1d4ed8', emissiveIntensity: 0.6, roughness: 0.2 }),
    crushed: new THREE.MeshStandardMaterial({ color: '#5a4a2a', roughness: 0.9 }),
  }
  return caseMats
}

function RelayCase({ m, shell }) {
  return (
    <group>
      <mesh material={shell} position={[0, 0.11, 0]} castShadow receiveShadow><boxGeometry args={[0.42, 0.2, 0.3]} /></mesh>
      {[-0.13, 0, 0.13].map((x) => <mesh key={x} material={shell} position={[x, 0.11, 0]}><boxGeometry args={[0.03, 0.205, 0.31]} /></mesh>)}
      <mesh material={m.dark} position={[0, 0.215, 0]}><boxGeometry args={[0.43, 0.012, 0.31]} /></mesh>
      {[-0.12, 0.12].map((x) => <mesh key={x} material={m.dark} position={[x, 0.17, 0.155]}><boxGeometry args={[0.05, 0.035, 0.012]} /></mesh>)}
      <mesh material={m.dark} position={[0, 0.24, 0]} rotation={[0, 0, Math.PI / 2]}><torusGeometry args={[0.035, 0.008, 6, 12, Math.PI]} /></mesh>
      <mesh material={m.metal} position={[-0.14, 0.42, -0.08]}><cylinderGeometry args={[0.012, 0.016, 0.42, 8]} /></mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} material={m.rubber} position={[-0.14 + s * 0.05, 0.72, -0.08]} rotation={[0, 0, s * 0.12]}><cylinderGeometry args={[0.005, 0.008, 0.26, 6]} /></mesh>
      ))}
    </group>
  )
}

function RelayNode({ pos, label, on = true, phone = false, known = true, busy = false, destroyed = false }) {
  const halo = useRef()
  const phase = useRef(Math.random())
  useFrame(({ clock }) => {
    if (!halo.current) return
    const k = (clock.elapsedTime * 0.8 + phase.current) % 1
    halo.current.scale.setScalar(1 + k * 2.5)
    halo.current.material.opacity = 0.45 * (1 - k)
  })
  const lamp = !known ? '#6b7280' : on ? '#22c55e' : OFF
  const top = phone ? 0.5 : 0.62
  const m = relayMats()
  const led = useRef()
  useFrame(({ clock }) => {
    if (led.current) led.current.emissiveIntensity = known && on ? (Math.sin((clock.elapsedTime + phase.current * 3) * 6) > 0.6 ? 3 : 0.3) : 0
  })
  if (destroyed) {
    // crushed by the aftershock: knocked flat, antenna snapped, no lamp
    return (
      <group position={w2t(pos[0], pos[1], 0)}>
        <group rotation={[0.25, 0.5, Math.PI / 2 - 0.2]} position={[0.1, 0.16, 0]} scale={[1, 0.6, 1]}>
          <RelayCase m={m} shell={m.crushed} />
        </group>
        {label && (
          <Html position={[0, 0.7, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
            <div className="tag relay off"><b>{label}</b></div>
          </Html>
        )}
      </group>
    )
  }
  return (
    <group position={w2t(pos[0], pos[1], 0)} scale={1.4 /* readable next to the drawn robots */}>
      {phone ? (
        <group>
          <mesh material={m.dark} position={[0, 0.05, 0]}><cylinderGeometry args={[0.1, 0.12, 0.04, 16]} /></mesh>
          <mesh material={m.metal} position={[0, 0.14, 0]} rotation={[0.25, 0, 0]}><boxGeometry args={[0.02, 0.16, 0.02]} /></mesh>
          <group position={[0, 0.32, 0.02]} rotation={[-0.3, 0, 0]}>
            <mesh material={m.rubber} castShadow><boxGeometry args={[0.2, 0.38, 0.03]} /></mesh>
            <mesh material={m.screen} position={[0, 0, 0.016]}><boxGeometry args={[0.17, 0.34, 0.002]} /></mesh>
          </group>
        </group>
      ) : <RelayCase m={m} shell={known ? m.shell : m.shellDim} />}
      <mesh position={phone ? [0, 0.53, -0.04] : [0.15, 0.235, 0.1]}>
        <sphereGeometry args={[phone ? 0.02 : 0.022, 10, 10]} />
        <meshStandardMaterial ref={led} color={lamp} emissive={lamp} emissiveIntensity={1} toneMapped={false} />
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
    <RelayNode key={r.id} pos={r.pos} on={r.on} phone={r.phone} busy={r.queue > 0} destroyed={r.destroyed}
               label={r.destroyed ? `${r.id} destroyed` : r.phone ? `${r.id} phone${r.on ? '' : ' · off'}` : r.on ? null : `${r.id} off`} />
  ))
}

export function CommandRelays() {
  const relays = useStable((s) => s.tick?.command.relays) ?? NONE
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

// --------------------------------------------------------------- packets
// One dot per actual completed hop (Aziz's bundle_hop), flown from sender to receiver just after
// the custody acknowledgment, coloured by what it carries. Pooled instances, positions from the
// nodes' current places; nothing is drawn without traffic events.
const PACKET_POOL = 96
const PACKET_MS = 650
const KIND_COLOR = { survivor: '#ef4444', rescue_route: '#facc15', fault: '#f59e0b', plan: '#60a5fa', command: '#60a5fa', command_ack: '#60a5fa' }
const packetColor = new THREE.Color()
const packetPos = new THREE.Vector3()
function Packets({ at }) {
  const mesh = useRef()
  const nodes = useRef(at)
  nodes.current = at
  const flying = useRef([])
  useFrame(() => {
    const m = mesh.current
    if (!m) return
    const now = performance.now()
    for (const h of drainHops()) {
      flying.current.push({ ...h, t0: now })
      if (flying.current.length > PACKET_POOL) flying.current.shift()
    }
    flying.current = flying.current.filter((p) => now - p.t0 < PACKET_MS)
    let i = 0
    for (const p of flying.current) {
      const a = nodes.current[p.a]
      const b = nodes.current[p.b]
      if (!a || !b) continue
      const k = (now - p.t0) / PACKET_MS
      const e = k * k * (3 - 2 * k)
      packetPos.set(a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e + Math.sin(Math.PI * e) * 0.35, a[2] + (b[2] - a[2]) * e)
      PACKET_DUMMY.position.copy(packetPos)
      PACKET_DUMMY.scale.setScalar(1)
      PACKET_DUMMY.updateMatrix()
      m.setMatrixAt(i, PACKET_DUMMY.matrix)
      m.setColorAt(i, packetColor.set(KIND_COLOR[p.kind] ?? '#5eead4'))
      i++
    }
    m.count = i
    m.instanceMatrix.needsUpdate = true
    if (m.instanceColor) m.instanceColor.needsUpdate = true
  })
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, PACKET_POOL]} frustumCulled={false} renderOrder={5}>
      <sphereGeometry args={[0.11, 10, 8]} />
      <meshBasicMaterial toneMapped={false} depthTest={false} transparent opacity={0.95} />
    </instancedMesh>
  )
}
const PACKET_DUMMY = new THREE.Object3D()

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
  // with traffic events (DZ_NETWORK_TRAFFIC): thickness from the bytes that actually crossed the
  // link in the last 3 s, dimmed when nothing did; colour from its state (weak or FEC = amber)
  const now = performance.now()
  return (
    <group>
      {up.map((l) => {
        const rate = linkRate(l.a, l.b, now)
        const weak = l.fec || l.rssi < -80
        const width = rate == null ? 1 : 1 + Math.min(3.5, Math.log2(1 + rate / 150))
        const opacity = rate == null ? (weak ? 0.28 : 0.16) : rate > 0 ? (weak ? 0.75 : 0.6) : 0.1
        return (
          <Line key={`${l.a}-${l.b}`} points={[at[l.a], at[l.b]]} color={weak ? COLORS.amber : '#cbd5e1'}
                lineWidth={width} transparent opacity={opacity} />
        )
      })}
      <Packets at={at} />
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
