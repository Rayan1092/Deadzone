import * as THREE from 'three'
import { useSim } from '../store'

// Shared camera so the Reality and Command panes always show the same angle.
// `pos - target` is the shared view offset (orbit angle + zoom). In follow mode
// each pane keeps that offset but centres on its own idea of the robot.
export const shared = {
  pos: new THREE.Vector3(20, 50, 16),
  target: new THREE.Vector3(20, 0, -15),
  home: null,  // fitted overview { pos, target } for the 0 key
  src: null,   // pane the user is dragging
  rev: 0,      // bumps whenever pos/target change
}

// Pull the overview camera back along its viewing direction until the whole
// building (plus the CMD antenna west of it) fits the pane, whatever its shape.
const VIEW_W = 44 // m, x from -3 to 41
const VIEW_D = 32 // m, y from -1 to 31
export function fitOverview(camera, aspect) {
  const dir = shared.pos.clone().sub(shared.target).normalize()
  const elevation = Math.asin(dir.y)
  const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)
  const byWidth = VIEW_W / 2 / (tanV * aspect)
  const byDepth = (VIEW_D * Math.sin(elevation)) / 2 / tanV
  shared.pos.copy(shared.target).addScaledVector(dir, Math.max(byWidth, byDepth) * 1.05)
  shared.home = { pos: shared.pos.clone(), target: shared.target.clone() }
}

const CHASE = new THREE.Vector3(0, 17, 12) // follow offset: above and south of the robot

export function followRobot(rid) {
  shared.pos.copy(shared.target).add(CHASE)
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
