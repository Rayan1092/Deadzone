import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line } from '@react-three/drei'
import * as THREE from 'three'
import { useSim } from '../store'
import { COLORS, w2t } from './util'

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

function RobotBody({ pose, color, ghost = false, label, sub, headlight = true }) {
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
      <mesh position={[0, 0.16, 0]} castShadow>
        <boxGeometry args={[0.5, 0.18, 0.36]} />
        <meshStandardMaterial color={color} transparent={ghost} opacity={op}
                              emissive={color} emissiveIntensity={ghost ? 0.1 : 0.25} />
      </mesh>
      {[[-0.15, 0.2], [0.15, 0.2], [-0.15, -0.2], [0.15, -0.2]].map(([x, z], i) => (
        <mesh key={i} position={[x, 0.08, z]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.08, 0.08, 0.06, 12]} />
          <meshStandardMaterial color="#0f1214" transparent={ghost} opacity={op} />
        </mesh>
      ))}
      <mesh ref={sensor} position={[0.05, 0.32, 0]}>
        <cylinderGeometry args={[0.07, 0.07, 0.1, 12]} />
        <meshStandardMaterial color="#e5e7eb" transparent={ghost} opacity={op} />
      </mesh>
      {!ghost && headlight && <Headlight />}
      {label && (
        <Html position={[0, 0.8, 0]} center distanceFactor={40} style={{ pointerEvents: 'none' }}>
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
  const [x, y] = robot.pose
  const pts = []
  for (const [lx, ly] of robot.lidar) {
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
function Survivor({ pos, label }) {
  const ring = useRef()
  useFrame(({ clock }) => {
    const s = 1 + 0.5 * ((clock.elapsedTime * 1.2) % 1)
    if (ring.current) {
      ring.current.scale.set(s, s, s)
      ring.current.material.opacity = 1.2 - s * 0.7
    }
  })
  return (
    <group position={w2t(pos[0], pos[1], 0)}>
      <mesh position={[0, 0.35, 0]}>
        <sphereGeometry args={[0.22, 16, 16]} />
        <meshStandardMaterial color={COLORS.red} emissive={COLORS.red} emissiveIntensity={2} />
      </mesh>
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
        <ringGeometry args={[0.45, 0.6, 32]} />
        <meshBasicMaterial color={COLORS.red} transparent opacity={0.8} side={THREE.DoubleSide} />
      </mesh>
      <pointLight position={[0, 0.8, 0]} color={COLORS.red} intensity={3} distance={4} />
      <Html position={[0, 1.1, 0]} center distanceFactor={40} style={{ pointerEvents: 'none' }}>
        <div className="tag alert"><b>{label}</b></div>
      </Html>
    </group>
  )
}

// --------------------------------------------------------------- views
export function RealityActors() {
  const tick = useSim((s) => s.tick)
  const fp = useSim((s) => s.floorplan)
  if (!tick || !fp) return null
  const cmd = fp.command_post.pos
  const { robots, survivors_found } = tick.reality
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
          <Line points={[w2t(r.pose[0], r.pose[1], 0.5), w2t(cmd[0], cmd[1], 2.4)]}
                color={r.link.up ? COLORS.green : COLORS.red} lineWidth={r.link.up ? 2 : 1}
                transparent opacity={r.link.up ? 0.7 : 0.35} dashed={!r.link.up} dashSize={0.4} gapSize={0.3} />
        </group>
      ))}
      {survivors_found.map((s) => <Survivor key={s.id} pos={s.pos} label={`${s.id} found by ${s.by}`} />)}
    </group>
  )
}

export function CommandActors() {
  const tick = useSim((s) => s.tick)
  const time = useSim((s) => s.time)
  if (!tick) return null
  const { robots, survivors } = tick.command
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
      {survivors.map((s) => <Survivor key={s.id} pos={s.pos} label={`${s.id} reported`} />)}
    </group>
  )
}
