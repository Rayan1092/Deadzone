import { Component, Suspense, memo, useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Environment, Lightformer, OrbitControls } from '@react-three/drei'
import { Bloom, BrightnessContrast, EffectComposer, HueSaturation, N8AO, Noise, SMAA, ToneMapping, Vignette } from '@react-three/postprocessing'
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
import BeliefLayer from './Belief'
import DetectionCards from '../panels/DetectionCards'
import RobotEye from './RobotEye'
import CommandInset from './CommandInset'
import NightLights from './NightLights'

const GAP_COLUMN_PX = 330 // Command inset (300) + margins

// Late-afternoon sun from the south-west so every wall throws a readable shadow, a cool
// sky fill, and image-based light from a few soft panels (no HDR download) so metal,
// glass and polished concrete have something to reflect. The shadow frustum covers the
// whole site.
class EnvGuard extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

// Soft light panels instead of a sky photo (no download needed).
function PanelEnv({ night }) {
  return (
    <Environment resolution={128} frames={1} environmentIntensity={night ? 0.16 : 0.55}>
      <Lightformer form="rect" intensity={1.6} color="#e6eefb" scale={[40, 40]} position={[0, 20, 0]} rotation-x={Math.PI / 2} />
      <Lightformer form="rect" intensity={2.2} color="#ffd2a1" scale={[30, 8]} position={[-25, 6, 10]} rotation-y={Math.PI / 2} />
      <Lightformer form="rect" intensity={0.8} color="#9cc3ff" scale={[30, 8]} position={[25, 6, -10]} rotation-y={-Math.PI / 2} />
      <Lightformer form="ring" intensity={1.2} color="#ffffff" scale={6} position={[0, 8, 25]} />
    </Environment>
  )
}

function Lights({ perf, night }) {
  const fp = useSim((s) => s.floorplan)
  const [W, H] = fp?.size ?? [40, 30]
  const target = useMemo(() => {
    const t = new THREE.Object3D()
    t.position.set(W / 2, 0, -H / 2)
    return t
  }, [W, H])
  // earthquake: the lights stutter for the length of the shake (power flicker), then recover
  const amb = useRef()
  const hemi = useRef()
  const sun = useRef()
  const base = useRef(null)
  useFrame(() => {
    const a = useSim.getState().aftershock
    const age = a ? (performance.now() - a.born) / 1000 : Infinity
    const lights = [amb.current, hemi.current, sun.current]
    if (!lights.every(Boolean)) return
    if (age > 5.5) {
      if (base.current) { lights.forEach((l, i) => { l.intensity = base.current[i] }); base.current = null }
      return
    }
    base.current ??= lights.map((l) => l.intensity)
    const burst = Math.sin(age * 41) + Math.sin(age * 23.7) + Math.sin(age * 7.1)
    const f = age < 0.4 ? 0.25 : burst > 1.1 ? 0.3 : 1 - 0.25 * Math.max(0, 1 - age / 5.5)
    lights.forEach((l, i) => { l.intensity = base.current[i] * f })
  })
  return (
    <>
      <ambientLight ref={amb} intensity={night ? 0.06 : 0.08} />
      <hemisphereLight ref={hemi} args={night ? ['#7d92bd', '#1a1512', 0.42] : ['#c4d3e6', '#2b2622', 0.35]} />
      <primitive object={target} />
      {/* night: a weak cold moon instead of the afternoon sun */}
      <directionalLight ref={sun} position={[W / 2 - 17.5, 32, -H / 2 + 15]} target={target} intensity={night ? 1.25 : 2.6} color={night ? '#a7bbff' : '#ffe0b5'}
                        castShadow={!perf} shadow-mapSize={[4096, 4096]} shadow-bias={-0.0004} shadow-normalBias={0.03}
                        shadow-camera-left={-34} shadow-camera-right={34}
                        shadow-camera-top={30} shadow-camera-bottom={-30} shadow-camera-far={100} />
      {/* photo-scanned sky (CC0 HDRI) for light and reflections; soft panels if it can't load */}
      <EnvGuard fallback={<PanelEnv night={night} />}>
        <Suspense fallback={<PanelEnv night={night} />}>
          <Environment files={night ? '/assets/hdri/dikhololo_night_1k.hdr' : '/assets/hdri/industrial_sunset_puresky_1k.hdr'}
                       environmentIntensity={night ? 3.0 : 0.85} />
        </Suspense>
      </EnvGuard>
    </>
  )
}

// The building never moves, so render the shadow map only while the scene settles
// (props, debris, textures) and when the floorplan changes, not every frame.
// Night pushes the exposure up so the dark scene still reads; the lights stay the story.
function Exposure({ night }) {
  const gl = useThree((s) => s.gl)
  useEffect(() => { gl.toneMappingExposure = night ? 1.6 : 1.1 }, [gl, night])
  return null
}

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
  // A different map (or the floorplan arriving) needs a fresh fit too.
  const mapId = useSim((s) => s.floorplan?.id)
  useEffect(() => {
    if (shared.map !== mapId) { shared.home = null; shared.map = mapId }
    if (shared.home || !size.width || !size.height) return
    fitOverview(camera, Math.max(0.5, (size.width - reserve) / size.height))
    shared.rev++
  }, [camera, size.width, size.height, reserve, mapId])

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
      zoomToCursor // wheel zooms toward what is under the pointer; right-drag or shift-drag pans
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

// The live counters re-render every tick; kept out of Pane so the canvas (and the post-processing
// chain, which rebuilds and recompiles its passes whenever Pane re-renders) does not.
function PaneStats() {
  const delivered = useSim((s) => s.tick?.stats.delivered ?? 0)
  const waiting = useSim((s) => s.tick?.stats.in_flight ?? 0)
  return (
    <span className="pane-stats mono" title="Bundles delivered to the command post · still in transit">
      {delivered.toLocaleString()} delivered · {waiting} in transit
    </span>
  )
}

// contact shadows where walls, props and debris meet the floor; then only materials pushed
// past the threshold bloom (robot LEDs, survivors, beacons). Memoized: EffectComposer makes new
// effect passes (new shader programs) every time its children change.
const Grading = memo(function Grading({ which, night }) {
  return (
    <EffectComposer multisampling={0}>
      <N8AO halfRes quality="performance" aoRadius={1.4} distanceFalloff={1} intensity={2.6} color="#0b0d10" />
      {/* 5 mip levels at half resolution (rayan-ml's profile: ~30 bloom passes a frame before); same glow at projector distance */}
      <Bloom mipmapBlur levels={5} resolutionScale={0.5} luminanceThreshold={0.95} luminanceSmoothing={0.25} intensity={which === 'command' ? 0.5 : 0.85} />
      <ToneMapping mode={ToneMappingMode.AGX} />
      {/* disaster grading: drained color, a little more contrast, film grain */}
      <HueSaturation saturation={night ? -0.28 : -0.12} />
      <BrightnessContrast brightness={night ? 0.02 : 0} contrast={night ? 0.08 : 0.05} />
      <Vignette offset={0.3} darkness={night ? 0.75 : 0.5} />
      {night && <Noise premultiply opacity={0.65} />}
      <SMAA />
    </EffectComposer>
  )
})

// Command's view only changes when something reaches the antenna, so its canvas renders on demand.
// A change in what it shows (a robot's last report, survivors, routes, relays, faults, the map,
// the camera, the building) draws one frame: a ghost robot then jumps to its newly reported
// pose, which is what "last report" means. Only the antenna pulse after a big delivery keeps
// drawing, for its 0.7 s. Routine telemetry no longer keeps the pane rendering every frame.
const PULSE_MS = 900
function commandSignature(s) {
  const c = s.tick?.command
  return [c ? c.robots.map((r) => r.last_seen).join(',') : '', c?.survivors.length, c?.routes?.length, c?.relays.length, c?.faults?.length,
    s.maps.commandVersion, shared.rev, s.floorplan, s.night, s.follow, s.showTruth, s.beliefOn].join('|')
}
function CommandRedraw() {
  const invalidate = useThree((s) => s.invalidate)
  useEffect(() => {
    let raf = 0
    let until = 0
    let last = ''
    let lastBig = -1
    const loop = () => {
      const s = useSim.getState()
      const now = performance.now()
      const sig = commandSignature(s)
      if (sig !== last) { last = sig; invalidate() }
      if (s.bigDeliveries !== lastBig) { lastBig = s.bigDeliveries; until = now + PULSE_MS }
      if (now < until) invalidate()
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [invalidate])
  return null
}

// ?perfdebug: each pane's renderer and scene on window.__dzScenes, for profiling from the console
const PERF_DEBUG = (() => { try { return new URLSearchParams(location.search).has('perfdebug') } catch { return false } })()
function DebugExpose({ which }) {
  const { gl, scene } = useThree()
  useEffect(() => {
    if (!PERF_DEBUG) return undefined
    window.__dzScenes = { ...(window.__dzScenes ?? {}), [which]: { gl, scene } }
    window.__dzShared = shared
    return () => { if (window.__dzScenes) delete window.__dzScenes[which] }
  }, [gl, scene, which])
  return null
}

export default function Pane({ which, title, subtitle }) {
  const showTruth = useSim((s) => s.showTruth)
  const follow = useSim((s) => s.follow)
  const perf = useSim((s) => s.perf)
  const night = useSim((s) => s.night)
  const traffic = useSim((s) => s.traffic)
  return (
    <div className={`pane pane-${which}`}>
      <div className="pane-title">
        <span className={`dot ${which}`} />
        <b>{title}</b>
        <span className="muted">{subtitle}</span>
        {which === 'command' && <PaneStats />}
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
          {traffic && <span><i className="lg-packet" />Data packet</span>}
        </div>
      )}
      <DetectionCards side={which} sides={which === 'gap' ? ['command', 'reality'] : undefined} />
      {which !== 'command' && <RobotEye />}
      {which === 'gap' && <CommandInset />}
      <Canvas shadows={!perf} dpr={perf ? 1 : [1, 1.5]} camera={{ fov: 42, near: 0.1, far: 300 }} frameloop={which === 'command' ? 'demand' : 'always'}
              gl={{ toneMapping: THREE.AgXToneMapping, toneMappingExposure: 1.1 }}>
        <color attach="background" args={[night ? '#08090b' : COLORS.bg]} />
        {/* night: dust haze thickens with distance; day: plain depth fog */}
        {night ? <fogExp2 attach="fog" args={['#101216', 0.011]} /> : <fog attach="fog" args={[COLORS.bg, 80, 160]} />}
        <Lights perf={perf} night={night} />
        <Exposure night={night} />
        {night && which !== 'command' && <NightLights />}
        <StaticShadows />
        <DebugExpose which={which} />
        {which === 'command' ? (
          <>
            <CommandRedraw />
            <Building props={false} />
            <Fog which={which} />
            <BeliefLayer which={which === 'command' ? 'command' : 'reality'} />
            <AntennaPulse />
            <PlanZones />
            <CommandActors />
          </>
        ) : (
          <Shake>
            <Building />
            <Fog which={which} />
            <BeliefLayer which={which === 'command' ? 'command' : 'reality'} />
            <AntennaPulse />
            <PlanZones />
            <RealityActors gap={which === 'gap'} />
          </Shake>
        )}
        <SyncedControls id={which} />
        {!perf && <Grading which={which} night={night} />}
      </Canvas>
    </div>
  )
}
