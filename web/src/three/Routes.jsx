import { useEffect, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import Line from './FastLine' // drei's Line relinks its shader on every new points array
import * as THREE from 'three'
import { useSim } from '../store'
import { w2t } from './util'
import { latestRoutes } from '../format'

// Safe A* routes from the entrance to a confirmed survivor (Rayan's rescue_route).
// Reality draws the robot's own event; Command draws only routes delivered to it.
const ROUTE = '#facc15'
const NONE = []
const FLASH_MS = 2500

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

// pending = the robot has the route but Command doesn't yet (gap view): faint, says so.
function Route({ route, relays, pending = false }) {
  const pts = route.path.map(([x, y]) => w2t(x, y, 0.12))
  const end = route.path[route.path.length - 1]
  const beacon = route.beacon && relays.find((r) => r.id === route.beacon)
  // a replacement route (newer t, e.g. rerouted around new rubble) flashes as it redraws
  const lastT = useRef(route.t)
  const [flashAt, setFlashAt] = useState(null)
  const glow = useRef()
  useEffect(() => {
    if (route.t !== lastT.current) { lastT.current = route.t; setFlashAt(performance.now()) }
  }, [route.t])
  useEffect(() => {
    if (!flashAt) return
    const id = setTimeout(() => setFlashAt(null), FLASH_MS)
    return () => clearTimeout(id)
  }, [flashAt])
  useFrame(() => {
    if (glow.current && flashAt) glow.current.material.opacity = 0.9 * Math.max(0, 1 - (performance.now() - flashAt) / FLASH_MS)
  })
  return (
    <group>
      {flashAt && (
        <Line ref={glow} points={pts} color="#fff7cc" lineWidth={9} depthTest={false} renderOrder={4} transparent opacity={0.9} />
      )}
      {/* drawn through the fog layer so a route over not-yet-mapped cells stays visible */}
      <Line points={pts} color={ROUTE} lineWidth={pending ? 2 : 3.5} dashed dashSize={pending ? 0.3 : 0.6}
            gapSize={pending ? 0.4 : 0.35} depthTest={false} renderOrder={4} transparent opacity={pending ? 0.45 : 0.95} />
      <mesh position={pts[0]} renderOrder={4}>
        <sphereGeometry args={[0.18, 12, 12]} />
        <meshBasicMaterial color={ROUTE} depthTest={false} />
      </mesh>
      <Html position={w2t(end[0], end[1], 1.9)} center zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
        <div className={`tag route${pending ? ' pending' : ''}`}>
          <b>Route to {route.survivor}</b>
          <span>{pending ? 'not reported yet' : `${route.length_m.toFixed(1)} m${flashAt ? ' · rerouted' : ''}`}</span>
        </div>
      </Html>
      {beacon && <Beacon pos={beacon.pos} id={beacon.id} />}
    </group>
  )
}

export function RealityRoutes({ gap = false }) {
  const routes = useSim((s) => s.routes)
  const relays = useSim((s) => s.tick?.reality.relays) ?? NONE
  const delivered = useSim((s) => s.tick?.command.routes) ?? NONE
  // pending until Command holds this version of the route (an older one doesn't count)
  return Object.values(routes).map((r) => (
    <Route key={r.survivor} route={r} relays={relays}
           pending={gap && !delivered.some((d) => d.survivor === r.survivor && (d.t ?? 0) >= (r.t ?? 0))} />
  ))
}

export function CommandRoutes() {
  const routes = latestRoutes(useSim((s) => s.tick?.command.routes) ?? NONE)
  const relays = useSim((s) => s.tick?.command.relays) ?? NONE
  return routes.map((r) => <Route key={r.survivor} route={r} relays={relays} />)
}
