import * as THREE from 'three'
import { useSim } from '../store'

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
const VIEW_DIR = new THREE.Vector3(0, 50, 31).normalize() // default overview angle
export function fitOverview(camera, aspect) {
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
  shared.pos.copy(shared.target).addScaledVector(dir, Math.max(byWidth, byDepth) * 1.05)
  shared.home = { pos: shared.pos.clone(), target: shared.target.clone() }
}

const CHASE = new THREE.Vector3(0, 17, 12) // follow offset: above and south of the robot

export const CLOSE = new THREE.Vector3(0, 6.5, 7) // auto-director close shot

export function followRobot(rid, offset = CHASE) {
  shared.pos.copy(shared.target).add(offset)
  shared.src = null
  shared.rev++
  useSim.getState().set({ follow: rid })
}

export function overview() {
  useSim.getState().set({ follow: null })
  if (!shared.home) return
  shared.pos.copy(shared.home.pos)
  shared.target.copy(shared.home.target)
  shared.src = null
  shared.rev++
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
