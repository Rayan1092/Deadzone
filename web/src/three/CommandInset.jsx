import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import Line from './FastLine' // drei's Line relinks its shader on every new points array
import { useSim } from '../store'
import Building from './Building'
import CoverageLayer, { CoverageLegend } from './Coverage'
import { w2t } from './util'
import { latestRoutes, lastContact, CONTACT_STALE_S, freshDelivery } from '../format'

// One view's Command post inset: what the command post knows, as a top-down blueprint, from
// delivered data only (tick.command; the floor plan drawn without truth rubble). This is the
// "no cheating" story when the presenter runs one view: a robot that goes dark greys out at its
// last reported spot with a "last contact N s" counter, and a survivor appears only when its
// report is delivered, with a short pulse. C swaps it with the main view for the reveal.
const NONE = []
const PULSE_S = 1.2        // one ring when the report arrives, then the marker stays still
const PULSES = 1
const PAD_SMALL = { t: 40, r: 10, b: 10, l: 10 }
// swapped: clear of the status strip and title (top) and of the building view, now the smaller box
// in the bottom right (styles.css .pane-gap.swapped > .pane-view, 32% wide) with the AI cards above it
const SWAP_FRAC = 0.32
const padBig = (width) => ({ t: 120, r: Math.round(width * SWAP_FRAC) + 40, b: 48, l: 24 })

// Fit the building into the canvas minus the padding, north up, and center it in what is left.
function TopDown({ big }) {
  const { camera, size } = useThree()
  const fp = useSim((s) => s.floorplan)
  useEffect(() => {
    if (!fp || !size.width || !size.height) return
    const [W, H] = fp.size
    const p = big ? padBig(size.width) : PAD_SMALL
    const zoom = Math.max(1, Math.min((size.width - p.l - p.r) / (W + 2), (size.height - p.t - p.b) / (H + 2)))
    const dx = (p.l - p.r) / 2 / zoom // building center moves right by dx, down by dy
    const dy = (p.t - p.b) / 2 / zoom
    camera.up.set(0, 0, -1) // north up
    camera.position.set(W / 2 - dx, 60, -H / 2 - dy)
    camera.lookAt(W / 2 - dx, 0, -H / 2 - dy)
    camera.zoom = zoom
    camera.updateProjectionMatrix()
  }, [camera, size.width, size.height, fp, big])
  return null
}

// The map as Command knows it (maps.command, from delivered map patches only): floor it has
// mapped is lit, walls and debris it has seen are bright, the frontier edge teal; what it has
// not heard about stays dark. Updates only when Command's own map changes.
function CommandMap() {
  const grid = useSim((s) => s.grid)
  const version = useSim((s) => s.maps.commandVersion)
  const tex = useMemo(() => {
    if (!grid) return null
    const t = new THREE.DataTexture(new Uint8Array(grid.w * grid.h * 4), grid.w, grid.h, THREE.RGBAFormat)
    t.magFilter = THREE.NearestFilter
    t.minFilter = THREE.LinearFilter
    t.needsUpdate = true
    return t
  }, [grid])
  useEffect(() => () => tex?.dispose(), [tex])
  useEffect(() => {
    const map = useSim.getState().maps.command
    if (!tex || !map || map.length !== tex.image.width * tex.image.height) return
    const px = tex.image.data
    const { w } = grid
    const unknownAt = (i) => map[i] === 0
    for (let i = 0; i < map.length; i++) {
      const v = map[i]
      const o = i * 4
      const x = i % w
      const edge = v === 1 && ((x > 0 && unknownAt(i - 1)) || (x < w - 1 && unknownAt(i + 1)) || unknownAt(i - w) || unknownAt(i + w))
      const [r, g, b, a] = v === 2 ? [191, 219, 254, 235] : edge ? [94, 234, 212, 170] : v === 1 ? [37, 99, 235, 95] : [0, 0, 0, 0]
      px[o] = r; px[o + 1] = g; px[o + 2] = b; px[o + 3] = a
    }
    tex.needsUpdate = true
  }, [version, tex, grid])
  if (!tex || !grid) return null
  const W = grid.w * grid.cell
  const H = grid.h * grid.cell
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, 0.02)} renderOrder={0}>
      <planeGeometry args={[W, H]} />
      <meshBasicMaterial map={tex} transparent depthWrite={false} toneMapped={false} />
    </mesh>
  )
}

function Dot({ pos, color, r = 0.55 }) {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(pos[0], pos[1], 2)}>
      <circleGeometry args={[r, 24]} />
      <meshBasicMaterial color={color} />
    </mesh>
  )
}

// Robot at its last reported pose. Dark (no report for CONTACT_STALE_S): grey ring + counter.
// A robot that reported its own shutdown (mission done) is not dark, it is off.
function RobotMark({ robot, color, age }) {
  const off = robot.state === 'SHUTDOWN'
  const dark = off || age > CONTACT_STALE_S
  return (
    <group position={w2t(robot.pose[0], robot.pose[1], 2.1)}>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        {dark ? <ringGeometry args={[0.38, 0.62, 24]} /> : <circleGeometry args={[0.62, 24]} />}
        <meshBasicMaterial color={dark ? '#64748b' : color} />
      </mesh>
      <Html zIndexRange={[3, 0]} style={{ pointerEvents: 'none' }}>
        <div className={`inset-tag${dark ? ' dark' : ''}`} style={dark ? undefined : { borderColor: color }}>
          <b>{robot.id}</b>{off ? <span>powered down</span> : dark && <span>last contact {lastContact(age)}</span>}
        </div>
      </Html>
    </group>
  )
}

// A delivered survivor. Pulses when its report arrives while this screen is watching (not
// after a reload: freshDelivery checks the report's own time).
function SurvivorMark({ survivor, time }) {
  const ring = useRef()
  const born = useRef(null)
  if (born.current === null) born.current = freshDelivery(survivor, time) ? performance.now() : 0
  useFrame(() => {
    const m = ring.current
    if (!m) return
    const t = born.current ? (performance.now() - born.current) / 1000 / PULSE_S : PULSES
    m.visible = t < PULSES
    if (!m.visible) return
    const k = t % 1
    const sc = 1 + k * 3.2
    m.scale.set(sc, sc, 1)
    m.material.opacity = 0.95 * (1 - k)
  })
  return (
    <group position={w2t(survivor.pos[0], survivor.pos[1], 2.2)}>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.8, 24]} />
        <meshBasicMaterial color="#f59e0b" />
      </mesh>
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} visible={false}>
        <ringGeometry args={[0.8, 1.05, 32]} />
        <meshBasicMaterial color="#fbbf24" transparent depthWrite={false} />
      </mesh>
      <Html zIndexRange={[3, 0]} style={{ pointerEvents: 'none' }}>
        <div className="inset-tag survivor"><b>{survivor.id}</b></div>
      </Html>
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
      {cmd.survivors.map((s) => <SurvivorMark key={s.id} survivor={s} time={time} />)}
      {cmd.robots.map((r) => (
        <RobotMark key={r.id} robot={r} color={colors[r.id] ?? '#2dd4bf'} age={time - r.last_seen} />
      ))}
    </group>
  )
}

export default function CommandInset({ big = false }) {
  const swap = () => useSim.getState().set({ insetSwap: !useSim.getState().insetSwap })
  return (
    <div className={`cmd-inset${big ? ' big' : ''}`}>
      <div className="inset-head">
        <i className="dot command" />
        <b>Command post</b><span>· knows only what was delivered</span>
        <CoverageLegend className="in-inset" />
        <button type="button" className="inset-swap" onClick={swap}
                title={big ? 'Back to the building view (C)' : 'Show the command post view full screen (C)'}>⇄ <kbd>C</kbd></button>
      </div>
      {big && (
        <div className="pane-legend inset-legend">
          <span><i className="lg-known" />Mapped by Command</span>
          <span><i className="lg-robot" />Robot, last report</span>
          <span><i className="lg-robot dark" />No contact</span>
          <span><i className="lg-survivor" />Survivor, report delivered</span>
          <span><i className="lg-route" />Rescue route</span>
          <span><i className="lg-relay" />Relay</span>
        </div>
      )}
      <Canvas orthographic dpr={big ? [1, 1.5] : 1} gl={{ antialias: true, powerPreference: 'low-power' }}
              camera={{ position: [20, 60, -15], zoom: 6, near: 0.1, far: 200 }}>
        <color attach="background" args={['#081325']} />
        <ambientLight intensity={1.1} />
        <CommandMap />
        <CoverageLayer />
        <Building blueprint />
        <Known />
        <TopDown big={big} />
      </Canvas>
    </div>
  )
}
