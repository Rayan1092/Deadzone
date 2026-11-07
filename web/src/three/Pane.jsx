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
import { fitOverview, shared } from './camera'

function SyncedControls({ id }) {
  const ctrl = useRef()
  const { camera, size } = useThree()
  const seen = useRef(-1)
  const applying = useRef(false)
  const goal = useRef(new THREE.Vector3()).current

  useEffect(() => {
    if (!shared.home && size.width && size.height) fitOverview(camera, size.width / size.height)
    camera.position.copy(shared.pos)
    ctrl.current?.target.copy(shared.target)
    ctrl.current?.update()
  }, [camera])

  useFrame((_, dt) => {
    if (!ctrl.current) return
    // Follow mode: Reality tracks the robot, Command tracks its last reported pose,
    // so the Command camera never reveals where a dark robot really is.
    const { follow, tick } = useSim.getState()
    const robot = follow && (id === 'reality' ? tick?.reality.robots : tick?.command.robots)?.find((r) => r.id === follow)
    if (robot) {
      const offset = shared.pos.clone().sub(shared.target)
      ctrl.current.target.lerp(goal.set(robot.pose[0], 0, -robot.pose[1]), Math.min(1, dt * 4))
      applying.current = true
      camera.position.copy(ctrl.current.target).add(offset)
      ctrl.current.update()
      applying.current = false
      return
    }
    if (shared.src === id || seen.current === shared.rev) return
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
  const follow = useSim((s) => s.follow)
  return (
    <div className={`pane pane-${which}`}>
      <div className="pane-title">
        <span className={`dot ${which}`} />
        <b>{title}</b>
        <span className="muted">{subtitle}</span>
        {which === 'reality' && showTruth && <span className="truth-chip">Truth overlay · T</span>}
        {follow && <span className="follow-chip">{which === 'reality' ? `Following ${follow}` : `${follow} last report`} · 0</span>}
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
