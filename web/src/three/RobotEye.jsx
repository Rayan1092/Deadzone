import { useEffect, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Billboard } from '@react-three/drei'
import * as THREE from 'three'
import { FOCUS_HOLD_MS, useSim } from '../store'
import Building from './Building'
import { PersonFigure } from './Actors'
import Rover, { ROBOT_SCALE } from './Rover'
import { w2t } from './util'

// Picture-in-picture from a robot's forward camera (V key or the card's Camera
// button). Reality pane only: it shows what the robot's own camera sees. A third
// WebGL canvas, so it only exists while open and renders small at dpr 1.
// the camera head on the drawn rover (Rover.jsx, scaled): lens height and how far forward
const EYE_H = 0.56
const EYE_FWD = 0.36

// While the classifier's verdict is on screen the camera turns from straight ahead to
// the judged hot spot, then back.
function focusFor(robotId) {
  const f = useSim.getState().eyeFocus
  return f && f.robot === robotId && performance.now() - f.born < FOCUS_HOLD_MS ? f : null
}

function EyeCamera({ robotId }) {
  const { camera } = useThree()
  const look = useRef(new THREE.Vector3())
  const at = useRef(null)
  useFrame((_, dt) => {
    const r = useSim.getState().tick?.reality.robots.find((x) => x.id === robotId)
    if (!r) return
    const [x, y, th] = r.pose
    const goal = new THREE.Vector3(...w2t(x + Math.cos(th) * EYE_FWD, y + Math.sin(th) * EYE_FWD, EYE_H))
    const f = focusFor(robotId)
    const ahead = f
      ? new THREE.Vector3(...w2t(f.pos[0], f.pos[1], 0.2))
      : new THREE.Vector3(...w2t(x + Math.cos(th) * 2, y + Math.sin(th) * 2, EYE_H - 0.3))
    if (!at.current) { at.current = goal.clone(); look.current.copy(ahead) }
    const k = Math.min(1, dt * 8) // 10 Hz poses, smoothed to the frame rate
    at.current.lerp(goal, k)
    look.current.lerp(ahead, f ? Math.min(1, dt * 3) : k)
    camera.position.copy(at.current)
    camera.lookAt(look.current)
  })
  return null
}

// Hot spots as the camera sees them: survivors and decoys both glow in thermal,
// which is exactly why the onboard detector has to judge them. In thermal mode each one
// is the exact FLIR crop the detector scores (served at /crops), so this view and the
// AI card show the same image. A shape stands in if the crop is unavailable.
const loader = new THREE.TextureLoader()
const crops = new Map()
function cropTexture(name) {
  if (!crops.has(name)) {
    const tex = loader.load(`/crops/${name}`, undefined, undefined, () => crops.set(name, null))
    tex.colorSpace = THREE.SRGBColorSpace
    crops.set(name, tex)
  }
  return crops.get(name)
}

function ThermalCrop({ name, fallback }) {
  const tex = name ? cropTexture(name) : null
  if (!tex) return fallback
  return (
    <Billboard position={[0, 0.6, 0]}>
      <mesh>
        <planeGeometry args={[1.1, 1.1]} />
        <meshBasicMaterial map={tex} toneMapped={false} />
      </mesh>
    </Billboard>
  )
}

function HotSpots({ thermal }) {
  const fp = useSim((s) => s.floorplan)
  if (!fp) return null
  return (
    <group>
      {(fp.survivors ?? []).map((s) => (
        <group key={s.id} position={w2t(s.pos[0], s.pos[1], 0)}>
          {thermal ? (
            <ThermalCrop name={s.thermal} fallback={(
              <mesh position={[0, 0.15, 0]} scale={[1.4, 0.35, 0.6]}>
                <sphereGeometry args={[0.5, 16, 12]} />
                <meshBasicMaterial color="#fff1b8" />
              </mesh>
            )} />
          ) : <PersonFigure id={s.id} />}
        </group>
      ))}
      {(fp.decoys ?? []).map((d) => (
        <group key={d.id} position={w2t(d.pos[0], d.pos[1], 0)}>
          {thermal ? (
            <ThermalCrop name={d.thermal} fallback={(
              <mesh position={[0, 0.45, 0]}><boxGeometry args={[0.6, 0.9, 0.35]} /><meshBasicMaterial color="#ffb347" /></mesh>
            )} />
          ) : null /* the real object is part of the building's props */}
        </group>
      ))}
    </group>
  )
}

// Every robot in this camera is the same rover model as on the 3D map, at the same drawn
// scale, smoothed toward its streamed pose. The camera's own robot
// is left out: when the camera pans to a hot spot its own mast would fill the frame.
function EyeRover({ r, thermal }) {
  const g = useRef()
  const sensor = useRef()
  useFrame((_, dt) => {
    if (!g.current) return
    const [x, y, th] = r.pose
    g.current.position.lerp(new THREE.Vector3(...w2t(x, y, 0)), Math.min(1, dt * 10))
    let d = th - g.current.rotation.y
    d = Math.atan2(Math.sin(d), Math.cos(d))
    g.current.rotation.y += d * Math.min(1, dt * 10)
    if (sensor.current) sensor.current.rotation.y += dt * 6
  })
  return (
    <group ref={g} position={w2t(r.pose[0], r.pose[1], 0)} rotation={[0, r.pose[2], 0]}>
      <group scale={ROBOT_SCALE}>
        <Rover color={r.color} tag={r.id} thermal={thermal} sensor={sensor} linkUp={r.link?.up ?? true} />
      </group>
    </group>
  )
}

function Robots({ robotId, thermal }) {
  const robots = useSim((s) => s.tick?.reality.robots)
  return (robots ?? []).filter((r) => r.id !== robotId).map((r) => <EyeRover key={r.id} r={r} thermal={thermal} />)
}

// Screen box around the judged object: its known extent projected through the robot
// camera. The classifier scores a crop; it does not localize, so the box only marks the
// object that was judged.
const corner = new THREE.Vector3()
function FocusBox({ robotId, thermal, boxRef }) {
  const { camera, size } = useThree()
  useFrame(() => {
    const el = boxRef.current
    if (!el) return
    const f = focusFor(robotId)
    if (!f) { el.style.display = 'none'; return }
    const person = f.kind === 'person'
    const r = thermal ? 0.55 : person ? 0.85 : 0.6
    const [y0, y1] = thermal ? [0.05, 1.15] : person ? [0, 0.45] : [0, 1.1]
    let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity
    let behind = false
    for (const dx of [-r, r]) for (const dz of [-r, r]) for (const y of [y0, y1]) {
      corner.set(f.pos[0] + dx, y, -(f.pos[1] + dz)).project(camera)
      if (corner.z > 1) behind = true
      x0 = Math.min(x0, corner.x); x1 = Math.max(x1, corner.x)
      z0 = Math.min(z0, corner.y); z1 = Math.max(z1, corner.y)
    }
    if (behind || x1 < -1 || x0 > 1) { el.style.display = 'none'; return }
    const clamp = (v) => Math.max(-1, Math.min(1, v))
    const left = ((clamp(x0) + 1) / 2) * size.width
    const right = ((clamp(x1) + 1) / 2) * size.width
    const top = ((1 - clamp(z1)) / 2) * size.height
    const bottom = ((1 - clamp(z0)) / 2) * size.height
    el.style.display = ''
    el.style.transform = `translate(${left}px, ${top}px)`
    el.style.width = `${Math.max(24, right - left)}px`
    el.style.height = `${Math.max(24, bottom - top)}px`
  })
  return null
}

const pct = (c) => `${(c * 100).toFixed(c > 0 && c < 0.01 ? 1 : 0)}%`

// What the robot does next, ticked off only by real events (never assumed).
function steps(f, events) {
  if (f.kind === 'decoy') {
    return [
      { done: true, text: 'Hot spot found on the thermal camera' },
      { done: true, text: `Onboard classifier: not a person (${pct(f.conf ?? 0)})` },
      { done: true, text: 'Rejected · keeps exploring' },
    ]
  }
  const mine = (e) => e.survivor === f.subject
  const route = events.find((e) => e.kind === 'rescue_route' && mine(e))
  const beacon = events.find((e) => e.kind === 'relay_dropped' && e.beacon_for === f.subject)
  const reported = events.find((e) => e.kind === 'survivor_reported' && mine(e))
  const out = [
    { done: true, text: `Person detected · ${pct(f.conf ?? 1)} (onboard classifier)` },
    { done: true, text: `Location marked · ${f.pos[0].toFixed(1)}, ${f.pos[1].toFixed(1)} m` },
    { done: !!route, text: route ? `Rescue route planned · ${Math.round(route.length_m)} m` : 'Planning rescue route…' },
  ]
  if (beacon) out.push({ done: true, text: `No signal: beacon ${beacon.id} dropped next to them` })
  else if (!f.linked && !reported) out.push({ done: false, text: 'No signal: holding the report' })
  out.push({ done: !!reported, text: reported ? `Report reached command (${reported.delay_s}s)` : 'Sending report to command…' })
  return out
}

function FocusPanel({ robotId, boxRef }) {
  const f = useSim((s) => (s.eyeFocus?.robot === robotId ? s.eyeFocus : null))
  const events = useSim((s) => s.events)
  const [, tick] = useState(0)
  useEffect(() => {
    if (!f) return
    const id = setTimeout(() => tick((n) => n + 1), Math.max(0, f.born + FOCUS_HOLD_MS - performance.now()) + 50)
    return () => clearTimeout(id)
  }, [f])
  const live = f && performance.now() - f.born < FOCUS_HOLD_MS
  const person = f?.kind === 'person'
  return (
    <>
      <div ref={boxRef} className={`eye-box ${person ? 'person' : 'decoy'}`} style={{ display: 'none' }}>
        {f && (
          <span className="eye-box-label">
            {person ? `PERSON ${pct(f.conf ?? 1)}` : `NOT A PERSON ${pct(f.conf ?? 0)}`}
            <small>{person ? 'onboard AI' : 'rejected'}</small>
          </span>
        )}
      </div>
      {live && (
        <ol className={`eye-steps ${person ? 'person' : 'decoy'}`}>
          {steps(f, events).map((st, i) => (
            <li key={i} className={st.done ? 'done' : 'wait'}><i />{st.text}</li>
          ))}
        </ol>
      )}
    </>
  )
}

export default function RobotEye() {
  const robotId = useSim((s) => s.eyeRobot)
  const thermal = useSim((s) => s.eyeThermal)
  const meta = useSim((s) => s.robotsMeta.find((r) => r.id === s.eyeRobot))
  const set = useSim((s) => s.set)
  const focused = useSim((s) => s.eyeFocus?.robot === s.eyeRobot && s.eyeFocus)
  const [, rerender] = useState(0)
  const boxRef = useRef()
  // grow while a verdict is on screen, then shrink back to the corner
  const live = focused && performance.now() - focused.born < FOCUS_HOLD_MS
  useEffect(() => {
    if (!live) return
    const id = setTimeout(() => rerender((n) => n + 1), Math.max(0, focused.born + FOCUS_HOLD_MS - performance.now()) + 50)
    return () => clearTimeout(id)
  }, [live, focused])
  if (!robotId) return null
  return (
    <div className={`robot-eye${thermal ? ' thermal' : ''}${live ? ' focus' : ''}`}>
      <div className="eye-head">
        <i className="swatch" style={{ background: meta?.color }} />
        <b>{meta?.name ?? robotId} camera</b>
        <button className={`eye-toggle${thermal ? ' on' : ''}`} onClick={() => set({ eyeThermal: !thermal })}>Thermal</button>
        <button className="eye-close" aria-label="Close camera" onClick={() => set({ eyeRobot: null })}>×</button>
      </div>
      <Canvas dpr={1} camera={{ fov: 75, near: 0.05, far: 60 }} gl={{ antialias: false, powerPreference: 'low-power' }}>
        <color attach="background" args={[thermal ? '#030614' : '#0e1114']} />
        {thermal ? <ambientLight intensity={0.6} /> : (
          <>
            <ambientLight intensity={0.7} />
            <hemisphereLight args={['#e2e8f0', '#1f2937', 1.4]} />
          </>
        )}
        {!thermal && <fog attach="fog" args={['#0e1114', 8, 26]} />}
        <Building thermal={thermal} />
        <HotSpots thermal={thermal} />
        <Robots robotId={robotId} thermal={thermal} />
        <EyeCamera robotId={robotId} />
        <FocusBox robotId={robotId} thermal={thermal} boxRef={boxRef} />
      </Canvas>
      <FocusPanel robotId={robotId} boxRef={boxRef} />
      <span className="eye-note">
        {live ? 'Box marks the hot spot the onboard classifier judged from its thermal crop'
          : thermal ? 'Thermal: walls cold, people and hot objects glow' : 'Forward camera'}
      </span>
    </div>
  )
}
