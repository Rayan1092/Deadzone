import { useRef } from 'react'
import { useSim } from '../store'

// Each robot's rate monotonic scheduler over the latest 100 ms frame. Slices are
// sorted and never overlap; a preempted job shows as several pieces.
const TASKS = ['safety', 'motion', 'comms', 'mapping', 'perception', 'battery']
const MISS_HOLD_MS = 1500 // keep a miss visible after it scrolls out of the frame

export default function Timeline() {
  const robots = useSim((s) => s.tick?.reality.robots)
  const lastMiss = useRef({}) // robot id -> { task, at }
  const now = Date.now()
  return (
    <footer className="timeline">
      <div className="tl-head">
        <b>Scheduler</b>
        <span className="muted">last 100 ms per robot</span>
        <div className="tl-legend">
          {TASKS.map((t) => <span key={t}><i className={`task ${t}`} />{t}</span>)}
          <span><i className="task missed" />missed deadline</span>
        </div>
      </div>
      {!robots?.length && <div className="tl-empty muted">Waiting for robot telemetry</div>}
      {robots?.map((r) => {
        const tasks = r.tasks ?? []
        const missed = tasks.find((t) => t.missed)
        if (missed) lastMiss.current[r.id] = { task: missed.name, at: now }
        const recent = lastMiss.current[r.id]
        const showMiss = recent && now - recent.at < MISS_HOLD_MS
        const busy = Math.round(tasks.reduce((sum, t) => sum + t.dur, 0))
        return (
          <div key={r.id} className={`tl-row${showMiss ? ' miss' : ''}`} style={{ '--c': r.color }}>
            <span className="tl-name"><i className="swatch" />{r.id}</span>
            <div className="tl-strip">
              {[25, 50, 75].map((ms) => <i key={ms} className="tl-grid" style={{ left: `${ms}%` }} />)}
              {tasks.map((t, i) => (
                <div key={i} className={`slice task ${t.name}${t.missed ? ' missed' : ''}`} title={`${t.name} ${t.start}–${t.start + t.dur} ms`}
                     style={{ left: `${t.start}%`, width: `${Math.max(t.dur, 0.6)}%` }} />
              ))}
              {!tasks.length && <span className="tl-idle muted">no scheduler data</span>}
            </div>
            <span className="tl-busy mono">{busy}%</span>
            <span className={`tl-flag${showMiss ? ' on' : ''}`}>{showMiss ? `${recent.task} missed` : ''}</span>
          </div>
        )
      })}
    </footer>
  )
}
