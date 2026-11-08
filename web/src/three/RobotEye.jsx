import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Billboard } from '@react-three/drei'
import * as THREE from 'three'
import { FOCUS_HOLD_MS, useSim } from '../store'
import { AI_CAPTION } from '../format'
import { useCropManifest } from '../crops'
import Building from './Building'
import { PersonFigure } from './Actors'
import { ROBOT_SCALE } from './Rover'
import RoverModel from './RoverModel'
import { w2t } from './util'
import { decoyLayout } from './furniture'

// Picture-in-picture from a robot's forward camera (V key or the card's Camera
// button). Reality pane only: it shows what the robot's own camera sees. A third
// WebGL canvas, so it only exists while open and renders small at dpr 1.
// the camera head on the drawn rover (Rover.jsx, scaled): lens height and how far forward
const EYE_H = 0.56
const EYE_FWD = 0.36

function EyeCamera({ robotId }) {
  const { camera } = useThree()
  const look = useRef(new THREE.Vector3())
  const at = useRef(null)
  // the robot's own headlight rides with the camera: at night it is what lights the view
  const lamp = useRef()
  const lampTarget = useMemo(() => new THREE.Object3D(), [])
  useFrame((_, dt) => {
    const r = useSim.getState().tick?.reality.robots.find((x) => x.id === robotId)
    if (!r) return
    const [x, y, th] = r.pose
    const goal = new THREE.Vector3(...w2t(x + Math.cos(th) * EYE_FWD, y + Math.sin(th) * EYE_FWD, EYE_H))
    // a chassis-mounted camera: it always looks where the robot is heading
    const ahead = new THREE.Vector3(...w2t(x + Math.cos(th) * 2, y + Math.sin(th) * 2, EYE_H - 0.3))
    if (!at.current) { at.current = goal.clone(); look.current.copy(ahead) }
    const k = Math.min(1, dt * 8) // 10 Hz poses, smoothed to the frame rate
    at.current.lerp(goal, k)
    look.current.lerp(ahead, k)
    camera.position.copy(at.current)
    camera.lookAt(look.current)
    if (lamp.current) { lamp.current.position.copy(at.current); lampTarget.position.copy(look.current) }
  })
  return (
    <>
      <primitive object={lampTarget} />
      <spotLight ref={lamp} target={lampTarget} angle={0.62} penumbra={0.5} intensity={14} distance={16} decay={1.5} color="#e8fbff" />
    </>
  )
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
      {decoyLayout(fp).map((d) => (
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
        <RoverModel color={r.color} tag={r.id} thermal={thermal} sensor={sensor} linkUp={r.link?.up ?? true} />
      </group>
    </group>
  )
}

function Robots({ robotId, thermal }) {
  const robots = useSim((s) => s.tick?.reality.robots)
  return (robots ?? []).filter((r) => r.id !== robotId).map((r) => <EyeRover key={r.id} r={r} thermal={thermal} />)
}

// Every warm object in this camera's view gets a box: the hot spots the thermal camera
// passes to the onboard person classifier (survivors and decoys). The score is the model's
// output for that object's real FLIR crop (/crops/manifest.json, the same crops the robot
// scores). Within the thermal camera's 5 m range it is judged; farther away it is only
// "warm". Cold things (walls, furniture, debris) never reach the classifier. Hidden
// behind a wall or rubble = not boxed. The classifier scores crops, it doesn't localize:
// the box is the object's known extent projected through this camera.
const THERMAL_RANGE = 5   // m, matches the sim's thermal camera
// Rayan's look-closer: a score in [0.35, 0.75) from afar is unsure when a close-up crop
// (<crop>_close.png) exists; within 2 m the close-up is what gets judged
const UNSURE = [0.35, 0.75]
const CLOSE_LOOK_M = 2
const MAX_BOXES = 6

// 2D segment intersection, for line of sight against walls and rubble edges.
function crosses([ax, ay], [bx, by], [cx, cy], [dx, dy]) {
  const d = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
  if (Math.abs(d) < 1e-9) return false
  const t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / d
  const u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / d
  return t > 0.02 && t < 0.98 && u >= 0 && u <= 1
}
function blockers(fp) {
  const segs = [...fp.walls, ...(fp.dynamic_walls ?? [])].map((w) => [w.a, w.b])
  for (const rb of fp.rubble ?? []) rb.poly.forEach((p, i) => segs.push([p, rb.poly[(i + 1) % rb.poly.length]]))
  return segs
}

// Drives the on-demand robot camera canvas at a fixed rate.
function EyeRate({ fps }) {
  const invalidate = useThree((s) => s.invalidate)
  useEffect(() => {
    const id = setInterval(() => invalidate(), 1000 / fps)
    return () => clearInterval(id)
  }, [invalidate, fps])
  return null
}

const corner = new THREE.Vector3()
function ClassifyBoxes({ robotId, thermal, boxes }) {
  const { camera, size } = useThree()
  const fp = useSim((s) => s.floorplan)
  const m = useCropManifest()
  const segs = useMemo(() => (fp ? blockers(fp) : []), [fp])
  const objects = useMemo(() => {
    if (!fp) return []
    const score = Object.fromEntries((m?.crops ?? []).map((c) => [c.file, c.conf]))
    const threshold = m?.threshold ?? 0.6
    return [...(fp.survivors ?? []), ...decoyLayout(fp)].map((o) => ({ // decoys where their model is drawn
      ...o, conf: score[o.thermal], threshold, lying: !o.label,
      closeConf: o.thermal ? score[o.thermal.replace(/\.png$/, '_close.png')] : undefined,
    }))
  }, [fp, m])
  useFrame(() => {
    const r = useSim.getState().tick?.reality.robots.find((x) => x.id === robotId)
    let used = 0
    if (r) {
      const eye = [r.pose[0], r.pose[1]]
      for (const o of objects) {
        if (used >= MAX_BOXES) break
        const dist = Math.hypot(o.pos[0] - eye[0], o.pos[1] - eye[1])
        if (dist > 16 || segs.some(([a, b]) => crosses(eye, o.pos, a, b))) continue
        const rx = thermal ? 0.55 : o.lying ? 0.85 : 0.6
        const [y0, y1] = thermal ? [0.05, 1.15] : o.lying ? [0, 0.5] : [0, 1.1]
        let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity, behind = false
        for (const dx of [-rx, rx]) for (const dz of [-rx, rx]) for (const y of [y0, y1]) {
          corner.set(o.pos[0] + dx, y, -(o.pos[1] + dz)).project(camera)
          if (corner.z > 1) behind = true
          x0 = Math.min(x0, corner.x); x1 = Math.max(x1, corner.x)
          z0 = Math.min(z0, corner.y); z1 = Math.max(z1, corner.y)
        }
        if (behind || x1 < -0.98 || x0 > 0.98 || z1 < -0.98 || z0 > 0.98) continue
        const el = boxes.current[used++]
        if (!el) continue
        const clamp = (v) => Math.max(-1, Math.min(1, v))
        const left = ((clamp(x0) + 1) / 2) * size.width
        const right = ((clamp(x1) + 1) / 2) * size.width
        const top = ((1 - clamp(z1)) / 2) * size.height
        const bottom = ((1 - clamp(z0)) / 2) * size.height
        const judged = dist <= THERMAL_RANGE && o.conf != null
        const close = o.closeConf != null && dist <= CLOSE_LOOK_M
        const conf = close ? o.closeConf : o.conf
        const unsure = judged && !close && o.closeConf != null && conf >= UNSURE[0] && conf < UNSURE[1]
        const person = conf >= o.threshold
        const kind = !judged ? 'warm' : unsure ? 'unsure' : person ? 'person' : 'decoy'
        el.className = `eye-box ${kind}`
        el.style.display = ''
        el.style.transform = `translate(${left}px, ${top}px)`
        el.style.width = `${Math.max(20, right - left)}px`
        el.style.height = `${Math.max(20, bottom - top)}px`
        const label = el.firstChild
        const text = !judged ? `WARM · ${dist.toFixed(0)} m · come closer to classify`
          : unsure ? `UNSURE ${pct(conf)}` : `${person ? 'PERSON' : 'NOT A PERSON'} ${pct(conf)}`
        const sub = !judged ? '' : unsure ? 'onboard AI · moving closer'
          : `onboard AI${close ? ' · up close' : ''}${person ? '' : ' · rejected'}`
        if (label.dataset.t !== text + sub) {
          label.dataset.t = text + sub
          label.innerHTML = sub ? `${text}<small>${sub}</small>` : text
        }
      }
    }
    for (let i = used; i < MAX_BOXES; i++) if (boxes.current[i]) boxes.current[i].style.display = 'none'
  })
  return null
}

const pct = (c) => `${(c * 100).toFixed(c > 0 && c < 0.01 ? 1 : 0)}%`

// What the robot does next, ticked off only by real events (never assumed).
function steps(f, events) {
  if (f.kind === 'unsure') {
    return [
      { done: true, text: 'Hot spot found on the thermal camera' },
      { done: true, text: `Onboard classifier unsure (${pct(f.conf ?? 0)})` },
      { done: false, text: 'Driving closer for a second look…' },
    ]
  }
  // decided after a close look: say where the doubt was and what the close-up said
  const second = f.confFar != null
    ? [{ done: true, text: f.closer ? `Unsure from afar (${pct(f.confFar)}) · judged again up close` : `Unsure from afar (${pct(f.confFar)}) · could not get close` }]
    : []
  if (f.kind === 'decoy') {
    return [
      { done: true, text: 'Hot spot found on the thermal camera' },
      ...second,
      { done: true, text: `Onboard classifier: not a person (${pct(f.conf ?? 0)})` },
      { done: true, text: 'Rejected · keeps exploring' },
    ]
  }
  const mine = (e) => e.survivor === f.subject
  const route = events.find((e) => e.kind === 'rescue_route' && mine(e))
  const beacon = events.find((e) => e.kind === 'relay_dropped' && e.beacon_for === f.subject)
  const reported = events.find((e) => e.kind === 'survivor_reported' && mine(e))
  const out = [
    ...second,
    { done: true, text: `Person detected · ${pct(f.conf ?? 1)} (onboard classifier)` },
    { done: true, text: `Location marked · ${f.pos[0].toFixed(1)}, ${f.pos[1].toFixed(1)} m` },
    { done: !!route, text: route ? `Rescue route planned · ${Math.round(route.length_m)} m` : 'Planning rescue route…' },
  ]
  if (beacon) out.push({ done: true, text: `No signal: beacon ${beacon.id} dropped next to them` })
  else if (!f.linked && !reported) out.push({ done: false, text: 'No signal: holding the report' })
  out.push({ done: !!reported, text: reported ? `Report reached command (${reported.delay_s}s)` : 'Sending report to command…' })
  return out
}

function FocusPanel({ robotId }) {
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
      {live && (
        <ol className={`eye-steps ${person ? 'person' : f.kind === 'unsure' ? 'unsure' : 'decoy'}`}>
          {steps(f, events).map((st, i) => (
            <li key={i} className={st.done ? 'done' : 'wait'}><i />{st.text}</li>
          ))}
        </ol>
      )}
    </>
  )
}

// The camera window floats over its pane: drag it by the title bar, resize it from the corner
// (CSS resize), double-click the title bar to dock it back. Kept per browser.
const EYE_KEY = 'dz-eye-window'
function loadBox() { try { return JSON.parse(localStorage.getItem(EYE_KEY)) || null } catch { return null } }
function saveBox(b) { try { if (b) localStorage.setItem(EYE_KEY, JSON.stringify(b)); else localStorage.removeItem(EYE_KEY) } catch { /* not kept */ } }
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))

function useFloating() {
  const win = useRef(null)
  const [box, setBox] = useState(loadBox)   // { left, top, width?, height? } in pane px; null = docked
  // a corner resize sets the inline size: remember it (CSS growth of .focus is not a user resize)
  useEffect(() => {
    const el = win.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => {
      if (!el.style.width) return
      setBox((b) => ({ ...(b ?? {}), width: el.offsetWidth, height: el.offsetHeight }))
    })
    ro.observe(el)
    return () => ro.disconnect()
  })
  const onPointerDown = (e) => {
    if (e.button !== 0 || e.target.closest('button')) return
    const el = win.current
    const parent = el.offsetParent?.getBoundingClientRect()
    if (!parent) return
    const r = el.getBoundingClientRect()
    const dx = e.clientX - r.left
    const dy = e.clientY - r.top
    const head = e.currentTarget
    head.setPointerCapture(e.pointerId)
    const place = (ev) => {
      const left = clamp(ev.clientX - parent.left - dx, 0, parent.width - 120)
      const top = clamp(ev.clientY - parent.top - dy, 0, parent.height - 40)
      el.style.left = `${left}px`
      el.style.top = `${top}px`
      el.style.right = 'auto'
      return { left, top }
    }
    const move = (ev) => place(ev)
    const up = (ev) => {
      head.removeEventListener('pointermove', move)
      head.removeEventListener('pointerup', up)
      const at = place(ev)
      setBox((b) => ({ ...(b ?? {}), ...at }))
    }
    head.addEventListener('pointermove', move)
    head.addEventListener('pointerup', up)
  }
  // saved from the state itself, so a late drag-end or resize update cannot undo a dock
  useEffect(() => { saveBox(box) }, [box])
  const dock = () => {
    const el = win.current
    if (el) for (const k of ['left', 'top', 'right', 'width', 'height']) el.style[k] = ''
    setBox(null)
  }
  const style = box ? {
    ...(box.left != null ? { left: box.left, top: box.top, right: 'auto' } : {}),
    ...(box.width ? { width: box.width, height: box.height } : {}),
  } : undefined
  return { win, style, floating: Boolean(box), onPointerDown, dock }
}

export default function RobotEye() {
  const robotId = useSim((s) => s.eyeRobot)
  const thermal = useSim((s) => s.eyeThermal)
  const night = useSim((s) => s.night)
  const meta = useSim((s) => s.robotsMeta.find((r) => r.id === s.eyeRobot))
  const set = useSim((s) => s.set)
  const focused = useSim((s) => s.eyeFocus?.robot === s.eyeRobot && s.eyeFocus)
  const [, rerender] = useState(0)
  const boxes = useRef([])
  const float = useFloating()
  // grow while a verdict is on screen, then shrink back to the corner
  const live = focused && performance.now() - focused.born < FOCUS_HOLD_MS
  useEffect(() => {
    if (!live) return
    const id = setTimeout(() => rerender((n) => n + 1), Math.max(0, focused.born + FOCUS_HOLD_MS - performance.now()) + 50)
    return () => clearTimeout(id)
  }, [live, focused])
  if (!robotId) return null
  return (
    <div ref={float.win} style={float.style} className={`robot-eye${thermal ? ' thermal' : ''}${live ? ' focus' : ''}${float.floating ? ' floating' : ''}`}>
      <div className="eye-head" onPointerDown={float.onPointerDown} onDoubleClick={float.dock} title="Drag to move · corner to resize · double-click to dock">
        <i className="swatch" style={{ background: meta?.color }} />
        <b>{meta?.name ?? robotId} camera</b>
        <button className={`eye-toggle${thermal ? ' on' : ''}`} onClick={() => set({ eyeThermal: !thermal })}>Thermal</button>
        <button className="eye-close" aria-label="Close camera" onClick={() => set({ eyeRobot: null })}>×</button>
      </div>
      {/* a whole second scene: half resolution, at most 15 frames a second (rayan-ml's profile: opening it halved the fps) */}
      <Canvas dpr={0.5} frameloop="demand" camera={{ fov: 85, near: 0.05, far: 60 }} gl={{ antialias: false, powerPreference: 'low-power' }}>
        <EyeRate fps={15} />
        <color attach="background" args={[thermal ? '#030614' : night ? '#07080a' : '#0e1114']} />
        {thermal ? <ambientLight intensity={0.6} /> : night ? (
          <>
            <ambientLight intensity={0.12} />
            <hemisphereLight args={['#6f86b0', '#120f0c', 0.3]} />
          </>
        ) : (
          <>
            <ambientLight intensity={0.7} />
            <hemisphereLight args={['#e2e8f0', '#1f2937', 1.4]} />
          </>
        )}
        {!thermal && <fog attach="fog" args={[night ? '#07080a' : '#0e1114', night ? 5 : 8, night ? 20 : 26]} />}
        <Building thermal={thermal} lite />
        <HotSpots thermal={thermal} />
        <Robots robotId={robotId} thermal={thermal} />
        <EyeCamera robotId={robotId} />
        <ClassifyBoxes robotId={robotId} thermal={thermal} boxes={boxes} />
      </Canvas>
      {Array.from({ length: MAX_BOXES }, (_, i) => (
        <div key={i} ref={(el) => { boxes.current[i] = el }} className="eye-box" style={{ display: 'none' }}><span className="eye-box-label" /></div>
      ))}
      <FocusPanel robotId={robotId} />
      <span className="eye-note">
        {thermal ? `Thermal camera · ${AI_CAPTION} Warm objects are scored by the onboard person classifier.`
          : 'Forward camera · every warm object is scored by the onboard person classifier from its thermal crop'}
      </span>
    </div>
  )
}
