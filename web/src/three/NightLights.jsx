import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useSim } from '../store'
import { MAST_H, WALL_H, w2t } from './util'

// Night operations (K): the building goes dark and the light comes from what rescuers
// brought: the command truck's flood light into the entrance, amber strobes the crews
// set up in the corridor and the warehouse, and the robots' own headlights. Light shafts
// are soft additive cones, so the dust in the air reads as lit. Reality panes only.

// Vertical fade for beams: bright at the source, gone at the far end.
let fade = null
function fadeTexture() {
  if (fade) return fade
  const c = document.createElement('canvas')
  c.width = 4
  c.height = 128
  const ctx = c.getContext('2d')
  const g = ctx.createLinearGradient(0, 0, 0, 128)
  g.addColorStop(0, 'rgba(255,255,255,1)') // canvas top = cone tip (texture v = 1)
  g.addColorStop(0.5, 'rgba(255,255,255,.35)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 4, 128)
  fade = new THREE.CanvasTexture(c)
  return fade
}

// Open cone with its tip at the origin, pointing along -y.
export function LightBeam({ length, radius, color = '#fff4d6', opacity = 0.18 }) {
  const geom = useMemo(() => {
    const g = new THREE.ConeGeometry(radius, length, 24, 1, true)
    g.translate(0, -length / 2, 0)
    return g
  }, [length, radius])
  return (
    <mesh geometry={geom} renderOrder={5}>
      <meshBasicMaterial color={color} alphaMap={fadeTexture()} transparent opacity={opacity} depthWrite={false}
                         blending={THREE.AdditiveBlending} side={THREE.FrontSide} toneMapped={false} />
    </mesh>
  )
}

// Point a group's -y axis from `from` toward `to` (three.js coordinates).
function aim(from, to) {
  const dir = new THREE.Vector3(...to).sub(new THREE.Vector3(...from)).normalize()
  return new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, -1, 0), dir)
}

// Amber rotating strobe on a tripod, lighting the area around it.
function Strobe({ at, phase = 0 }) {
  const light = useRef()
  const lamp = useRef()
  useFrame(({ clock }) => {
    const t = clock.elapsedTime * 2.4 + phase
    const k = Math.max(0, Math.sin(t * Math.PI)) ** 6
    if (light.current) light.current.intensity = 1.5 + 9 * k
    if (lamp.current) lamp.current.emissiveIntensity = 0.6 + 4 * k
  })
  return (
    <group position={w2t(at[0], at[1], 0)}>
      {[0, 2.1, 4.2].map((a) => (
        <mesh key={a} position={[Math.cos(a) * 0.18, 0.55, Math.sin(a) * 0.18]} rotation={[0, -a, 0.25]}>
          <cylinderGeometry args={[0.012, 0.012, 1.15, 5]} />
          <meshStandardMaterial color="#2b2f33" />
        </mesh>
      ))}
      <mesh position={[0, 1.15, 0]}>
        <cylinderGeometry args={[0.07, 0.08, 0.12, 12]} />
        <meshStandardMaterial ref={lamp} color="#ffb347" emissive="#ff9a1a" toneMapped={false} />
      </mesh>
      <pointLight ref={light} position={[0, 1.3, 0]} color="#ffa23a" distance={8} decay={1.6} />
    </group>
  )
}

// Flood light on the truck's mast, aimed through the entrance into the corridor.
function Flood({ from, to }) {
  const tgt = useMemo(() => new THREE.Object3D(), [])
  const q = useMemo(() => aim(from, to), [from, to])
  const len = new THREE.Vector3(...to).distanceTo(new THREE.Vector3(...from)) + 2
  return (
    <>
      <primitive object={tgt} position={to} />
      <spotLight position={from} target={tgt} angle={0.42} penumbra={0.5} intensity={26} distance={30} decay={1.4} color="#ffe6bf" />
      <group position={from} quaternion={q}>
        <mesh><boxGeometry args={[0.32, 0.12, 0.22]} /><meshStandardMaterial color="#fffbe8" emissive="#fff3cf" emissiveIntensity={3} toneMapped={false} /></mesh>
        <LightBeam length={len} radius={len * 0.42} opacity={0.028} />
      </group>
    </>
  )
}

export default function NightLights() {
  const fp = useSim((s) => s.floorplan)
  if (!fp) return null
  const [cx, cy] = fp.command_post.pos
  const [ex, ey] = fp.entry ?? [1, fp.size[1] / 2]
  const corridor = (fp.rooms ?? []).find((r) => /corridor/i.test(r.name))
  const warehouse = (fp.rooms ?? []).find((r) => /warehouse floor/i.test(r.name))
  // strobes stand against a wall, out of the robots' way
  const box = (room) => {
    const xs = room.poly.map((p) => p[0])
    const ys = room.poly.map((p) => p[1])
    return [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  }
  const strobes = [[cx + 0.9, cy - 2.4]]
  if (corridor) { const [x0, x1, y0] = box(corridor); strobes.push([(x0 + x1) / 2 + 3, y0 + 0.35]) }
  if (warehouse) { const [, x1, y0, y1] = box(warehouse); strobes.push([x1 - 0.45, (y0 + y1) / 2 - 4]) }
  return (
    <group>
      <Flood from={w2t(cx, cy, MAST_H - 0.6)} to={w2t(ex + (ex - cx) / (Math.hypot(ex - cx, ey - cy) || 1) * 6, ey + (ey - cy) / (Math.hypot(ex - cx, ey - cy) || 1) * 6, 0)} />
      {strobes.map((s, i) => <Strobe key={i} at={s} phase={i * 0.7} />)}
      {/* a little cold moonlight spilling over the top of the walls */}
      <pointLight position={w2t(fp.size[0] / 2, fp.size[1] / 2, WALL_H + 6)} intensity={4} distance={40} color="#7d93c9" />
    </group>
  )
}
