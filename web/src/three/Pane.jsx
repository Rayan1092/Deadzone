import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { Bloom, EffectComposer } from '@react-three/postprocessing'
import * as THREE from 'three'
import Building from './Building'
import Fog from './Fog'
import { RealityActors, CommandActors } from './Actors'
import { AntennaPulse } from './Network'
import PlanZones from './PlanZones'
import { COLORS } from './util'
import { useSim } from '../store'
import { fitOverview, shared } from './camera'
import DetectionCards from '../panels/DetectionCards'
import RobotEye from './RobotEye'
import CommandInset from './CommandInset'

const GAP_COLUMN_PX = 330 // Command inset (300) + margins

// Warm key light from the entrance side (west), cool sky fill. The shadow frustum covers
// the whole building (the default ±5 m only shaded one corner).
function Lights({ perf }) {
  const target = useMemo(() => {
    const t = new THREE.Object3D()
    t.position.set(20, 0, -15)
    return t
  }, [])
  return (
    <>
      <ambientLight intensity={0.28} />
      <hemisphereLight args={['#a9bfd6', '#0b0d10', 0.45]} />
      <primitive object={target} />
      <directionalLight position={[-6, 30, -4]} target={target} intensity={1.15} color="#ffe6c4"
                        castShadow={!perf} shadow-mapSize={[2048, 2048]} shadow-bias={-0.0005}
                        shadow-camera-left={-30} shadow-camera-right={30}
                        shadow-camera-top={30} shadow-camera-bottom={-30} shadow-camera-far={90} />
    </>
  )
}

function SyncedControls({ id }) {
  const ctrl = useRef()
  const { camera, size } = useThree()
  const seen = useRef(-1)
  const applying = useRef(false)
  const goal = useRef(new THREE.Vector3()).current

  // One view keeps a right-hand column free for the Command inset and AI cards: frame
  // the building in the rest and shift the projection so it sits centered there.
  const reserve = id === 'gap' ? GAP_COLUMN_PX : 0
  useEffect(() => {
    if (!size.width || !size.height) return
    if (reserve) camera.setViewOffset(size.width, size.height, reserve / 2, 0, size.width, size.height)
    else camera.clearViewOffset()
    camera.updateProjectionMatrix()
  }, [camera, size.width, size.height, reserve])

  // Fit once the canvas has a real size (a fresh canvas can report 0 on its first render).
  useEffect(() => {
    if (shared.home || !size.width || !size.height) return
    fitOverview(camera, Math.max(0.5, (size.width - reserve) / size.height))
    shared.rev++
  }, [camera, size.width, size.height, reserve])

  useEffect(() => {
    camera.position.copy(shared.pos)
    ctrl.current?.target.copy(shared.target)
    ctrl.current?.update()
  }, [camera])

  useFrame((_, dt) => {
    if (!ctrl.current) return
    // Follow mode: Reality tracks the robot, Command tracks its last reported pose,
    // so the Command camera never reveals where a dark robot really is.
    const { follow, tick } = useSim.getState()
    const robot = follow && (id === 'command' ? tick?.command.robots : tick?.reality.robots)?.find((r) => r.id === follow)
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
  const perf = useSim((s) => s.perf)
  const delivered = useSim((s) => s.tick?.stats.delivered ?? 0)
  const waiting = useSim((s) => s.tick?.stats.in_flight ?? 0)
  return (
    <div className={`pane pane-${which}`}>
      <div className="pane-title">
        <span className={`dot ${which}`} />
        <b>{title}</b>
        <span className="muted">{subtitle}</span>
        {which === 'command' && (
          <span className="pane-stats mono" title="Bundles delivered to the command post · still in transit">
            {delivered.toLocaleString()} delivered · {waiting} in transit
          </span>
        )}
        {which !== 'command' && showTruth && <span className="truth-chip">Truth overlay · T</span>}
        {follow && <span className="follow-chip">{which === 'command' ? `${follow} last report` : `Following ${follow}`} · 0</span>}
      </div>
      {which === 'gap' && (
        <div className="pane-legend">
          <span><i className="lg-link home" />Path home</span>
          <span><i className="lg-haze" />Not reported yet</span>
          <span><i className="lg-link tether" />Command's last fix</span>
          <span><i className="lg-route" />Rescue route</span>
          <span><i className="lg-relay" />Relay</span>
        </div>
      )}
      {which === 'reality' && (
        <div className="pane-legend">
          <span><i className="lg-link home" />Path home</span>
          <span><i className="lg-link up" />Radio link</span>
          <span><i className="lg-link weak" />Weak</span>
          <span><i className="lg-link down" />No link</span>
          <span><i className="lg-relay" />Relay</span>
        </div>
      )}
      <DetectionCards side={which} sides={which === 'gap' ? ['command', 'reality'] : undefined} />
      {which !== 'command' && <RobotEye />}
      {which === 'gap' && <CommandInset />}
      <Canvas shadows={!perf} dpr={perf ? 1 : [1, 1.5]} camera={{ fov: 50, near: 0.1, far: 300 }}>
        <color attach="background" args={[COLORS.bg]} />
        <fog attach="fog" args={[COLORS.bg, 90, 170]} />
        <Lights perf={perf} />
        <Building />
        <Fog which={which} />
        <AntennaPulse />
        <PlanZones />
        {which === 'command' ? <CommandActors /> : <RealityActors gap={which === 'gap'} />}
        <SyncedControls id={which} />
        {which !== 'command' && !perf && (
          // only materials pushed past the threshold bloom: robot LEDs, survivors, antenna
          <EffectComposer multisampling={4}>
            <Bloom mipmapBlur luminanceThreshold={0.9} luminanceSmoothing={0.25} intensity={0.9} />
          </EffectComposer>
        )}
      </Canvas>
    </div>
  )
}
