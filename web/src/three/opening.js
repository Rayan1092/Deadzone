import { useEffect } from 'react'
import { useSim } from '../store'
import { shared } from './camera'
import { REPLAY } from '../net/replay'

// The opening shot: before the run starts the camera stands on the street west of the lot, at
// eye height past the ambulance, the command post and the damaged block's facade (night lighting
// and dust come with the scene, key K); when the run starts (Space) it dives into the overview in
// about 4 s. A reset back to a paused start sets it up again. It never fights the presenter: a
// drag, a follow key or the auto-director ends it, and a page opened mid-run skips it.
const DIVE_S = 4
const ease = (k) => (k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2)

export function openingView(fp) {
  const [W, H] = fp.size
  const ey = fp.entry?.[1] ?? H / 2
  // eye 2.2 m up in the street's south lane, looking north-east at the entry corner and the stubs
  return { pos: [-17.5, 2.2, -(ey - 13)], target: [W * 0.18, 3.2, -(ey + 2)] }
}

function setShot(pos, target) {
  shared.pos.set(...pos)
  shared.target.set(...target)
  shared.src = null
  shared.rev++
}

export function useOpening() {
  useEffect(() => {
    if (REPLAY) return undefined
    let phase = 'idle' // idle -> holding (street shot) -> diving -> done
    let lastTime = Infinity
    let from = null
    let born = 0
    let raf = 0
    const loop = () => {
      const s = useSim.getState()
      if (s.time + 1 < lastTime && s.time < 0.5) phase = 'idle' // a reset: offer the shot again
      lastTime = s.time
      const busy = s.follow || s.director
      if (phase === 'idle' && shared.home && s.floorplan && s.time < 0.5 && !s.running && !busy) {
        const v = openingView(s.floorplan)
        setShot(v.pos, v.target)
        phase = 'holding'
      } else if (phase === 'holding') {
        if (busy || (shared.src && shared.src !== null)) phase = 'done' // the presenter took the camera
        else if (s.running) {
          from = { pos: shared.pos.toArray(), target: shared.target.toArray() }
          born = performance.now()
          phase = 'diving'
        }
      } else if (phase === 'diving') {
        if (busy || shared.src) { phase = 'done' } else {
          const k = Math.min(1, (performance.now() - born) / 1000 / DIVE_S)
          const e = ease(k)
          const lerp = (a, b) => a.map((v, i) => v + (b[i] - v) * e)
          setShot(lerp(from.pos, shared.home.pos.toArray()), lerp(from.target, shared.home.target.toArray()))
          if (k >= 1) phase = 'done'
        }
      } else if (phase === 'done' && s.running) {
        // stays done until a reset brings time back to the start
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [])
}
