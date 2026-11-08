import { useEffect } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { Line } from '@react-three/drei'
import { useSim } from '../store'
import Building from './Building'
import Fog from './Fog'
import { w2t } from './util'
import { latestRoutes } from '../format'

// Gap view corner inset: what the command post knows, as a top-down blueprint.
// Only delivered data; the floorplan drawn without truth rubble.
const NONE = []
const STALE_S = 3

function TopDown() {
  const { camera, size } = useThree()
  const fp = useSim((s) => s.floorplan)
  useEffect(() => {
    if (!fp) return
    const [W, H] = fp.size
    camera.up.set(0, 0, -1) // north up
    camera.position.set(W / 2 - 1, 60, -H / 2)
    camera.lookAt(W / 2 - 1, 0, -H / 2)
    camera.zoom = Math.min(size.width / (W + 6), size.height / (H + 2))
    camera.updateProjectionMatrix()
  }, [camera, size, fp])
  return null
}

function Dot({ pos, color, r = 0.55, ring = false }) {
  return (
    <group position={w2t(pos[0], pos[1], 2)}>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        {ring ? <ringGeometry args={[r * 0.6, r, 24]} /> : <circleGeometry args={[r, 24]} />}
        <meshBasicMaterial color={color} />
      </mesh>
    </group>
  )
}

function Known() {
  const cmd = useSim((s) => s.tick?.command)
  const time = useSim((s) => s.time)
  const robots = useSim((s) => s.robotsMeta)
  const colors = Object.fromEntries(robots.map((r) => [r.id, r.color]))
  if (!cmd) return null
  return (
    <group>
      {latestRoutes(cmd.routes ?? NONE).map((r) => (
        <Line key={r.survivor} points={r.path.map(([x, y]) => w2t(x, y, 1.9))} color="#facc15" lineWidth={2} />
      ))}
      {cmd.relays.map((r) => <Dot key={r.id} pos={r.pos} color="#b7791f" r={0.4} />)}
      {cmd.survivors.map((s) => <Dot key={s.id} pos={s.pos} color="#f59e0b" r={0.8} />)}
      {cmd.robots.map((r) => (
        <Dot key={r.id} pos={r.pose} color={time - r.last_seen > STALE_S ? '#64748b' : colors[r.id] ?? '#2dd4bf'}
             ring={time - r.last_seen > STALE_S} />
      ))}
    </group>
  )
}

export default function CommandInset() {
  return (
    <div className="cmd-inset">
      <div className="inset-head"><i className="dot command" /><b>Command post knows</b></div>
      <Canvas orthographic dpr={1} gl={{ antialias: true, powerPreference: 'low-power' }}
              camera={{ position: [20, 60, -15], zoom: 6, near: 0.1, far: 200 }}>
        <color attach="background" args={['#081325']} />
        <ambientLight intensity={1.1} />
        <Building blueprint />
        <Fog which="command" cover={false} />
        <Known />
        <TopDown />
      </Canvas>
    </div>
  )
}
