import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line } from '@react-three/drei'
import * as THREE from 'three'
import { useSim } from '../store'
import { COLORS, FOG_H, w2t } from './util'
import { materials, tiledSet } from './textures'
import { ROBOT_SCALE } from './Rover'
import RoverModel from './RoverModel'
import Human from './Human'
import { LightBeam } from './NightLights'
import { CommandRelays, RealityLinks, RealityRelays } from './Network'
import { CommandRoutes, RealityRoutes } from './Routes'

// --------------------------------------------------------------- robot body
// At night (K) the headlights are the main light in the building, with a visible beam.
const BEAM_Q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, -1, 0), new THREE.Vector3(1, -0.12, 0).normalize())
function Headlight() {
  // the target must live in the scene graph or three.js never updates its matrix
  const tgt = useMemo(() => new THREE.Object3D(), [])
  const night = useSim((s) => s.night)
  return (
    <>
      <primitive object={tgt} position={[3, 0, 0]} />
      <spotLight position={[0.3, 0.3, 0]} angle={night ? 0.6 : 0.7} penumbra={0.55} intensity={night ? 22 : 6}
                 distance={night ? 13 : 7} decay={1.5} color="#cffaf5" target={tgt} />
      {night && <group position={[0.26, 0.14, 0]} quaternion={BEAM_Q}><LightBeam length={3.2} radius={1.2} color="#d9fbff" opacity={0.06} /></group>}
    </>
  )
}


function RobotBody({ pose, color, tag, ghost = false, label, sub, headlight = true, linkUp = true }) {
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
        <RoverModel color={color} tag={tag} ghost={ghost} sensor={sensor} linkUp={linkUp} />
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

// Debris pinning the legs: a broken slab and a few chunks (they are trapped, which is why
// they need rescuing rather than walking out).
let pinMats = null
function Pinned() {
  pinMats ??= {
    slab: new THREE.MeshStandardMaterial({ ...tiledSet(materials().concrete, 0.5, 0.5), color: '#a8a299', roughness: 0.93 }),
    rock: new THREE.MeshStandardMaterial({ color: '#8f887e', roughness: 0.95, flatShading: true }),
  }
  return (
    <group>
      <mesh position={[-0.5, 0.2, 0]} rotation={[0.15, 0.3, 0.32]} material={pinMats.slab} castShadow receiveShadow>
        <boxGeometry args={[0.62, 0.08, 0.6]} />
      </mesh>
      {[[-0.18, 0.06, 0.24, 0.07], [-0.8, 0.05, -0.28, 0.06], [-0.35, 0.05, -0.3, 0.05], [-0.72, 0.07, 0.3, 0.08], [-0.25, 0.32, 0.05, 0.05]].map(([x, yy, z, s], i) => (
        <mesh key={i} position={[x, yy, z]} rotation={[i, i * 2, i * 3]} material={pinMats.rock} castShadow>
          <dodecahedronGeometry args={[s, 0]} />
        </mesh>
      ))}
    </group>
  )
}

export function PersonFigure({ id }) {
  // true scale: drawn bigger, their legs and glow reached under robots passing 2 m away
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.012, 0]}>
        <circleGeometry args={[0.95, 32]} />
        <meshBasicMaterial color="#ff5a1f" transparent opacity={0.16} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <Human id={id} angle={lieAngle(id)} />
      <group rotation={[0, lieAngle(id), 0]} scale={1.3}><Pinned /></group>
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

// --------------------------------------------------------------- aftershock
// The world shakes for a moment when an aftershock hits (Reality panes only: it is truth),
// and a dust cloud billows out of the collapse and settles.
const SHAKE_S = 1.4
const DUST_S = 6
export function Shake({ children }) {
  const ref = useRef()
  useFrame(() => {
    const g = ref.current
    const a = useSim.getState().aftershock
    if (!g) return
    const age = a ? (performance.now() - a.born) / 1000 : Infinity
    if (age > SHAKE_S) { if (g.position.lengthSq()) g.position.set(0, 0, 0); return }
    const k = 0.22 * (1 - age / SHAKE_S) ** 2
    const t = age * 40
    g.position.set(Math.sin(t * 1.3) * k, Math.abs(Math.sin(t * 0.9)) * k * 0.4, Math.cos(t * 1.7) * k)
  })
  return <group ref={ref}>{children}</group>
}

function AftershockDust() {
  const a = useSim((s) => s.aftershock)
  const group = useRef()
  const puffs = useMemo(() => Array.from({ length: 16 }, (_, i) => ({
    ang: (i / 16) * Math.PI * 2 + (i % 3) * 0.4, dist: 0.6 + (i % 4) * 0.5, h: 0.4 + (i % 5) * 0.35, s: 1.6 + (i % 3) * 0.8,
  })), [])
  useFrame(() => {
    if (!group.current || !a) return
    const age = (performance.now() - a.born) / 1000
    group.current.visible = age < DUST_S
    const k = Math.min(1, age / 1.2)
    group.current.children.forEach((sp, i) => {
      const p = puffs[i]
      const r = p.dist * (0.4 + k * 1.6)
      sp.position.set(Math.cos(p.ang) * r, p.h * (0.5 + k), Math.sin(p.ang) * r)
      sp.scale.setScalar(p.s * (0.5 + k))
      sp.material.opacity = 0.55 * (1 - age / DUST_S)
    })
  })
  if (!a) return null
  return (
    <group ref={group} position={w2t(a.at[0], a.at[1], 0)}>
      {puffs.map((p, i) => (
        <sprite key={i}>
          <spriteMaterial map={materials().puff} color="#a89b88" transparent opacity={0} depthWrite={false} />
        </sprite>
      ))}
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
          <RobotBody pose={r.pose} color={r.color} tag={r.id} label={r.name} sub={r.link.up ? null : 'no link'} linkUp={r.link.up} />
          <Lidar robot={r} />
          {r.path.length > 1 && (
            <Line points={[[r.pose[0], 0.06, -r.pose[1]], ...r.path.map(([px, py]) => [px, 0.06, -py])]}
                  color={r.color} lineWidth={1.2} dashed dashSize={0.25} gapSize={0.15} transparent opacity={0.45} />
          )}
        </group>
      ))}
      <AftershockDust />
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
          <RobotBody key={r.id} pose={r.pose} color={ghost ? '#94a3b8' : '#2dd4bf'} tag={r.id} ghost={ghost}
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
