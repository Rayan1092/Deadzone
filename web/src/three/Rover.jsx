import { useMemo } from 'react'
import { RoundedBox } from '@react-three/drei'
import * as THREE from 'three'
import { materials, signTexture } from './textures'

// The search rover, one model for every view (the 3D map, Command's ghosts and the robot's-eye
// camera), so a robot looks the same from above and through another robot's camera.
// Units: meters before ROBOT_SCALE, x forward, y up. A 0.56 m tracked UGV:
//  - two track pods (rubber tread over a sprocket and road wheels, sloped ends)
//  - a gunmetal hull with a sloped glacis, fenders and the robot's color on the deck and flanks
//  - a hazard-striped front bumper with two headlights
//  - a pan-tilt camera head with an LED light bar
//  - a mast-mounted lidar whose ring glows in the robot's color (spins: `sensor` ref)
//  - a rear battery pack, roll bar, and a radio whip whose tip shows the link (green / red)
//  - its id painted on both flanks
export const ROBOT_SCALE = 1.8 // drawn larger than the 0.5 m body so robots read on a projector

const TRACK_W = 0.1
const TRACK_Z = 0.17

// Side profile of a track pod: low stadium with sloped front and back.
let trackGeom = null
function trackGeometry() {
  if (trackGeom) return trackGeom
  const s = new THREE.Shape()
  const L = 0.28
  s.moveTo(-L + 0.03, 0.012)
  s.lineTo(L - 0.03, 0.012)
  s.quadraticCurveTo(L + 0.03, 0.012, L + 0.035, 0.07)
  s.quadraticCurveTo(L + 0.03, 0.14, L - 0.05, 0.15)
  s.lineTo(-L + 0.05, 0.15)
  s.quadraticCurveTo(-L - 0.03, 0.14, -L - 0.035, 0.07)
  s.quadraticCurveTo(-L - 0.03, 0.012, -L + 0.03, 0.012)
  const g = new THREE.ExtrudeGeometry(s, { depth: TRACK_W, bevelEnabled: true, bevelThickness: 0.008, bevelSize: 0.008, bevelSegments: 2, curveSegments: 10 })
  g.translate(0, 0, -TRACK_W / 2)
  trackGeom = g
  return g
}

// Hull side profile with a sloped glacis, extruded across the body.
let hullGeom = null
function hullGeometry() {
  if (hullGeom) return hullGeom
  const s = new THREE.Shape()
  s.moveTo(-0.235, 0.085)
  s.lineTo(0.18, 0.085)
  s.lineTo(0.25, 0.135)
  s.lineTo(0.215, 0.205)
  s.lineTo(-0.21, 0.205)
  s.lineTo(-0.24, 0.175)
  s.lineTo(-0.235, 0.085)
  const g = new THREE.ExtrudeGeometry(s, { depth: 0.22, bevelEnabled: true, bevelThickness: 0.006, bevelSize: 0.006, bevelSegments: 2 })
  g.translate(0, 0, -0.11)
  hullGeom = g
  return g
}

let base = null
function baseMats() {
  if (base) return base
  const t = materials()
  const tread = t.tread.map.clone()
  tread.repeat.set(10, 10)
  tread.needsUpdate = true
  const treadN = t.tread.normalMap.clone()
  treadN.repeat.set(10, 10)
  treadN.needsUpdate = true
  const stripes = t.tape.map.clone()
  stripes.repeat.set(2, 1)
  stripes.needsUpdate = true
  base = {
    track: new THREE.MeshStandardMaterial({ map: tread, normalMap: treadN, color: '#5a5e64', roughness: 0.92 }),
    hull: new THREE.MeshStandardMaterial({ color: '#30363d', metalness: 0.7, roughness: 0.36, envMapIntensity: 1.2 }),
    dark: new THREE.MeshStandardMaterial({ color: '#16191d', metalness: 0.5, roughness: 0.45 }),
    metal: new THREE.MeshStandardMaterial({ color: '#c5cbd3', metalness: 1, roughness: 0.22 }),
    rubber: new THREE.MeshStandardMaterial({ color: '#0e0f11', roughness: 0.85 }),
    lens: new THREE.MeshStandardMaterial({ color: '#06122a', metalness: 1, roughness: 0.04 }),
    lamp: new THREE.MeshStandardMaterial({ color: '#ffffff', emissive: '#eafcff', emissiveIntensity: 3.2, toneMapped: false }),
    bar: new THREE.MeshStandardMaterial({ color: '#ffffff', emissive: '#fff7e6', emissiveIntensity: 2.2, toneMapped: false }),
    hazard: new THREE.MeshStandardMaterial({ map: stripes, roughness: 0.55 }),
    battery: new THREE.MeshStandardMaterial({ color: '#23272c', metalness: 0.3, roughness: 0.6 }),
    ghost: new THREE.MeshStandardMaterial({ color: '#94a3b8', transparent: true, opacity: 0.32, depthWrite: false }),
    hot: new THREE.MeshBasicMaterial({ color: '#f97316' }), // thermal camera: motors and batteries run warm
  }
  return base
}

const perColor = new Map()
function colorMats(color) {
  if (!perColor.has(color)) {
    perColor.set(color, {
      paint: new THREE.MeshStandardMaterial({ color, metalness: 0.35, roughness: 0.32, emissive: color, emissiveIntensity: 0.1 }),
      led: new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 2.8, toneMapped: false }),
    })
  }
  return perColor.get(color)
}
const tips = {
  up: new THREE.MeshStandardMaterial({ color: '#4ade80', emissive: '#22c55e', emissiveIntensity: 3, toneMapped: false }),
  down: new THREE.MeshStandardMaterial({ color: '#ef4444', emissive: '#ef4444', emissiveIntensity: 3, toneMapped: false }),
}
// powered down (Rayan's SHUTDOWN, `lights: false`): lamps, LEDs and the link tip go dark
const UNLIT = new THREE.MeshStandardMaterial({ color: '#2a2f35', roughness: 0.6, metalness: 0.2 })
const decals = new Map()
function decal(tag) {
  if (!decals.has(tag)) {
    decals.set(tag, new THREE.MeshStandardMaterial({
      map: signTexture([tag], { w: 128, h: 64, bg: 'rgba(0,0,0,0)', fg: '#f3f4f6', font: 'bold 44px Inter, sans-serif' }),
      transparent: true, roughness: 0.6, polygonOffset: true, polygonOffsetFactor: -2,
    }))
  }
  return decals.get(tag)
}

export default function Rover({ color, tag, ghost = false, thermal = false, sensor, linkUp = true, powered = true }) {
  const B = baseMats()
  const C = colorMats(color)
  const M = useMemo(() => {
    const one = ghost ? B.ghost : thermal ? B.hot : null
    if (one) return new Proxy({}, { get: () => one })
    if (!powered) return { ...B, ...C, lamp: UNLIT, bar: UNLIT, led: UNLIT, tip: UNLIT }
    return { ...B, ...C, tip: linkUp ? tips.up : tips.down }
  }, [B, C, ghost, thermal, linkUp, powered])
  const label = tag && !ghost && !thermal ? decal(tag) : null
  return (
    <group>
      {/* track pods: tread, sprocket at the back, idler at the front, road wheels between */}
      {[-TRACK_Z, TRACK_Z].map((z) => {
        const out = z > 0 ? 1 : -1
        return (
          <group key={z} position={[0, 0, z]}>
            <mesh geometry={trackGeometry()} material={M.track} />
            {[[-0.25, 0.07, 0.055], [0.255, 0.07, 0.05]].map(([x, y, r]) => (
              <mesh key={x} position={[x, y, out * (TRACK_W / 2 + 0.006)]} rotation={[Math.PI / 2, 0, 0]} material={M.metal}>
                <cylinderGeometry args={[r * 0.8, r * 0.8, 0.012, 12]} />
              </mesh>
            ))}
            {[-0.14, -0.045, 0.05, 0.145].map((x) => (
              <mesh key={x} position={[x, 0.055, out * (TRACK_W / 2 + 0.005)]} rotation={[Math.PI / 2, 0, 0]} material={M.dark}>
                <cylinderGeometry args={[0.036, 0.036, 0.01, 14]} />
              </mesh>
            ))}
            {/* fender */}
            <mesh position={[0, 0.162, 0]} material={M.hull}><boxGeometry args={[0.5, 0.012, TRACK_W + 0.03]} /></mesh>
          </group>
        )
      })}
      {/* hull, deck panel and flank stripes in the robot's color */}
      <mesh geometry={hullGeometry()} material={M.hull} />
      <RoundedBox args={[0.3, 0.014, 0.19]} radius={0.006} smoothness={2} position={[-0.03, 0.214, 0]} material={M.paint} />
      {[-1, 1].map((s) => (
        <group key={s}>
          <mesh position={[-0.02, 0.15, s * 0.117]} material={M.paint}><boxGeometry args={[0.32, 0.03, 0.004]} /></mesh>
          <mesh position={[-0.02, 0.19, s * 0.117]} material={M.led}><boxGeometry args={[0.28, 0.008, 0.004]} /></mesh>
          {label && (
            <mesh position={[-0.09, 0.15, s * 0.1195]} rotation={[0, s > 0 ? 0 : Math.PI, 0]} material={label}>
              <planeGeometry args={[0.09, 0.045]} />
            </mesh>
          )}
        </group>
      ))}
      {/* front bumper with hazard stripes and headlights */}
      <mesh position={[0.262, 0.115, 0]} material={M.hazard}><boxGeometry args={[0.022, 0.05, 0.26]} /></mesh>
      {[-0.075, 0.075].map((z) => (
        <group key={z} position={[0.233, 0.168, z]} rotation={[0, 0, -0.95]}>
          <RoundedBox args={[0.012, 0.03, 0.05]} radius={0.004} smoothness={2} material={M.lamp} />
        </group>
      ))}
      {/* pan-tilt camera with light bar */}
      <mesh position={[0.12, 0.225, 0]} material={M.dark}><cylinderGeometry args={[0.03, 0.036, 0.03, 14]} /></mesh>
      <mesh position={[0.12, 0.255, 0]} material={M.metal}><cylinderGeometry args={[0.012, 0.012, 0.04, 8]} /></mesh>
      <RoundedBox args={[0.085, 0.06, 0.12]} radius={0.014} smoothness={3} position={[0.13, 0.3, 0]} material={M.dark} />
      <mesh position={[0.175, 0.3, -0.025]} rotation={[0, 0, Math.PI / 2]} material={M.lens}><cylinderGeometry args={[0.019, 0.019, 0.012, 16]} /></mesh>
      <mesh position={[0.175, 0.3, 0.03]} rotation={[0, 0, Math.PI / 2]} material={M.lens}><cylinderGeometry args={[0.012, 0.012, 0.012, 12]} /></mesh>
      <mesh position={[0.135, 0.338, 0]} material={M.bar}><boxGeometry args={[0.05, 0.01, 0.1]} /></mesh>
      {/* lidar mast */}
      <mesh position={[-0.07, 0.26, 0]} material={M.metal}><cylinderGeometry args={[0.014, 0.018, 0.1, 10]} /></mesh>
      <group ref={sensor} position={[-0.07, 0.34, 0]}>
        <mesh material={M.rubber}><cylinderGeometry args={[0.048, 0.048, 0.06, 24]} /></mesh>
        <mesh material={M.led}><cylinderGeometry args={[0.0495, 0.0495, 0.01, 24]} /></mesh>
        <mesh position={[0, 0.033, 0]} material={M.metal}><cylinderGeometry args={[0.04, 0.048, 0.008, 24]} /></mesh>
        <mesh position={[0.046, 0.012, 0]} material={M.lens}><boxGeometry args={[0.006, 0.018, 0.035]} /></mesh>
      </group>
      {/* battery pack and roll bar */}
      <RoundedBox args={[0.09, 0.05, 0.17]} radius={0.01} smoothness={2} position={[-0.17, 0.235, 0]} material={M.battery} />
      <mesh position={[-0.17, 0.262, 0.04]} material={M.led}><boxGeometry args={[0.03, 0.004, 0.012]} /></mesh>
      {[-0.1, 0.1].map((z) => (
        <mesh key={z} position={[-0.215, 0.255, z]} material={M.dark}><cylinderGeometry args={[0.007, 0.007, 0.1, 8]} /></mesh>
      ))}
      <mesh position={[-0.215, 0.305, 0]} rotation={[Math.PI / 2, 0, 0]} material={M.dark}><cylinderGeometry args={[0.007, 0.007, 0.2, 8]} /></mesh>
      {/* radio whip */}
      <mesh position={[-0.2, 0.42, -0.085]} material={M.rubber}><cylinderGeometry args={[0.003, 0.006, 0.38, 6]} /></mesh>
      <mesh position={[-0.2, 0.61, -0.085]} material={M.tip}><sphereGeometry args={[0.012, 12, 12]} /></mesh>
    </group>
  )
}
