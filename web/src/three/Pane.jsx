import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Environment, Lightformer, OrbitControls } from '@react-three/drei'
import { Bloom, EffectComposer, N8AO, SMAA, ToneMapping, Vignette } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'
import * as THREE from 'three'
import Building from './Building'
import Fog from './Fog'
import { RealityActors, CommandActors, Shake } from './Actors'
import { AntennaPulse } from './Network'
import PlanZones from './PlanZones'
import { COLORS } from './util'
import { useSim } from '../store'
import { fitOverview, shared } from './camera'
import DetectionCards from '../panels/DetectionCards'
import RobotEye from './RobotEye'
import CommandInset from './CommandInset'

const GAP_COLUMN_PX = 330 // Command inset (300) + margins

// Late-afternoon sun from the south-west so every wall throws a readable shadow, a cool
// sky fill, and image-based light from a few soft panels (no HDR download) so metal,
// glass and polished concrete have something to reflect. The shadow frustum covers the
// whole site.
function Lights({ perf }) {
  const target = useMemo(() => {
    const t = new THREE.Object3D()
    t.position.set(19.5, 0, -15)
    return t
  }, [])
  return (
    <>
      <ambientLight intensity={0.08} />
      <hemisphereLight args={['#c4d3e6', '#2b2622', 0.35]} />
      <primitive object={target} />
      <directionalLight position={[2, 32, 0]} target={target} intensity={2.6} color="#ffe0b5"
                        castShadow={!perf} shadow-mapSize={[4096, 4096]} shadow-bias={-0.0004} shadow-normalBias={0.03}
                        shadow-camera-left={-34} shadow-camera-right={34}
                        shadow-camera-top={30} shadow-camera-bottom={-30} shadow-camera-far={100} />
      <Environment resolution={128} frames={1} environmentIntensity={0.55}>
        <Lightformer form="rect" intensity={1.6} color="#e6eefb" scale={[40, 40]} position={[0, 20, 0]} rotation-x={Math.PI / 2} />
        <Lightformer form="rect" intensity={2.2} color="#ffd2a1" scale={[30, 8]} position={[-25, 6, 10]} rotation-y={Math.PI / 2} />
        <Lightformer form="rect" intensity={0.8} color="#9cc3ff" scale={[30, 8]} position={[25, 6, -10]} rotation-y={-Math.PI / 2} />
        <Lightformer form="ring" intensity={1.2} color="#ffffff" scale={6} position={[0, 8, 25]} />
      </Environment>
    </>
  )
}

// The building never moves, so render the shadow map only while the scene settles
// (props, debris, textures) and when the floorplan changes, not every frame.
function StaticShadows() {
  const gl = useThree((s) => s.gl)
  const fp = useSim((s) => s.floorplan)
  const perf = useSim((s) => s.perf)
  const frames = useRef(0)
  useEffect(() => {
    gl.shadowMap.autoUpdate = false
    frames.current = 0
  }, [gl, fp, perf])
  useFrame(() => {
    if (frames.current < 30) { gl.shadowMap.needsUpdate = true; frames.current++ }
  })
  return null
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
      <Canvas shadows={!perf} dpr={perf ? 1 : [1, 1.5]} camera={{ fov: 50, near: 0.1, far: 300 }}
              gl={{ toneMapping: THREE.AgXToneMapping, toneMappingExposure: 1.1 }}>
        <color attach="background" args={[COLORS.bg]} />
        <fog attach="fog" args={[COLORS.bg, 80, 160]} />
        <Lights perf={perf} />
        <StaticShadows />
        {which === 'command' ? (
          <>
            <Building props={false} />
            <Fog which={which} />
            <AntennaPulse />
            <PlanZones />
            <CommandActors />
          </>
        ) : (
          <Shake>
            <Building />
            <Fog which={which} />
            <AntennaPulse />
            <PlanZones />
            <RealityActors gap={which === 'gap'} />
          </Shake>
        )}
        <SyncedControls id={which} />
        {!perf && (
          // contact shadows where walls, props and debris meet the floor; then only
          // materials pushed past the threshold bloom (robot LEDs, survivors, beacons)
          <EffectComposer multisampling={0}>
            <N8AO halfRes quality="performance" aoRadius={1.4} distanceFalloff={1} intensity={2.6} color="#0b0d10" />
            <Bloom mipmapBlur luminanceThreshold={0.95} luminanceSmoothing={0.25} intensity={which === 'command' ? 0.5 : 0.85} />
            <ToneMapping mode={ToneMappingMode.AGX} />
            <Vignette offset={0.32} darkness={0.5} />
            <SMAA />
          </EffectComposer>
        )}
      </Canvas>
    </div>
  )
}
