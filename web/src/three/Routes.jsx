import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line } from '@react-three/drei'
import * as THREE from 'three'
import { useSim } from '../store'
import { w2t } from './util'

// Safe A* routes from the entrance to a confirmed survivor (Rayan's rescue_route).
// Reality draws the robot's own event; Command draws only routes delivered to it.
const ROUTE = '#facc15'
const NONE = []

function Beacon({ pos, id }) {
  const ring = useRef()
  useFrame(({ clock }) => {
    if (!ring.current) return
    const k = (clock.elapsedTime * 0.7) % 1
    ring.current.scale.setScalar(1 + k * 3)
    ring.current.material.opacity = 0.8 * (1 - k)
  })
  return (
    <group position={w2t(pos[0], pos[1], 0)}>
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.06, 0]} renderOrder={4}>
        <ringGeometry args={[0.4, 0.5, 40]} />
        <meshBasicMaterial color={ROUTE} transparent depthTest={false} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <Html position={[0, 1.6, 0]} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
        <div className="tag route">{id} beacon</div>
      </Html>
    </group>
  )
}

function Route({ route, relays }) {
  const pts = route.path.map(([x, y]) => w2t(x, y, 0.12))
  const end = route.path[route.path.length - 1]
  const beacon = route.beacon && relays.find((r) => r.id === route.beacon)
  return (
    <group>
      {/* drawn through the fog layer so a route over not-yet-mapped cells stays visible */}
      <Line points={pts} color={ROUTE} lineWidth={3.5} dashed dashSize={0.6} gapSize={0.35}
            depthTest={false} renderOrder={4} transparent opacity={0.95} />
      <mesh position={pts[0]} renderOrder={4}>
        <sphereGeometry args={[0.18, 12, 12]} />
        <meshBasicMaterial color={ROUTE} depthTest={false} />
      </mesh>
      <Html position={w2t(end[0], end[1], 1.9)} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
        <div className="tag route"><b>Route to {route.survivor}</b><span>{route.length_m.toFixed(1)} m</span></div>
      </Html>
      {beacon && <Beacon pos={beacon.pos} id={beacon.id} />}
    </group>
  )
}

export function RealityRoutes() {
  const routes = useSim((s) => s.routes)
  const relays = useSim((s) => s.tick?.reality.relays) ?? NONE
  return Object.values(routes).map((r) => <Route key={r.survivor} route={r} relays={relays} />)
}

export function CommandRoutes() {
  const routes = useSim((s) => s.tick?.command.routes) ?? NONE
  const relays = useSim((s) => s.tick?.command.relays) ?? NONE
  return routes.map((r) => <Route key={r.survivor} route={r} relays={relays} />)
}
