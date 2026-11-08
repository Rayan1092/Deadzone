import { useRef, useState } from 'react'
import { useSim } from '../store'

// Each robot's rate monotonic scheduler over the latest 100 ms frame (slices sorted, never
// overlapping; a preempted job shows as several pieces).
// Collapsed by default to one calm line: per robot a stacked bar of where its CPU time
// went and one status. It opens by itself for the followed robot, when a deadline is
// missed or a robot is overloaded (the O beat), or when the presenter pins it open.
const TASKS = ['safety', 'motion', 'comms', 'mapping', 'perception', 'battery']
const MISS_HOLD_MS = 6000 // keep a miss on screen (and the panel open) this long
const BUSY_OPEN = 85      // % of the frame: overloaded enough to open the panel
const NONE = []

function readPinned() {
  try { return localStorage.getItem('dz-tl-open') === '1' } catch { return false }
}

function usage(tasks) {
  const by = Object.fromEntries(TASKS.map((t) => [t, 0]))
  for (const t of tasks) by[t.name] = (by[t.name] ?? 0) + t.dur
  return by
}

function Mini({ r, tasks, missed }) {
  const by = usage(tasks)
  const busy = Math.round(Object.values(by).reduce((a, b) => a + b, 0))
  return (
    <div className={`tl-mini${missed ? ' miss' : ''}`} style={{ '--c': r.color }} title={`${r.name ?? r.id}: ${busy}% of the last 100 ms`}>
      <i className="swatch" />
      <b>{r.id}</b>
      <span className="tl-stack">
        {TASKS.map((t) => by[t] > 0 && <i key={t} className={`task ${t}`} style={{ width: `${by[t]}%` }} />)}
      </span>
      <span className="mono">{busy}%</span>
    </div>
  )
}

function Row({ r, tasks, missedTask }) {
  const busy = Math.round(tasks.reduce((sum, t) => sum + t.dur, 0))
  return (
    <div className={`tl-row${missedTask ? ' miss' : ''}`} style={{ '--c': r.color }}>
      <span className="tl-name"><i className="swatch" />{r.id}</span>
      <div className="tl-strip">
        {[10, 20, 30, 40, 50, 60, 70, 80, 90].map((ms) => <i key={ms} className={`tl-grid${ms % 50 ? '' : ' major'}`} style={{ left: `${ms}%` }} />)}
        {tasks.map((t, i) => (
          <div key={i} className={`slice task ${t.name}${t.missed ? ' missed' : ''}`} title={`${t.name} ${t.start}–${t.start + t.dur} ms${t.missed ? ' · missed its deadline' : ''}`}
               style={{ left: `${t.start}%`, width: `${Math.max(t.dur, 0.6)}%` }}>
            {t.dur >= 9 && <span>{t.name}</span>}
          </div>
        ))}
        {!tasks.length && <span className="tl-idle muted">no scheduler data</span>}
      </div>
      <span className={`tl-busy mono${busy >= BUSY_OPEN ? ' hot' : ''}`}>{busy}%</span>
      <span className={`tl-flag${missedTask ? ' on' : ''}`}>{missedTask ? `${missedTask} missed` : 'on time'}</span>
    </div>
  )
}

export default function Timeline() {
  const robots = useSim((s) => s.tick?.reality.robots) ?? NONE
  const follow = useSim((s) => s.follow)
  const lastMiss = useRef({}) // robot id -> { task, at }
  const [pinned, setPinned] = useState(readPinned)
  const now = Date.now()
  for (const r of robots) {
    const m = (r.tasks ?? NONE).find((t) => t.missed)
    if (m) lastMiss.current[r.id] = { task: m.name, at: now }
  }
  const missOf = (r) => {
    const m = lastMiss.current[r.id]
    return m && now - m.at < MISS_HOLD_MS ? m.task : null
  }
  const busyOf = (r) => (r.tasks ?? NONE).reduce((sum, t) => sum + t.dur, 0)
  const alert = robots.filter((r) => missOf(r) || busyOf(r) >= BUSY_OPEN)
  const followed = robots.filter((r) => r.id === follow)
  const shown = pinned ? robots : alert.length ? alert : followed
  const open = shown.length > 0
  const toggle = () => {
    const next = !pinned
    setPinned(next)
    try { localStorage.setItem('dz-tl-open', next ? '1' : '0') } catch { /* private mode */ }
  }
  const worst = robots.find((r) => missOf(r))
  return (
    <footer className={`timeline${open ? ' open' : ''}`}>
      <div className="tl-head">
        <button className="tl-title" onClick={toggle} aria-expanded={open} title={pinned ? 'Collapse' : 'Keep open'}>
          <b>Scheduler</b><i className={`tl-caret${open ? ' up' : ''}`} />
        </button>
        {!robots.length && <span className="muted">Waiting for robot telemetry</span>}
        {robots.map((r) => <Mini key={r.id} r={r} tasks={r.tasks ?? NONE} missed={!!missOf(r)} />)}
        <span className={`tl-status${worst ? ' bad' : ''}`}>
          <i />{worst ? `${worst.id} missed a ${missOf(worst)} deadline` : robots.length ? 'All deadlines met' : ''}
        </span>
      </div>
      {open && (
        <div className="tl-body">
          <div className="tl-sub">
            <span className="muted">Rate monotonic schedule · last 100 ms{!pinned && !alert.length && followed.length ? ' · followed robot' : ''}</span>
            <div className="tl-legend">
              {TASKS.map((t) => <span key={t}><i className={`task ${t}`} />{t}</span>)}
              <span><i className="task missed" />missed</span>
            </div>
          </div>
          {shown.map((r) => <Row key={r.id} r={r} tasks={r.tasks ?? NONE} missedTask={missOf(r)} />)}
          <div className="tl-axis mono"><span>0</span><span>25</span><span>50</span><span>75</span><span>100 ms</span></div>
        </div>
      )}
    </footer>
  )
}
