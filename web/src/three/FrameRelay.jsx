import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { useSim } from '../store'
import { REPLAY } from '../net/replay'
import { captureJpeg, createFrameSender } from '../net/phoneFrames'
import Building from './Building'
import { EYE_FWD, EYE_H, HotSpots, Robots } from './RobotEye'
import { w2t } from './util'

// The big-screen half of the phone camera (Aziz's #152, DZ_PHONE_FRAMES): every robot's scout
// view, rendered from the scene in one small hidden canvas (320x180) that takes the robots in
// turn, 8 renders a second, so each robot gets about 2.7 frames a second. Each frame goes through
// Aziz's sender (net/phoneFrames.js): 320x180 JPEG, at most 3 per second per robot, and only
// while Command has a fresh report from that robot (delivered in the last 3 s), so a dark robot
// sends nothing and the phone shows NO SIGNAL. Mounted only when the server offers phone frames.
const TURNS_PER_S = 8 // about 2.7 frames a second per robot: under the server's 3 per second, with room for jitter

function Relay() {
  const { gl, scene, camera, invalidate } = useThree()
  const senders = useRef(new Map())
  const turn = useRef(0)
  const target = useMemo(() => document.createElement('canvas'), [])
  const lamp = useRef()
  const lampTarget = useMemo(() => new THREE.Object3D(), [])
  useEffect(() => {
    const id = setInterval(() => invalidate(), 1000 / TURNS_PER_S)
    const map = senders.current
    return () => { clearInterval(id); for (const sd of map.values()) sd.close(); map.clear() }
  }, [invalidate])
  useFrame(() => {
    const robots = useSim.getState().tick?.reality.robots ?? []
    if (!robots.length) return
    const r = robots[turn.current++ % robots.length]
    const [x, y, th] = r.pose
    const eye = new THREE.Vector3(...w2t(x + Math.cos(th) * EYE_FWD, y + Math.sin(th) * EYE_FWD, EYE_H))
    const ahead = new THREE.Vector3(...w2t(x + Math.cos(th) * 2, y + Math.sin(th) * 2, EYE_H - 0.3))
    camera.position.copy(eye)
    camera.lookAt(ahead)
    camera.updateMatrixWorld()
    if (lamp.current) { lamp.current.position.copy(eye); lampTarget.position.copy(ahead); lampTarget.updateMatrixWorld() }
    gl.render(scene, camera) // own the render so the capture reads it before the buffer clears
    let sd = senders.current.get(r.id)
    if (!sd) {
      sd = createFrameSender({ getState: useSim.getState, capture: (src) => captureJpeg(src, target) })
      senders.current.set(r.id, sd)
    }
    void sd.send(r.id, gl.domElement)
  }, 1)
  return (
    <>
      <primitive object={lampTarget} />
      <spotLight ref={lamp} target={lampTarget} angle={0.62} penumbra={0.5} intensity={14} distance={16} decay={1.5} color="#e8fbff" />
    </>
  )
}

function RelayScene() {
  const night = useSim((s) => s.night)
  return (
    <>
      <color attach="background" args={[night ? '#07080a' : '#0e1114']} />
      {night ? (
        <>
          <ambientLight intensity={0.12} />
          <hemisphereLight args={['#6f86b0', '#120f0c', 0.3]} />
        </>
      ) : (
        <>
          <ambientLight intensity={0.7} />
          <hemisphereLight args={['#e2e8f0', '#1f2937', 1.4]} />
        </>
      )}
      <fog attach="fog" args={[night ? '#07080a' : '#0e1114', night ? 5 : 8, night ? 20 : 26]} />
      <Building lite />
      <HotSpots thermal={false} />
      <Robots robotId={null} thermal={false} />
      <Relay />
    </>
  )
}

export default function FrameRelay() {
  const caps = useSim((s) => s.phoneFrames)
  if (REPLAY || !caps) return null
  return (
    <div className="frame-relay" aria-hidden>
      <Canvas key={caps.epoch} dpr={1} frameloop="demand" camera={{ fov: 85, near: 0.05, far: 60 }} gl={{ antialias: true }}>
        <RelayScene />
      </Canvas>
    </div>
  )
}
