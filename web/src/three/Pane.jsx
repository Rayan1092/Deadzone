import { useEffect, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import Building from './Building'
import Fog from './Fog'
import { RealityActors, CommandActors } from './Actors'
import { COLORS } from './util'

// Shared camera so the Reality and Command panes always show the same angle.
const shared = { pos: new THREE.Vector3(20, 50, 16), target: new THREE.Vector3(20, 0, -15), src: null, rev: 0 }

function SyncedControls({ id }) {
  const ctrl = useRef()
  const { camera } = useThree()
  const seen = useRef(-1)
  const applying = useRef(false)

  useEffect(() => {
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
  return (
    <div className={`pane pane-${which}`}>
      <div className="pane-title">
        <span className={`dot ${which}`} />
        <b>{title}</b>
        <span className="muted">{subtitle}</span>
      </div>
      <Canvas shadows dpr={[1, 2]} camera={{ fov: 50, near: 0.1, far: 300 }}>
        <color attach="background" args={[COLORS.bg]} />
        <fog attach="fog" args={[COLORS.bg, 90, 170]} />
        <ambientLight intensity={0.35} />
        <directionalLight position={[10, 30, 10]} intensity={0.6} castShadow />
        <hemisphereLight args={['#9fb3c8', '#0b0d10', 0.25]} />
        <Building />
        <Fog which={which} />
        {which === 'reality' ? <RealityActors /> : <CommandActors />}
        <SyncedControls id={which} />
      </Canvas>
    </div>
  )
}
