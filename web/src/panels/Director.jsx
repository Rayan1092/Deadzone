import { useEffect, useRef } from 'react'
import { useSim } from '../store'
import { CLOSE, followRobot, orbit, overview } from '../three/camera'

// Auto-director (D): the camera cuts to what matters, like a broadcast. A robot going
// dark or finding someone gets a close follow shot; a report reaching the command post
// (the reveal), an aftershock or a rerouted rescue route gets the wide shot; with nothing
// happening it swings slowly around the building. Any manual camera input (drag, 0-9)
// hands control back to the presenter for a while.
const HOLD_MS = 9000      // a close shot lasts this long, then back to the wide shot
const MIN_GAP_MS = 4000   // don't cut again sooner, unless the news is bigger
const IDLE_MS = 12000     // quiet this long: start the slow orbit
const MANUAL_PAUSE_MS = 20000
const ORBIT_RAD_S = 0.05

function shotFor(ev, names) {
  const who = names[ev.robot ?? ev.by] ?? ev.robot ?? ev.by
  switch (ev.kind) {
    case 'link_lost': return { rank: 3, robot: ev.robot, caption: `${who} lost its link, still searching` }
    case 'survivor_found': return { rank: 4, robot: ev.robot, caption: `${who} found ${ev.survivor}` }
    case 'fault': return { rank: 2, robot: ev.robot, caption: `${who}: fault` }
    case 'survivor_reported': return { rank: 5, caption: `${ev.survivor} reached the command post` }
    case 'aftershock': return { rank: 5, caption: 'Aftershock' }
    case 'rescue_route_reported': return ev.updated ? { rank: 3, caption: `Route to ${ev.survivor} rerouted` } : null
    default: return null
  }
}

export function useDirector() {
  const last = useRef({ eid: 0, at: 0, rank: 0, until: 0, manualUntil: 0 })
  useEffect(() => {
    const st = last.current
    // presenter takes over: dragging a 3D view or pressing a camera key
    const manual = () => { st.manualUntil = performance.now() + MANUAL_PAUSE_MS }
    const onPointer = (e) => { if (e.target.tagName === 'CANVAS') manual() }
    const onKey = (e) => { if (/^[0-9]$/.test(e.key)) manual() }
    window.addEventListener('pointerdown', onPointer)
    window.addEventListener('wheel', onPointer, { passive: true })
    window.addEventListener('keydown', onKey)

    const unsub = useSim.subscribe((s, prev) => {
      if (!s.director || s.events === prev.events) return
      const ev = s.events[0]
      if (!ev || ev.eid === st.eid) return
      st.eid = ev.eid
      const now = performance.now()
      if (now < st.manualUntil) return
      const names = Object.fromEntries(s.robotsMeta.map((r) => [r.id, r.name]))
      const shot = shotFor(ev, names)
      if (!shot) return
      if (now - st.at < MIN_GAP_MS && shot.rank <= st.rank) return
      st.at = now
      st.rank = shot.rank
      if (shot.robot) { followRobot(shot.robot, CLOSE); st.until = now + HOLD_MS } else { overview(); st.until = now + 6000 }
      s.set({ shot: { caption: shot.caption, at: Date.now() } })
    })

    let raf = 0
    let prevT = performance.now()
    const tick = (t) => {
      const dt = Math.min(0.1, (t - prevT) / 1000)
      prevT = t
      const s = useSim.getState()
      if (s.director && t > st.manualUntil) {
        if (st.until && t > st.until) { st.until = 0; st.rank = 0; overview(); s.set({ shot: null }) }
        if (!st.until && t - st.at > IDLE_MS && s.running) orbit(ORBIT_RAD_S * dt)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      unsub()
      cancelAnimationFrame(raf)
      window.removeEventListener('pointerdown', onPointer)
      window.removeEventListener('wheel', onPointer)
      window.removeEventListener('keydown', onKey)
    }
  }, [])
}

// "Auto camera" caption over the main view while the director is on.
export function DirectorChip() {
  const on = useSim((s) => s.director)
  const shot = useSim((s) => s.shot)
  if (!on) return null
  return (
    <div className="director-chip" aria-live="polite">
      <i />Auto camera{shot ? <span> · {shot.caption}</span> : null}
    </div>
  )
}
