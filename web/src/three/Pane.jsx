import { useEffect, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import Building from './Building'
import Fog from './Fog'
import { RealityActors, CommandActors } from './Actors'
import { AntennaPulse } from './Network'
import PlanZones from './PlanZones'
import { COLORS } from './util'
import { useSim } from '../store'

// Shared camera so the Reality and Command panes always show the same angle.
const shared = { pos: new THREE.Vector3(20, 50, 16), target: new THREE.Vector3(20, 0, -15), src: null, rev: 0, fitted: false }

// Pull the overview camera back along its viewing direction until the whole
// building (plus the CMD antenna west of it) fits the pane, whatever its shape.
const VIEW_W = 44 // m, x from -3 to 41
const VIEW_D = 32 // m, y from -1 to 31
function fitOverview(camera, aspect) {
  const dir = shared.pos.clone().sub(shared.target).normalize()
  const elevation = Math.asin(dir.y)
  const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)
  const byWidth = VIEW_W / 2 / (tanV * aspect)
  const byDepth = (VIEW_D * Math.sin(elevation)) / 2 / tanV
  shared.pos.copy(shared.target).addScaledVector(dir, Math.max(byWidth, byDepth) * 1.05)
}

function SyncedControls({ id }) {
  const ctrl = useRef()
  const { camera, size } = useThree()
  const seen = useRef(-1)
  const applying = useRef(false)

  useEffect(() => {
    if (!shared.fitted && size.width && size.height) {
      fitOverview(camera, size.width / size.height)
      shared.fitted = true
    }
    camera.position.copy(shared.pos)
    ctrl.current?.target.copy(shared.target)
    ctrl.current?.update()
  }, [camera])

  useFrame(() => {
    if (!ctrl.current || shared.src === id || seen.current === shared.rev) return
    applying.current = true
    camera.position.copy(shared.pos)
    ctrl.current.target.copy(shared.target)
    ctrl.current.update()
    applying.current = false
    seen.current = shared.rev
  })

  return (
    <OrbitControls
      ref={ctrl}
      makeDefault
      enableDamping
      maxPolarAngle={Math.PI / 2.2}
      minDistance={6}
      maxDistance={110}
      onStart={() => { shared.src = id }}
      onChange={() => {
        if (applying.current || shared.src !== id) return
        shared.pos.copy(camera.position)
        shared.target.copy(ctrl.current.target)
        shared.rev++
        seen.current = shared.rev
      }}
    />
  )
}

export default function Pane({ which, title, subtitle }) {
  const showTruth = useSim((s) => s.showTruth)
  return (
    <div className={`pane pane-${which}`}>
      <div className="pane-title">
        <span className={`dot ${which}`} />
        <b>{title}</b>
        <span className="muted">{subtitle}</span>
        {which === 'reality' && showTruth && <span className="truth-chip">Truth overlay · T</span>}
      </div>
      {which === 'reality' && (
        <div className="pane-legend">
          <span><i className="lg-link up" />Link</span>
          <span><i className="lg-link weak" />Weak link</span>
          <span><i className="lg-link down" />No link</span>
          <span><i className="lg-relay" />Relay</span>
        </div>
      )}
      <Canvas shadows dpr={[1, 2]} camera={{ fov: 50, near: 0.1, far: 300 }}>
        <color attach="background" args={[COLORS.bg]} />
        <fog attach="fog" args={[COLORS.bg, 90, 170]} />
        <ambientLight intensity={0.35} />
        <directionalLight position={[10, 30, 10]} intensity={0.6} castShadow />
        <hemisphereLight args={['#9fb3c8', '#0b0d10', 0.25]} />
        <Building />
        <Fog which={which} />
        <AntennaPulse />
        <PlanZones />
        {which === 'reality' ? <RealityActors /> : <CommandActors />}
        <SyncedControls id={which} />
      </Canvas>
    </div>
  )
}
