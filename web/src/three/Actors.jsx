import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line } from '@react-three/drei'
import * as THREE from 'three'
import { useSim } from '../store'
import { COLORS, FOG_H, w2t } from './util'
import { CommandRelays, RealityLinks, RealityRelays } from './Network'
import { CommandRoutes, RealityRoutes } from './Routes'

// --------------------------------------------------------------- robot body
function Headlight() {
  // the target must live in the scene graph or three.js never updates its matrix
  const tgt = useMemo(() => new THREE.Object3D(), [])
  return (
    <>
      <primitive object={tgt} position={[3, 0, 0]} />
      <spotLight position={[0.3, 0.3, 0]} angle={0.7} penumbra={0.6} intensity={6} distance={7}
                 decay={1.5} color="#cffaf5" target={tgt} />
    </>
  )
}

const ROBOT_SCALE = 1.8 // drawn larger than the 0.5 m body so robots read on a projector

function RobotBody({ pose, color, ghost = false, label, sub, headlight = true }) {
  const perf = useSim((s) => s.perf)
  const group = useRef()
  const sensor = useRef()
  const target = useRef(new THREE.Vector3(...w2t(pose[0], pose[1], 0)))
  const yaw = useRef(pose[2])
  target.current.set(...w2t(pose[0], pose[1], 0))

  useFrame((_, dt) => {
    const g = group.current
    if (!g) return
    // smooth toward the latest streamed pose so 10 Hz state looks like 60 fps motion
    g.position.lerp(target.current, Math.min(1, dt * 10))
    let d = pose[2] - yaw.current
    d = Math.atan2(Math.sin(d), Math.cos(d))
    yaw.current += d * Math.min(1, dt * 10)
    g.rotation.y = yaw.current
    if (sensor.current && !ghost) sensor.current.rotation.y += dt * 6
  })

  const op = ghost ? 0.35 : 1
  return (
    <group ref={group} position={target.current.toArray()}>
      <group scale={ROBOT_SCALE}>
      {!ghost && (
        // colored pool of light under the robot so it reads from across the room
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.015, 0]}>
          <circleGeometry args={[0.42, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.35} blending={THREE.AdditiveBlending} depthWrite={false} />
        </mesh>
      )}
      <mesh position={[0, 0.16, 0]} castShadow>
        <boxGeometry args={[0.5, 0.18, 0.36]} />
        <meshStandardMaterial color={color} transparent={ghost} opacity={op}
                              emissive={color} emissiveIntensity={ghost ? 0.1 : 0.7} />
      </mesh>
      {[[-0.15, 0.2], [0.15, 0.2], [-0.15, -0.2], [0.15, -0.2]].map(([x, z], i) => (
        <mesh key={i} position={[x, 0.08, z]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.08, 0.08, 0.06, 12]} />
          <meshStandardMaterial color="#0f1214" transparent={ghost} opacity={op} />
        </mesh>
      ))}
      <mesh ref={sensor} position={[0.05, 0.32, 0]}>
        <cylinderGeometry args={[0.07, 0.07, 0.1, 12]} />
        <meshStandardMaterial color="#e5e7eb" transparent={ghost} opacity={op}
                              emissive="#ffffff" emissiveIntensity={ghost ? 0 : 0.6} />
      </mesh>
      {!ghost && headlight && !perf && <Headlight />}
      </group>
      {label && (
        <Html position={[0, 0.8 * ROBOT_SCALE, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
          <div className={ghost ? 'tag ghost' : 'tag'}>
            <b>{label}</b>{sub ? <span>{sub}</span> : null}
          </div>
        </Html>
      )}
    </group>
  )
}

// --------------------------------------------------------------- lidar rays
function Lidar({ robot }) {
  const geom = useMemo(() => new THREE.BufferGeometry(), [])
  const perf = useSim((s) => s.perf)
  const [x, y] = robot.pose
  const pts = []
  for (const [lx, ly] of perf ? robot.lidar.filter((_, i) => i % 2 === 0) : robot.lidar) {
    pts.push(x, 0.3, -y, lx, 0.3, -ly)
  }
  geom.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
  geom.computeBoundingSphere()
  return (
    <lineSegments geometry={geom}>
      <lineBasicMaterial color={COLORS.teal} transparent opacity={0.18} />
    </lineSegments>
  )
}

// --------------------------------------------------------------- survivor marker
const BURST_S = 2.5

// Fixed per-survivor angle so each person lies differently but never jumps between frames.
function lieAngle(id = '') {
  let h = 0
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 360
  return (h * Math.PI) / 180
}

// Low-poly person lying down, colored like a thermal image: head hottest, limbs cooler.
const HOT = { color: '#ffd166', emissive: '#ffb02e', emissiveIntensity: 1.6, flatShading: true, roughness: 0.7 }
const WARM = { color: '#ff7a3d', emissive: '#ff4d1a', emissiveIntensity: 1.3, flatShading: true, roughness: 0.7 }
const COOL = { color: '#c2410c', emissive: '#9a2a0a', emissiveIntensity: 1.0, flatShading: true, roughness: 0.8 }
export function PersonFigure({ id }) {
  return (
    <group rotation={[0, lieAngle(id), 0]} scale={1.5}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
        <circleGeometry args={[0.75, 32]} />
        <meshBasicMaterial color="#ff5a1f" transparent opacity={0.3} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh position={[0.44, 0.11, 0]}><icosahedronGeometry args={[0.12, 0]} /><meshStandardMaterial {...HOT} /></mesh>
      <mesh position={[0.13, 0.1, 0]}><boxGeometry args={[0.4, 0.15, 0.28]} /><meshStandardMaterial {...WARM} /></mesh>
      <mesh position={[0.16, 0.08, 0.2]} rotation={[0, 0.25, 0]}><boxGeometry args={[0.36, 0.08, 0.08]} /><meshStandardMaterial {...COOL} /></mesh>
      <mesh position={[0.16, 0.08, -0.2]} rotation={[0, -0.25, 0]}><boxGeometry args={[0.36, 0.08, 0.08]} /><meshStandardMaterial {...COOL} /></mesh>
      <mesh position={[-0.27, 0.08, 0.075]} rotation={[0, 0.08, 0]}><boxGeometry args={[0.46, 0.1, 0.11]} /><meshStandardMaterial {...COOL} /></mesh>
      <mesh position={[-0.27, 0.08, -0.075]} rotation={[0, -0.12, 0]}><boxGeometry args={[0.46, 0.1, 0.11]} /><meshStandardMaterial {...COOL} /></mesh>
    </group>
  )
}

// `born` (performance.now ms) plays a shockwave when Command first learns a survivor.
function Survivor({ pos, label, born, id }) {
  const ring = useRef()
  const shock = useRef()
  const light = useRef()
  useFrame(({ clock }) => {
    const s = 1 + 0.5 * ((clock.elapsedTime * 1.2) % 1)
    if (ring.current) {
      ring.current.scale.set(s, s, s)
      ring.current.material.opacity = 1.2 - s * 0.7
    }
    const age = born ? (performance.now() - born) / 1000 : BURST_S
    const k = Math.min(1, age / BURST_S)
    if (shock.current) {
      shock.current.visible = k < 1
      shock.current.scale.setScalar(1 + k * 9)
      shock.current.material.opacity = 0.9 * (1 - k)
    }
    if (light.current) light.current.intensity = 3 + 25 * (1 - k)
  })
  return (
    <group position={w2t(pos[0], pos[1], 0)}>
      <PersonFigure id={id} />
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
        <ringGeometry args={[0.95, 1.12, 48]} />
        <meshBasicMaterial color={COLORS.red} transparent opacity={0.8} side={THREE.DoubleSide} />
      </mesh>
      {born && (
        <mesh ref={shock} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.08, 0]}>
          <ringGeometry args={[0.5, 0.62, 48]} />
          <meshBasicMaterial color="#fecaca" transparent side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      <pointLight ref={light} position={[0, 0.8, 0]} color={COLORS.red} intensity={3} distance={4} />
      <Html position={[0, 1.1, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
        <div className="tag alert"><b>{label}</b></div>
      </Html>
    </group>
  )
}

// Ground truth the robots have not found yet (T key): survivors in red, thermal
// decoys in amber. Reality pane only, never Command. Drawn just above the fog layer.
function TruthMarker({ pos, id, sub = 'not found yet', color = COLORS.red, decoy = false }) {
  const ring = useRef()
  useFrame(({ clock }) => {
    if (ring.current) ring.current.material.opacity = 0.35 + 0.2 * Math.sin(clock.elapsedTime * 2)
  })
  return (
    <group position={w2t(pos[0], pos[1], 0)}>
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, FOG_H + 0.03, 0]} renderOrder={3}>
        <ringGeometry args={[0.35, 0.42, 32]} />
        <meshBasicMaterial color={color} transparent side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <Html position={[0, FOG_H + 0.6, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
        <div className={`tag ghost truth${decoy ? ' decoy' : ''}`}><b>{id}</b><span>{sub}</span></div>
      </Html>
    </group>
  )
}

// --------------------------------------------------------------- views
// survivors_found has one record per robot that saw a survivor; keep the earliest.
function firstFinds(records) {
  const byId = new Map()
  for (const rec of records) if (!byId.has(rec.id) || rec.t < byId.get(rec.id).t) byId.set(rec.id, rec)
  return [...byId.values()]
}

export function RealityActors() {
  const tick = useSim((s) => s.tick)
  const fp = useSim((s) => s.floorplan)
  const showTruth = useSim((s) => s.showTruth)
  if (!tick || !fp) return null
  const { robots } = tick.reality
  const survivors_found = firstFinds(tick.reality.survivors_found)
  const found = new Set(survivors_found.map((s) => s.id))
  return (
    <group>
      {robots.map((r) => (
        <group key={r.id}>
          <RobotBody pose={r.pose} color={r.color} label={r.name}
                     sub={r.link.up ? `${r.link.rssi} dBm` : 'NO LINK'} />
          <Lidar robot={r} />
          {r.path.length > 1 && (
            <Line points={[[r.pose[0], 0.06, -r.pose[1]], ...r.path.map(([px, py]) => [px, 0.06, -py])]}
                  color={r.color} lineWidth={1.5} dashed dashSize={0.25} gapSize={0.15} transparent opacity={0.7} />
          )}
        </group>
      ))}
      <RealityLinks />
      <RealityRelays />
      <RealityRoutes />
      {survivors_found.map((s) => <Survivor key={s.id} id={s.id} pos={s.pos} label={`${s.id} found by ${s.by}`} />)}
      {showTruth && (fp.survivors ?? []).filter((s) => !found.has(s.id)).map((s) => (
        <TruthMarker key={s.id} pos={s.pos} id={s.id} />
      ))}
      {showTruth && (fp.decoys ?? []).map((d) => (
        <TruthMarker key={d.id} pos={d.pos} id={d.id} sub={`${d.label} · decoy`} color={COLORS.amber} decoy />
      ))}
    </group>
  )
}

export function CommandActors() {
  const tick = useSim((s) => s.tick)
  const time = useSim((s) => s.time)
  const births = useRef(new Map()) // survivor id -> when Command first learned it
  if (!tick) return null
  const { robots, survivors } = tick.command
  const ids = new Set(survivors.map((s) => s.id))
  for (const id of births.current.keys()) if (!ids.has(id)) births.current.delete(id) // reset
  for (const s of survivors) if (!births.current.has(s.id)) births.current.set(s.id, performance.now())
  return (
    <group>
      {robots.map((r) => {
        const stale = time - r.last_seen
        const ghost = stale > 3
        return (
          <RobotBody key={r.id} pose={r.pose} color={ghost ? '#94a3b8' : '#2dd4bf'} ghost={ghost}
                     headlight={false} label={r.id}
                     sub={ghost ? `last seen ${stale.toFixed(0)}s ago` : r.state.replaceAll('_', ' ').toLowerCase()} />
        )
      })}
      <CommandRelays />
      <CommandRoutes />
      {survivors.map((s) => <Survivor key={s.id} id={s.id} pos={s.pos} label={`${s.id} reported`} born={births.current.get(s.id)} />)}
    </group>
  )
}
