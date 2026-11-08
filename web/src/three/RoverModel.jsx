import { Component, Suspense, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { clone as cloneScene } from 'three/examples/jsm/utils/SkeletonUtils.js'
import Rover from './Rover'
import { signTexture } from './textures'

// The rescue robot as a real glTF model when the asset pack has one, the procedural Rover
// otherwise. Same props and behaviour as Rover (color, tag, ghost, thermal, sensor, linkUp),
// so Actors and RobotEye never know which one they got, and a robot never disappears: the
// procedural one stands in while the file downloads and takes over if it fails.
//
// Expected file: /assets/models/robot/robot.glb (public/assets/models/robot/README.md has the
// spec). The file is assumed to face +X: the sim's yaw spins around Y and the Rover's nose is
// +X, and facing cannot be measured. Size and origin are fitted here: longest horizontal extent
// -> 0.56 m, origin at the floor center. Node names drive the dressing: 'lidar' spins, led*
// glow in the robot's color, paint*/body* are tinted, headlight* glow white, antenna_tip shows
// the radio link, tag* carries the id (otherwise two flank stickers do).
const MODEL = '/assets/models/robot/robot.glb'
const LENGTH = 0.56 // m, the procedural Rover's length; the parent applies ROBOT_SCALE

// One HEAD per page load decides for every robot. A missing file costs one 404; a present one
// starts downloading right away so the first robot to appear already has it. Vite's dev server
// answers a missing path with index.html (200), hence the content-type check.
let have = null
let broken = false // a failed load: every robot uses the procedural one for the rest of the session
const probe = fetch(MODEL, { method: 'HEAD', headers: { Accept: 'model/gltf-binary' } })
  .then((r) => r.ok && !(r.headers.get('content-type') ?? '').includes('text/html'))
  .catch(() => false)
  .then((ok) => { have = ok; return ok })

export function preloadRover() {
  return probe.then((ok) => { if (ok && !broken) useGLTF.preload(MODEL); return ok })
}
preloadRover()

function useModelReady() {
  const [ok, setOk] = useState(have)
  useEffect(() => { if (have == null) probe.then(setOk) }, [])
  return ok === true && !broken
}

// Load errors surface as a throw from useGLTF; catch them here instead of taking the pane down.
class ModelBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(err) {
    if (!broken) console.warn('[RoverModel] robot.glb failed to load, using the procedural rover', err)
    broken = true
  }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

// --------------------------------------------------------------- materials
// Overrides are shared by every robot (the ghost and thermal looks never depend on the file).
const GHOST = new THREE.MeshStandardMaterial({ color: '#94a3b8', transparent: true, opacity: 0.32, depthWrite: false })
const HOT = new THREE.MeshBasicMaterial({ color: '#f97316' })
const labels = new Map()
function tagMat(tag) {
  if (!labels.has(tag)) {
    labels.set(tag, new THREE.MeshStandardMaterial({
      map: signTexture([tag], { w: 128, h: 64, bg: 'rgba(0,0,0,0)', fg: '#f3f4f6', font: 'bold 44px Inter, sans-serif' }),
      transparent: true, roughness: 0.6, polygonOffset: true, polygonOffsetFactor: -2,
    }))
  }
  return labels.get(tag)
}

const ROLES = [[/^led/i, 'led'], [/^paint|^body/i, 'paint'], [/^headlight/i, 'lamp'], [/^antenna_tip/i, 'tip'], [/^tag/i, 'tag']]
// A mesh's role comes from its node name, or its material's name (whichever the modeller set).
function roleOf(mesh) {
  const names = [mesh.name, ...[].concat(mesh.material).map((m) => m?.name ?? '')]
  for (const [re, role] of ROLES) if (names.some((n) => re.test(n))) return role
  return null
}

// Emissive where the material has it, plain color on unlit ones; untonemapped so it reads as a lamp.
function glow(m, color, emissive, k) {
  m.color?.set(color)
  if (m.emissive) { m.emissive.set(emissive); m.emissiveIntensity = k }
  if (m.toneMapped) { m.toneMapped = false; m.needsUpdate = true }
}

function tint(m, role, color, linkUp) {
  if (role === 'led') glow(m, color, color, 2.5)
  else if (role === 'paint') m.color?.set(color)
  else if (role === 'lamp') glow(m, '#ffffff', '#eafcff', 3.2)
  else if (role === 'tip') glow(m, linkUp ? '#4ade80' : '#ef4444', linkUp ? '#22c55e' : '#ef4444', 3)
}

function applyLook(rig, color, ghost, thermal, linkUp, label) {
  for (const { mesh, own, role } of rig.parts) {
    if (ghost) { mesh.material = GHOST; continue }
    if (thermal) { mesh.material = HOT; continue }
    if (role === 'tag' && label) { mesh.material = label; continue }
    mesh.material = own
    for (const m of [].concat(own)) tint(m, role, color, linkUp)
  }
}

// --------------------------------------------------------------- fit and rig
// Per loaded file: scale and offset into the Rover's frame, and how far out the flanks are at
// sticker height (so the id sits on the hull instead of floating off the tracks). Once per file.
const fits = new WeakMap()
const v = new THREE.Vector3()
function fitOf(scene) {
  if (fits.has(scene)) return fits.get(scene)
  const bb = new THREE.Box3().setFromObject(scene) // also brings every matrixWorld up to date
  const size = bb.getSize(new THREE.Vector3())
  const c = bb.getCenter(new THREE.Vector3())
  const span = Math.max(size.x, size.z)
  const s = span > 1e-6 ? LENGTH / span : 1
  const y0 = bb.min.y + size.y * 0.3
  const y1 = bb.min.y + size.y * 0.6
  let flank = 0
  scene.traverse((o) => {
    const p = o.isMesh && !o.isInstancedMesh ? o.geometry.attributes.position : null
    if (!p) return
    const step = Math.max(1, Math.floor(p.count / 20000)) // sample dense meshes
    for (let i = 0; i < p.count; i += step) {
      v.fromBufferAttribute(p, i).applyMatrix4(o.matrixWorld)
      if (v.y >= y0 && v.y <= y1) flank = Math.max(flank, Math.abs(v.z - c.z))
    }
  })
  const f = { scale: s, offset: [-c.x, -bb.min.y, -c.z], height: size.y * s, flank: (flank || size.z / 2) * s }
  fits.set(scene, f)
  return f
}

function findByName(root, re) {
  let hit = null
  root.traverse((o) => { if (!hit && re.test(o.name)) hit = o })
  return hit
}

// One robot's copy of the file: its own materials (tinted per robot; the cached scene's stay
// clean), its meshes by role, and the lidar re-hung in a group whose Y is the robot's up, so
// the parent's spin never tumbles a node that was exported with a rotation of its own.
function buildRig(scene) {
  const root = cloneScene(scene)
  const parts = []
  root.traverse((o) => {
    if (!o.isMesh) return
    const own = Array.isArray(o.material) ? o.material.map((m) => m.clone()) : o.material.clone()
    parts.push({ mesh: o, own, role: roleOf(o) })
  })
  let spin = null
  const lidar = root.getObjectByName('lidar') ?? findByName(root, /^lidar/i)
  if (lidar && lidar !== root) {
    spin = new THREE.Group()
    spin.name = 'lidar_spin'
    spin.position.copy(lidar.position)
    lidar.position.set(0, 0, 0)
    lidar.parent.add(spin)
    spin.add(lidar)
  }
  return { root, parts, spin, tagged: parts.some((p) => p.role === 'tag') }
}

const setRef = (ref, value) => {
  if (typeof ref === 'function') ref(value)
  else if (ref) ref.current = value
}

function GltfRover({ color, tag, ghost = false, thermal = false, sensor, linkUp = true }) {
  const { scene } = useGLTF(MODEL)
  const fit = useMemo(() => fitOf(scene), [scene])
  const rig = useMemo(() => buildRig(scene), [scene])
  const label = tag && !ghost && !thermal ? tagMat(tag) : null
  useLayoutEffect(() => applyLook(rig, color, ghost, thermal, linkUp, label), [rig, color, ghost, thermal, linkUp, label])
  useLayoutEffect(() => {
    setRef(sensor, rig.spin) // the parent spins whatever this points at
    return () => setRef(sensor, null)
  }, [rig, sensor])
  useEffect(() => () => { for (const p of rig.parts) for (const m of [].concat(p.own)) m.dispose() }, [rig])
  return (
    <group>
      <group scale={fit.scale}>
        <group position={fit.offset}><primitive object={rig.root} /></group>
      </group>
      {label && !rig.tagged && [-1, 1].map((s) => (
        <mesh key={s} position={[0, fit.height * 0.45, s * (fit.flank + 0.003)]} rotation={[0, s > 0 ? 0 : Math.PI, 0]} material={label}>
          <planeGeometry args={[0.09, 0.045]} />
        </mesh>
      ))}
    </group>
  )
}

export default function RoverModel(props) {
  const ready = useModelReady()
  if (!ready) return <Rover {...props} />
  const fallback = <Rover {...props} />
  return (
    <ModelBoundary fallback={fallback}>
      <Suspense fallback={fallback}>
        <GltfRover {...props} />
      </Suspense>
    </ModelBoundary>
  )
}
