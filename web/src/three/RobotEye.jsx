import { useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { useSim } from '../store'
import Building from './Building'
import { PersonFigure } from './Actors'
import { w2t } from './util'

// Picture-in-picture from a robot's forward camera (V key or the card's Camera
// button). Reality pane only: it shows what the robot's own camera sees. A third
// WebGL canvas, so it only exists while open and renders small at dpr 1.
const EYE_H = 0.4 // m, camera height on the robot

function EyeCamera({ robotId }) {
  const { camera } = useThree()
  const look = useRef(new THREE.Vector3())
  const at = useRef(null)
  useFrame((_, dt) => {
    const r = useSim.getState().tick?.reality.robots.find((x) => x.id === robotId)
    if (!r) return
    const [x, y, th] = r.pose
    const goal = new THREE.Vector3(...w2t(x, y, EYE_H))
    const ahead = new THREE.Vector3(...w2t(x + Math.cos(th), y + Math.sin(th), EYE_H - 0.05))
    if (!at.current) { at.current = goal.clone(); look.current.copy(ahead) }
    const k = Math.min(1, dt * 8) // 10 Hz poses, smoothed to the frame rate
    at.current.lerp(goal, k)
    look.current.lerp(ahead, k)
    camera.position.copy(at.current)
    camera.lookAt(look.current)
  })
  return null
}

// Hot spots as the camera sees them: survivors and decoys both glow in thermal,
// which is exactly why the onboard detector has to judge them.
function HotSpots({ thermal }) {
  const fp = useSim((s) => s.floorplan)
  if (!fp) return null
  return (
    <group>
      {(fp.survivors ?? []).map((s) => (
        <group key={s.id} position={w2t(s.pos[0], s.pos[1], 0)}>
          {thermal ? (
            <mesh position={[0, 0.15, 0]} scale={[1.4, 0.35, 0.6]}>
              <sphereGeometry args={[0.5, 16, 12]} />
              <meshBasicMaterial color="#fff1b8" />
            </mesh>
          ) : <PersonFigure id={s.id} />}
        </group>
      ))}
      {(fp.decoys ?? []).map((d) => (
        <mesh key={d.id} position={w2t(d.pos[0], d.pos[1], 0.45)}>
          <boxGeometry args={[0.6, 0.9, 0.35]} />
          {thermal ? <meshBasicMaterial color="#ffb347" /> : <meshStandardMaterial color="#6b7280" roughness={0.6} />}
        </mesh>
      ))}
    </group>
  )
}

function OtherRobots({ robotId, thermal }) {
  const robots = useSim((s) => s.tick?.reality.robots)
  return (robots ?? []).filter((r) => r.id !== robotId).map((r) => (
    <mesh key={r.id} position={w2t(r.pose[0], r.pose[1], 0.16)} rotation={[0, r.pose[2], 0]}>
      <boxGeometry args={[0.5, 0.2, 0.36]} />
      {thermal ? <meshBasicMaterial color="#f97316" /> : <meshStandardMaterial color={r.color} emissive={r.color} emissiveIntensity={0.4} />}
    </mesh>
  ))
}

export default function RobotEye() {
  const robotId = useSim((s) => s.eyeRobot)
  const thermal = useSim((s) => s.eyeThermal)
  const meta = useSim((s) => s.robotsMeta.find((r) => r.id === s.eyeRobot))
  const set = useSim((s) => s.set)
  if (!robotId) return null
  return (
    <div className={`robot-eye${thermal ? ' thermal' : ''}`}>
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
        <OtherRobots robotId={robotId} thermal={thermal} />
        <EyeCamera robotId={robotId} />
      </Canvas>
      <span className="eye-note">{thermal ? 'Thermal: walls cold, people and hot objects glow' : 'Forward camera'}</span>
    </div>
  )
}
