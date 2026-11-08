import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line, RoundedBox } from '@react-three/drei'
import * as THREE from 'three'
import { useSim } from '../store'
import { COLORS, FOG_H, w2t } from './util'
import { materials } from './textures'
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

// Tracked search rover, x forward, 0.5 m long before ROBOT_SCALE: rubber tracks with
// road wheels, graphite chassis, a shell in the robot's color with LED strips, a pan-tilt
// camera head up front, a spinning lidar puck on a mast and a radio whip at the back whose
// tip shows the link (green up, red dark).
let roverMats = null
function sharedRoverMats() {
  if (roverMats) return roverMats
  const t = materials().tread
  const tread = t.map.clone()
  tread.repeat.set(6, 1)
  tread.needsUpdate = true
  roverMats = {
    track: new THREE.MeshStandardMaterial({ map: tread, color: '#4b4f55', roughness: 0.9 }),
    chassis: new THREE.MeshStandardMaterial({ color: '#2a2f35', metalness: 0.6, roughness: 0.42 }),
    metal: new THREE.MeshStandardMaterial({ color: '#b8bec6', metalness: 0.9, roughness: 0.28 }),
    black: new THREE.MeshStandardMaterial({ color: '#0d0f11', metalness: 0.3, roughness: 0.25 }),
    lens: new THREE.MeshStandardMaterial({ color: '#0a1630', metalness: 1, roughness: 0.05 }),
    lamp: new THREE.MeshStandardMaterial({ color: '#ffffff', emissive: '#e8fbff', emissiveIntensity: 3, toneMapped: false }),
    ghost: new THREE.MeshStandardMaterial({ color: '#94a3b8', transparent: true, opacity: 0.32, depthWrite: false }),
  }
  return roverMats
}

function Rover({ color, ghost, sensor, linkUp }) {
  const base = sharedRoverMats()
  const paint = useMemo(() => new THREE.MeshStandardMaterial({ color, metalness: 0.25, roughness: 0.38, emissive: color, emissiveIntensity: 0.12 }), [color])
  const led = useMemo(() => new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 2.6, toneMapped: false }), [color])
  const tip = useMemo(() => new THREE.MeshStandardMaterial({ color: linkUp ? '#4ade80' : '#ef4444', emissive: linkUp ? '#22c55e' : '#ef4444', emissiveIntensity: 3, toneMapped: false }), [linkUp])
  const M = ghost
    ? { track: base.ghost, chassis: base.ghost, metal: base.ghost, black: base.ghost, lens: base.ghost, lamp: base.ghost, paint: base.ghost, led: base.ghost, tip: base.ghost }
    : { ...base, paint, led, tip }
  const shadow = false // static shadow map; ambient occlusion grounds the rover
  return (
    <group>
      {[-0.15, 0.15].map((z) => (
        <group key={z} position={[0, 0, z]}>
          <RoundedBox args={[0.54, 0.13, 0.09]} radius={0.055} smoothness={3} position={[0, 0.075, 0]} material={M.track} castShadow={shadow} />
          {[-0.17, 0, 0.17].map((x) => (
            <mesh key={x} position={[x, 0.075, z > 0 ? 0.047 : -0.047]} rotation={[Math.PI / 2, 0, 0]} material={M.metal}>
              <cylinderGeometry args={[0.04, 0.04, 0.012, 14]} />
            </mesh>
          ))}
        </group>
      ))}
      <RoundedBox args={[0.44, 0.1, 0.21]} radius={0.02} smoothness={2} position={[0, 0.15, 0]} material={M.chassis} castShadow={shadow} />
      <RoundedBox args={[0.36, 0.07, 0.27]} radius={0.03} smoothness={3} position={[-0.02, 0.225, 0]} material={M.paint} castShadow={shadow} />
      {[-0.137, 0.137].map((z) => (
        <mesh key={z} position={[-0.02, 0.215, z]} material={M.led}>
          <boxGeometry args={[0.3, 0.018, 0.006]} />
        </mesh>
      ))}
      {/* front bumper with two lamps */}
      <mesh position={[0.235, 0.13, 0]} material={M.black}><boxGeometry args={[0.04, 0.07, 0.24]} /></mesh>
      {[-0.07, 0.07].map((z) => (
        <mesh key={z} position={[0.257, 0.135, z]} rotation={[0, 0, Math.PI / 2]} material={M.lamp}>
          <cylinderGeometry args={[0.018, 0.018, 0.006, 12]} />
        </mesh>
      ))}
      {/* pan-tilt camera */}
      <mesh position={[0.12, 0.28, 0]} material={M.chassis}><cylinderGeometry args={[0.025, 0.03, 0.05, 10]} /></mesh>
      <RoundedBox args={[0.08, 0.055, 0.1]} radius={0.012} smoothness={2} position={[0.13, 0.325, 0]} material={M.black} castShadow={shadow} />
      <mesh position={[0.172, 0.325, 0]} rotation={[0, 0, Math.PI / 2]} material={M.lens}><cylinderGeometry args={[0.02, 0.02, 0.012, 14]} /></mesh>
      {/* lidar mast and spinning puck */}
      <mesh position={[-0.06, 0.29, 0]} material={M.metal}><cylinderGeometry args={[0.012, 0.012, 0.08, 8]} /></mesh>
      <group ref={sensor} position={[-0.06, 0.345, 0]}>
        <mesh material={M.black} castShadow={shadow}><cylinderGeometry args={[0.05, 0.05, 0.045, 18]} /></mesh>
        <mesh position={[0, 0.026, 0]} material={M.metal}><cylinderGeometry args={[0.04, 0.05, 0.008, 18]} /></mesh>
        <mesh position={[0.048, 0, 0]} material={M.led}><boxGeometry args={[0.006, 0.012, 0.03]} /></mesh>
      </group>
      {/* radio whip */}
      <mesh position={[-0.17, 0.42, 0.09]} material={M.black}><cylinderGeometry args={[0.004, 0.006, 0.34, 6]} /></mesh>
      <mesh position={[-0.17, 0.595, 0.09]} material={M.tip}><sphereGeometry args={[0.012, 10, 10]} /></mesh>
    </group>
  )
}

const ROBOT_SCALE = 1.8 // drawn larger than the 0.5 m body so robots read on a projector

function RobotBody({ pose, color, ghost = false, label, sub, headlight = true, linkUp = true }) {
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

  return (
    <group ref={group} position={target.current.toArray()}>
      <group scale={ROBOT_SCALE}>
        {!ghost && (
          // colored pool of light under the robot so it reads from across the room
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.012, 0]}>
            <circleGeometry args={[0.42, 32]} />
            <meshBasicMaterial color={color} transparent opacity={0.22} blending={THREE.AdditiveBlending} depthWrite={false} />
          </mesh>
        )}
        <Rover color={color} ghost={ghost} sensor={sensor} linkUp={linkUp} />
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

// --------------------------------------------------------------- lidar coverage
// What the lidar sees right now, as one soft fan in the robot's color (a visibility
// polygon from the beam endpoints) instead of dozens of individual rays.
function Lidar({ robot }) {
  const geom = useMemo(() => new THREE.BufferGeometry(), [])
  const perf = useSim((s) => s.perf)
  const [x, y] = robot.pose
  const ends = perf ? robot.lidar.filter((_, i) => i % 2 === 0) : robot.lidar
  if (ends.length < 3) return null
  const pts = [x, 0.05, -y]
  for (const [lx, ly] of ends) pts.push(lx, 0.05, -ly)
  const index = []
  for (let i = 1; i <= ends.length; i++) index.push(0, i, (i % ends.length) + 1)
  geom.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
  geom.setIndex(index)
  geom.computeBoundingSphere()
  return (
    <mesh geometry={geom} renderOrder={1}>
      <meshBasicMaterial color={robot.color} transparent opacity={0.05} depthWrite={false} side={THREE.DoubleSide} />
    </mesh>
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

// A person lying where they fell: capsule limbs, clothes and skin, one arm flung up by
// the head. Clothing varies per survivor id. A warm glow pool underneath keeps them
// readable from across the room (the heat the thermal camera picks up).
const OUTFITS = [
  { top: '#2b4a7a', legs: '#2d3340', skin: '#c99a7a', hair: '#2a1d14' },
  { top: '#7a2b2b', legs: '#3b3f47', skin: '#8d5e43', hair: '#16110d' },
  { top: '#4f6b3a', legs: '#26303d', skin: '#e0b896', hair: '#6b4a2b' },
  { top: '#d97706', legs: '#2f3640', skin: '#b07b5a', hair: '#1c1410' },
]
const personMats = new Map()
function outfit(id) {
  let h = 0
  for (const ch of id ?? '') h = (h * 31 + ch.charCodeAt(0)) % 997
  const o = OUTFITS[h % OUTFITS.length]
  if (!personMats.has(o)) {
    const m = (color, rough = 0.85) => new THREE.MeshStandardMaterial({ color, roughness: rough })
    personMats.set(o, { top: m(o.top), legs: m(o.legs), skin: m(o.skin, 0.6), hair: m(o.hair, 0.9), shoe: m('#1a1a1a', 0.6) })
  }
  return personMats.get(o)
}

function Limb({ from, to, r, m }) {
  const a = new THREE.Vector3(...from)
  const b = new THREE.Vector3(...to)
  const mid = a.clone().add(b).multiplyScalar(0.5)
  const dir = b.clone().sub(a)
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize())
  return (
    <mesh position={mid} quaternion={q} material={m} castShadow>
      <capsuleGeometry args={[r, Math.max(0.01, dir.length() - r * 2), 4, 10]} />
    </mesh>
  )
}

export function PersonFigure({ id }) {
  const M = outfit(id)
  const y = 0.1 // limbs rest on the floor
  return (
    <group rotation={[0, lieAngle(id), 0]} scale={1.35}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.015, 0]}>
        <circleGeometry args={[0.8, 32]} />
        <meshBasicMaterial color="#ff5a1f" transparent opacity={0.22} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      {/* torso and hips */}
      <Limb from={[0.02, y + 0.02, 0]} to={[0.36, y + 0.03, 0]} r={0.12} m={M.top} />
      <Limb from={[-0.06, y, 0]} to={[0.06, y + 0.01, 0]} r={0.105} m={M.legs} />
      {/* head */}
      <mesh position={[0.56, y + 0.01, 0.02]} material={M.skin} castShadow><sphereGeometry args={[0.085, 18, 14]} /></mesh>
      <mesh position={[0.6, y + 0.03, 0.02]} scale={[0.9, 0.85, 1]} material={M.hair}><sphereGeometry args={[0.086, 14, 10, 0, Math.PI * 2, 0, Math.PI / 2]} /></mesh>
      {/* arms: one along the side, one flung up past the head */}
      <Limb from={[0.34, y + 0.02, 0.15]} to={[0.08, y - 0.02, 0.2]} r={0.042} m={M.top} />
      <Limb from={[0.08, y - 0.02, 0.2]} to={[-0.12, y - 0.04, 0.17]} r={0.036} m={M.skin} />
      <Limb from={[0.36, y + 0.02, -0.15]} to={[0.56, y - 0.02, -0.28]} r={0.042} m={M.top} />
      <Limb from={[0.56, y - 0.02, -0.28]} to={[0.76, y - 0.04, -0.22]} r={0.036} m={M.skin} />
      {/* legs, one bent */}
      <Limb from={[-0.06, y, 0.07]} to={[-0.46, y - 0.01, 0.1]} r={0.058} m={M.legs} />
      <Limb from={[-0.46, y - 0.01, 0.1]} to={[-0.84, y - 0.03, 0.12]} r={0.05} m={M.legs} />
      <Limb from={[-0.06, y, -0.07]} to={[-0.4, y + 0.12, -0.16]} r={0.058} m={M.legs} />
      <Limb from={[-0.4, y + 0.12, -0.16]} to={[-0.74, y - 0.03, -0.2]} r={0.05} m={M.legs} />
      <mesh position={[-0.89, y - 0.02, 0.12]} material={M.shoe}><boxGeometry args={[0.1, 0.08, 0.1]} /></mesh>
      <mesh position={[-0.79, y - 0.02, -0.2]} material={M.shoe}><boxGeometry args={[0.1, 0.08, 0.1]} /></mesh>
    </group>
  )
}

// `born` (performance.now ms) plays a shockwave when Command first learns a survivor.
const SETTLE_S = 10 // seconds a new survivor pulses and keeps its label

// tone 'pending' = found but Command doesn't know yet (gap view): amber, keeps pulsing.
function Survivor({ pos, label, born, id, burst = false, tone = 'alert', hold = false }) {
  const ring = useRef()
  const shock = useRef()
  const light = useRef()
  const tag = useRef()
  useFrame(({ clock }) => {
    const age = born ? (performance.now() - born) / 1000 : SETTLE_S
    const fresh = hold || age < SETTLE_S
    if (ring.current) {
      const s = fresh ? 1 + 0.5 * ((clock.elapsedTime * 1.2) % 1) : 1
      ring.current.scale.set(s, s, s)
      ring.current.material.opacity = fresh ? 1.2 - s * 0.7 : 0.35
    }
    if (tag.current) tag.current.style.display = fresh ? '' : 'none'
    const k = Math.min(1, age / BURST_S)
    if (shock.current) {
      shock.current.visible = k < 1
      shock.current.scale.setScalar(1 + k * 9)
      shock.current.material.opacity = 0.9 * (1 - k)
    }
    if (light.current) light.current.intensity = 3 + (burst ? 25 * (1 - k) : 0)
  })
  return (
    <group position={w2t(pos[0], pos[1], 0)}>
      <PersonFigure id={id} />
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
        <ringGeometry args={[0.95, 1.12, 48]} />
        <meshBasicMaterial color={tone === 'pending' ? COLORS.amber : COLORS.red} transparent opacity={0.8} side={THREE.DoubleSide} />
      </mesh>
      {burst && born && (
        <mesh ref={shock} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.08, 0]}>
          <ringGeometry args={[0.5, 0.62, 48]} />
          <meshBasicMaterial color="#fecaca" transparent side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      <pointLight ref={light} position={[0, 0.8, 0]} color={COLORS.red} intensity={3} distance={4} />
      <Html position={[0, 1.1, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
        <div ref={tag} className={`tag ${tone === 'pending' ? 'pending' : 'alert'}`}><b>{label}</b></div>
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

// When each survivor id first appeared in a list, so new ones pulse and fade calm.
function useBirths(ids) {
  const births = useRef(new Map())
  for (const id of births.current.keys()) if (!ids.includes(id)) births.current.delete(id) // reset
  for (const id of ids) if (!births.current.has(id)) births.current.set(id, performance.now())
  return births.current
}

export function RealityActors({ gap = false }) {
  const tick = useSim((s) => s.tick)
  const fp = useSim((s) => s.floorplan)
  const showTruth = useSim((s) => s.showTruth)
  const survivors_found = firstFinds(tick?.reality.survivors_found ?? [])
  const births = useBirths(survivors_found.map((s) => s.id))
  const reportedIds = (tick?.command.survivors ?? []).map((s) => s.id)
  const reportBirths = useBirths(reportedIds) // when Command learned each (gap view reveal)
  if (!tick || !fp) return null
  const { robots } = tick.reality
  const found = new Set(survivors_found.map((s) => s.id))
  return (
    <group>
      {robots.map((r) => (
        <group key={r.id}>
          <RobotBody pose={r.pose} color={r.color} label={r.name} sub={r.link.up ? null : 'no link'} linkUp={r.link.up} />
          <Lidar robot={r} />
          {r.path.length > 1 && (
            <Line points={[[r.pose[0], 0.06, -r.pose[1]], ...r.path.map(([px, py]) => [px, 0.06, -py])]}
                  color={r.color} lineWidth={1.2} dashed dashSize={0.25} gapSize={0.15} transparent opacity={0.45} />
          )}
        </group>
      ))}
      <RealityLinks />
      <RealityRelays />
      <RealityRoutes gap={gap} />
      {gap && <GapOverlay />}
      {survivors_found.map((s) => {
        if (!gap) return <Survivor key={s.id} id={s.id} pos={s.pos} label={`${s.id} found by ${s.by}`} born={births.get(s.id)} />
        const reported = reportedIds.includes(s.id)
        return reported
          ? <Survivor key={s.id} id={s.id} pos={s.pos} label={`${s.id} · reported to command`} born={reportBirths.get(s.id)} burst />
          : <Survivor key={s.id} id={s.id} pos={s.pos} label={`${s.id} · not reported yet`} tone="pending" hold />
      })}
      {showTruth && (fp.survivors ?? []).filter((s) => !found.has(s.id)).map((s) => (
        <TruthMarker key={s.id} pos={s.pos} id={s.id} />
      ))}
      {showTruth && (fp.decoys ?? []).map((d) => (
        <TruthMarker key={d.id} pos={d.pos} id={d.id} sub={`${d.label} · decoy`} color={COLORS.amber} decoy />
      ))}
    </group>
  )
}

// Gap view: a ghost where Command last heard from a dark robot, tied to the real robot.
const GHOST_AFTER_S = 3
function GapOverlay() {
  const tick = useSim((s) => s.tick)
  const time = useSim((s) => s.time)
  if (!tick) return null
  const real = Object.fromEntries(tick.reality.robots.map((r) => [r.id, r]))
  return tick.command.robots.filter((c) => time - c.last_seen > GHOST_AFTER_S && real[c.id]).map((c) => {
    const r = real[c.id]
    return (
      <group key={c.id}>
        <RobotBody pose={c.pose} color="#94a3b8" ghost headlight={false} label={c.id}
                   sub={`last report ${Math.round(time - c.last_seen)}s ago`} />
        <Line points={[w2t(c.pose[0], c.pose[1], 0.3), w2t(r.pose[0], r.pose[1], 0.3)]} color={COLORS.amber}
              lineWidth={1.5} dashed dashSize={0.35} gapSize={0.25} transparent opacity={0.75} />
      </group>
    )
  })
}

export function CommandActors() {
  const tick = useSim((s) => s.tick)
  const time = useSim((s) => s.time)
  const births = useBirths((tick?.command.survivors ?? []).map((s) => s.id)) // when Command first learned each
  if (!tick) return null
  const { robots, survivors } = tick.command
  return (
    <group>
      {robots.map((r) => {
        const stale = time - r.last_seen
        const ghost = stale > 3
        return (
          <RobotBody key={r.id} pose={r.pose} color={ghost ? '#94a3b8' : '#2dd4bf'} ghost={ghost}
                     headlight={false} label={r.id} sub={ghost ? `${stale.toFixed(0)}s ago` : null} />
        )
      })}
      <CommandRelays />
      <CommandRoutes />
      {survivors.map((s) => (
        <Survivor key={s.id} id={s.id} pos={s.pos} label={`${s.id} reported`} born={births.get(s.id)} burst />
      ))}
    </group>
  )
}
