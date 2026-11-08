import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import Line from './FastLine' // drei's Line relinks its shader on every new points array
import * as THREE from 'three'
import { useSim, useStable } from '../store'
import { COLORS, FOG_H, w2t } from './util'
import { decoyLayout } from './furniture'
import { materials, tiledSet } from './textures'
import { ROBOT_SCALE } from './Rover'
import RoverModel from './RoverModel'
import Human from './Human'
import { SeatChair } from './Props'
import { cropEntry, useCropManifest } from '../crops'
import { planCaption, robotTag } from '../format'
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


function RobotBody({ pose, color, tag, ghost = false, label, sub, headlight = true, linkUp = true, powered = true, dark = false }) {
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
    if (sensor.current && !ghost && powered) sensor.current.rotation.y += dt * 6
  })

  return (
    <group ref={group} position={target.current.toArray()}>
      <group scale={ROBOT_SCALE}>
        {!ghost && powered && (
          // colored pool of light under the robot so it reads from across the room
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.012, 0]}>
            <circleGeometry args={[0.42, 32]} />
            <meshBasicMaterial color={color} transparent opacity={0.22} blending={THREE.AdditiveBlending} depthWrite={false} />
          </mesh>
        )}
        <RoverModel color={color} tag={tag} ghost={ghost} sensor={sensor} linkUp={linkUp} powered={powered} />
        {!ghost && headlight && powered && !perf && <Headlight />}
      </group>
      {label && (
        <Html position={[0, 0.8 * ROBOT_SCALE, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
          <div className={ghost ? 'tag ghost' : dark ? 'tag nolink' : 'tag'} style={ghost || dark ? undefined : { borderColor: color }}>
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

// The survivor as the real crop shows them (the crop manifest's `pose`, or the floor plan's own
// `pose`): crouched, kneeling bent over, slumped in a chair, else lying pinned under a slab.
// Plain props lit like the rest of the scene: no glow, ring or light (Reality and the robot camera).
const POSE_OF = { crouching: 'crouching', crouched: 'crouching', bent: 'kneeling', kneeling: 'kneeling', sitting: 'sitting', slumped: 'sitting', lying: 'lying' }
export function survivorPose(s, manifest) {
  return POSE_OF[s?.pose ?? cropEntry(manifest, s?.thermal)?.pose] ?? 'lying'
}
export function SurvivorFigure({ id, pose = 'lying' }) {
  return (
    <group rotation={[0, lieAngle(id), 0]}>
      {pose === 'sitting' && <SeatChair />}
      <Human id={id} pose={pose} />
      {pose === 'lying' && <group scale={1.3}><Pinned /></group>}
    </group>
  )
}

// Reality: every survivor is in the building from sim 0 (it's truth); a plain tag when a robot
// finds them (and in one view, whether Command has the report yet). No rings, glow or pulse.
function RealitySurvivor({ id, pos, pose, tag }) {
  const el = useRef()
  useFrame(() => {
    if (!el.current) return
    const age = tag?.born ? (performance.now() - tag.born) / 1000 : SETTLE_S
    el.current.style.display = tag && (tag.hold || age < SETTLE_S) ? '' : 'none'
  })
  return (
    <group position={w2t(pos[0], pos[1], 0)}>
      <SurvivorFigure id={id} pose={pose} />
      {tag && (
        <Html position={[0, 1.35, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
          <div ref={el} className={`tag ${tag.tone === 'pending' ? 'pending' : 'alert'}`}><b>{tag.label}</b></div>
        </Html>
      )}
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


function rng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}

// --------------------------------------------------------------- aftershock
// The world shakes for a moment when an aftershock hits (Reality panes only: it is truth),
// and a dust cloud billows out of the collapse and settles.
const SHAKE_S = 5.2   // Rayan's earthquake v2: 4 to 6 s of shake
const DUST_S = 9
export function Shake({ children }) {
  const ref = useRef()
  useFrame(() => {
    const g = ref.current
    const a = useSim.getState().aftershock
    if (!g) return
    const age = a ? (performance.now() - a.born) / 1000 : Infinity
    const len = a?.shakeS ?? SHAKE_S // a secondary collapse shakes shorter and softer than an aftershock
    if (age > len) { if (g.position.lengthSq()) g.position.set(0, 0, 0); return }
    // hits hard in the first half second, then rumbles out; two frequencies so it never loops
    const k = 0.26 * (a.k ?? 1) * Math.min(1, age * 3) * (1 - age / len) ** 1.6
    const t = age * 40
    g.position.set(Math.sin(t * 1.3) * k + Math.sin(t * 0.37) * k * 0.5, Math.abs(Math.sin(t * 0.9)) * k * 0.35, Math.cos(t * 1.7) * k + Math.cos(t * 0.29) * k * 0.5)
  })
  return <group ref={ref}>{children}</group>
}

function AftershockDust() {
  const a = useSim((s) => s.aftershock)
  const group = useRef()
  const puffs = useMemo(() => Array.from({ length: 26 }, (_, i) => ({
    ang: (i / 26) * Math.PI * 2 + (i % 3) * 0.4, dist: 0.6 + (i % 5) * 0.6, h: 0.4 + (i % 5) * 0.4, s: 1.8 + (i % 3) * 0.9,
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
      sp.scale.setScalar(p.s * (0.5 + k * 0.8))
      sp.material.opacity = 0.3 * (1 - age / DUST_S)
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

// Ceiling slabs and chunks that come down with the aftershock: they fall from roof height
// onto the new rubble footprint in the first second, bounce once and stay as debris.
const SLAB_FALL_S = 0.9
function AftershockSlabs() {
  const a = useSim((s) => s.aftershock)
  const group = useRef()
  const pieces = useMemo(() => {
    if (!a) return []
    const r = rng(Math.round(a.at[0] * 31 + a.at[1] * 17) + 11)
    const out = []
    for (let i = 0; i < 4; i++) {
      out.push({ slab: true, x: a.at[0] + (r() - 0.5) * 1.6, y: a.at[1] + (r() - 0.5) * 1.6, h0: 3.0 + r() * 1.2, rest: 0.25 + i * 0.16,
        size: [0.9 + r() * 0.9, 0.16, 0.7 + r() * 0.8], rot: [(r() - 0.5) * 0.8, r() * Math.PI, (r() - 0.5) * 0.8], delay: r() * 0.35, spin: (r() - 0.5) * 2 })
    }
    for (let i = 0; i < 14; i++) {
      out.push({ slab: false, x: a.at[0] + (r() - 0.5) * 3.2, y: a.at[1] + (r() - 0.5) * 3.2, h0: 2.6 + r() * 1.5, rest: 0.06 + r() * 0.3,
        size: [0.12 + r() * 0.25, 0.1 + r() * 0.2, 0.12 + r() * 0.25], rot: [r() * 6, r() * 6, r() * 6], delay: r() * 0.6, spin: (r() - 0.5) * 6 })
    }
    return out
  }, [a])
  useFrame(() => {
    if (!group.current || !a) return
    const age = (performance.now() - a.born) / 1000
    group.current.children.forEach((m, i) => {
      const p = pieces[i]
      const t = Math.max(0, age - p.delay)
      const fall = p.h0 - 0.5 * 9.81 * t * t * 1.6 // a little faster than g: the drop is seen from far away
      let h = Math.max(p.rest, fall)
      if (fall < p.rest && t < SLAB_FALL_S + 0.5) h = p.rest + Math.max(0, 0.18 * Math.sin((t - Math.sqrt((p.h0 - p.rest) / (0.5 * 9.81 * 1.6))) * 9)) * (p.slab ? 1 : 0.5)
      m.position.set(p.x, h, -p.y)
      const k = Math.min(1, t / SLAB_FALL_S)
      m.rotation.set(p.rot[0] * k, p.rot[1] + p.spin * k, p.rot[2] * k)
      m.visible = t > 0
    })
  })
  if (!a) return null
  const mat = slabMats()
  return (
    <group ref={group}>
      {pieces.map((p, i) => (
        <mesh key={i} material={p.slab ? mat.slab : mat.rock} castShadow>
          <boxGeometry args={p.size} />
        </mesh>
      ))}
    </group>
  )
}
let slabCache = null
function slabMats() {
  slabCache ??= {
    slab: new THREE.MeshStandardMaterial({ ...tiledSet(materials().rubble, 0.6, 0.6), color: '#b9b2a8', roughness: 0.93 }),
    rock: new THREE.MeshStandardMaterial({ ...tiledSet(materials().rubble, 1, 1), color: '#9d968c', roughness: 0.96 }),
  }
  return slabCache
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
  const survivors_found = firstFinds(tick?.reality.survivors_found ?? [])
  const births = useBirths(survivors_found.map((s) => s.id))
  const reportedIds = (tick?.command.survivors ?? []).map((s) => s.id)
  const reportBirths = useBirths(reportedIds) // when Command learned each (gap view reveal)
  const manifest = useCropManifest()
  const dispatched = useSim((s) => s.dispatchedPlans)
  const plan = useSim((s) => s.plan)
  const zoneSeen = useRef(new Map()) // robot -> { key: plan|zone, at }: a new zone gets a short caption
  if (!tick || !fp) return null
  const now = performance.now()
  // the line under the robot's label: holding, plan not delivered yet, then for 8 s after it
  // starts a zone "Scout 2 → Zone 3"; plain words, no glow
  const caption = (r) => {
    const key = `${r.plan_id}|${r.zone}`
    const seen = zoneSeen.current.get(r.id)
    if (!seen || seen.key !== key) zoneSeen.current.set(r.id, { key, at: seen ? now : -Infinity }) // not on page load
    if (r.state === 'SHUTDOWN') return null // the label says it
    const c = planCaption(r, { dispatched, plan })
    if (c?.kind === 'holding' || c?.kind === 'pending') return c.text
    if (c?.kind === 'zone' && now - zoneSeen.current.get(r.id).at < 8000) return c.text // "Scout 2 → Zone 3"
    return null // dark: the label says NO LINK
  }
  const { robots } = tick.reality
  const foundBy = new Map(survivors_found.map((s) => [s.id, s]))
  const cmdById = Object.fromEntries(tick.command.robots.map((c) => [c.id, c]))
  const simTime = useSim.getState().time // updates with every tick, like this component
  const tags = Object.fromEntries(robots.map((r) => [r.id, robotTag(r, cmdById[r.id], simTime)]))
  return (
    <group>
      {robots.map((r) => (
        <group key={r.id}>
          {/* Rayan's SHUTDOWN: back at command, powered down (lights, lidar and camera off) */}
          <RobotBody pose={r.pose} color={r.color} tag={r.id} linkUp={r.link.up} powered={r.lights !== false}
                     label={tags[r.id].text} dark={tags[r.id].dark} sub={caption(r)} />
          {r.lights !== false && <Lidar robot={r} />}
          {r.path.length > 1 && (
            <Line points={[[r.pose[0], 0.06, -r.pose[1]], ...r.path.map(([px, py]) => [px, 0.06, -py])]}
                  color={r.color} lineWidth={1.2} dashed dashSize={0.25} gapSize={0.15} transparent opacity={0.45} />
          )}
        </group>
      ))}
      <AftershockDust />
      <AftershockSlabs />
      <RealityLinks />
      <RealityRelays />
      <RealityRoutes gap={gap} />
      {gap && <GapOverlay />}
      {(fp.survivors ?? []).map((s) => {
        const f = foundBy.get(s.id)
        const tag = !f ? null : !gap ? { label: `${s.id} found by ${f.by}`, born: births.get(s.id) }
          : reportedIds.includes(s.id) ? { label: `${s.id} · reported to command`, born: reportBirths.get(s.id) }
            : { label: `${s.id} · not reported yet`, tone: 'pending', hold: true }
        return <RealitySurvivor key={s.id} id={s.id} pos={s.pos} pose={survivorPose(s, manifest)} tag={tag} />
      })}
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

// What the Command pane draws, as a key that changes only when the picture would: robot poses,
// ghost or live, the whole seconds on a ghost's "Ns ago" tag, and the survivors. Re-rendering on
// every tick redrew the (on-demand) Command canvas about 25 times a second for nothing.
function commandView(s) {
  const c = s.tick?.command
  if (!c) return null
  return {
    robots: c.robots.map((r) => {
      const stale = s.time - r.last_seen
      return { id: r.id, pose: r.pose, ghost: stale > 3, ago: stale > 3 ? Math.floor(stale) : null,
        color: s.robotsMeta.find((m) => m.id === r.id)?.color ?? '#2dd4bf' }
    }),
    survivors: c.survivors.map((v) => ({ id: v.id, pos: v.pos })),
  }
}

export function CommandActors() {
  const view = useStable(commandView)
  const births = useBirths((view?.survivors ?? []).map((s) => s.id)) // when Command first learned each
  if (!view) return null
  const { robots, survivors } = view
  return (
    <group>
      {robots.map((r) => (
        <RobotBody key={r.id} pose={r.pose} color={r.ghost ? '#94a3b8' : r.color} tag={r.id} ghost={r.ghost}
                   headlight={false} label={r.id} sub={r.ghost ? `${r.ago}s ago` : null} />
      ))}
      <CommandRelays />
      <CommandRoutes />
      {survivors.map((s) => (
        <Survivor key={s.id} id={s.id} pos={s.pos} label={`${s.id} reported`} born={births.get(s.id)} burst />
      ))}
    </group>
  )
}
