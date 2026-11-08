import * as THREE from 'three'
import { useSim } from '../store'
import { commandPostLayout } from './furniture'

// Shared camera so the Reality and Command panes always show the same angle.
// `pos - target` is the shared view offset (orbit angle + zoom). In follow mode
// each pane keeps that offset but centres on its own idea of the robot.
export const shared = {
  pos: new THREE.Vector3(19.5, 50, 16),
  target: new THREE.Vector3(19.5, 0, -15),
  home: null,  // fitted overview { pos, target } for the 0 key
  map: null,   // floorplan id the overview was fitted for
  src: null,   // pane the user is dragging
  rev: 0,      // bumps whenever pos/target change
}

// Pull the overview camera back along its viewing direction until the whole
// building (plus the CMD antenna west of it) fits the pane, whatever its shape.
// default overview: a low perspective from the south-west (about 34 degrees up), not a
// top-down plan view, which reads as a scale model
const VIEW_DIR = new THREE.Vector3(-0.42, 0.56, 0.72).normalize()

// ?cam=px,py,pz,tx,ty,tz[,fov] (three.js coordinates: y up, z = -north) pins the camera, so
// before/after screenshots and video takes use the exact same angle.
const CAM = (() => {
  try {
    const v = new URLSearchParams(location.search).get('cam')
    const n = v ? v.split(',').map(Number) : []
    return n.length >= 6 && n.every(Number.isFinite) ? n : null
  } catch { return null }
})()

export function fitOverview(camera, aspect) {
  if (CAM) {
    shared.pos.set(CAM[0], CAM[1], CAM[2])
    shared.target.set(CAM[3], CAM[4], CAM[5])
    if (CAM[6]) { camera.fov = CAM[6]; camera.updateProjectionMatrix() }
    shared.home = { pos: shared.pos.clone(), target: shared.target.clone() }
    return
  }
  // frame the building plus the command post (and its truck) outside it, whatever the map
  let VIEW_W = 48
  let VIEW_D = 32
  const fp = useSim.getState().floorplan
  if (fp) {
    const [W, H] = fp.size
    const [cx, cy] = fp.command_post.pos
    const x0 = Math.min(-0.5, cx - 3.5)
    const x1 = Math.max(W + 0.5, cx + 3.5)
    const y0 = Math.min(-1, cy - 3.5)
    const y1 = Math.max(H + 1, cy + 3.5)
    VIEW_W = x1 - x0 + 2
    VIEW_D = y1 - y0
    shared.target.set((x0 + x1) / 2, 0, -(y0 + y1) / 2)
    shared.pos.copy(shared.target).addScaledVector(VIEW_DIR, 60)
  }
  const dir = shared.pos.clone().sub(shared.target).normalize()
  const elevation = Math.asin(dir.y)
  const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)
  const byWidth = VIEW_W / 2 / (tanV * aspect)
  const byDepth = (VIEW_D * Math.sin(elevation)) / 2 / tanV
  shared.pos.copy(shared.target).addScaledVector(dir, Math.max(byWidth, byDepth) * 1.12)
  shared.home = { pos: shared.pos.clone(), target: shared.target.clone() }
}

const CHASE = new THREE.Vector3(0, 9, 11) // follow offset: low, south of the robot

export const CLOSE = new THREE.Vector3(0, 3.2, 6.5) // auto-director close shot, eye-level cinematic

export function followRobot(rid, offset = CHASE) {
  shared.pos.copy(shared.target).add(offset)
  shared.src = null
  shared.rev++
  useSim.getState().set({ follow: rid })
}

export function overview() {
  useSim.getState().set({ follow: null })
  shared.cmdFramed = false
  if (!shared.home) return
  shared.pos.copy(shared.home.pos)
  shared.target.copy(shared.home.target)
  shared.src = null
  shared.rev++
}

// C in split view: look down on the command post (the tent, the operators, the mast every radio
// link ends at); C again returns to the overview.
export function frameCommandPost() {
  const fp = useSim.getState().floorplan
  if (!fp?.command_post) return
  if (shared.cmdFramed) { overview(); return }
  const [mx, my] = fp.command_post.pos
  const { tent } = commandPostLayout(fp.command_post.pos, fp.entry)
  const [x, y] = [(mx + tent[0]) / 2, (my + tent[1]) / 2] // between the mast and the operators' canopy
  useSim.getState().set({ follow: null })
  shared.target.set(x, 0.8, -y)
  shared.pos.set(x + 5, 12, -y + 8) // from above at about 45 degrees: the tent, the operators and the mast together
  shared.src = null
  shared.rev++
  shared.cmdFramed = true
}

// A new layout means a new pane shape: forget the fitted overview so the next pane refits.
export function resetOverview() {
  shared.pos.set(19.5, 50, 16)
  shared.target.set(19.5, 0, -15)
  shared.home = null
  shared.src = null
  shared.rev++
  useSim.getState().set({ follow: null })
}

// Auto-director idle shot: swing slowly around the building.
const UP = new THREE.Vector3(0, 1, 0)
export function orbit(angle) {
  if (useSim.getState().follow) return
  shared.pos.sub(shared.target).applyAxisAngle(UP, angle).add(shared.target)
  shared.src = null
  shared.rev++
}
