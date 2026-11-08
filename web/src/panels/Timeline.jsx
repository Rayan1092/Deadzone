import { useRef, useState } from 'react'
import { useSim } from '../store'
import { RM_BOUND, TASK_INFO, TASK_ORDER, deadlineTicks, frameLoad } from './scheduler'

// Each robot's rate monotonic scheduler (server/deadzone/robot/scheduler.py), as a Gantt chart of
// the latest 100 ms frame: one lane per task in priority order, plain names (Lidar scan, Plan,
// Radio, Map update, Thermal, Battery), a tick where each task's job is released and due, slices
// of the CPU each job got (a preempted job shows as several pieces), misses flashing red, and a
// utilization bar (CPU busy over the last second) with the Liu & Layland bound 0.735 marked.
// Collapsed by default to one calm line per robot; it opens by itself for the followed robot,
// when a deadline is missed or a robot is overloaded (the O beat), or when pinned open.
const MISS_HOLD_MS = 6000 // keep a miss on screen (and the panel open) this long
const BUSY_OPEN = 97      // % of a frame: overloaded enough to open the panel
const NONE = []

function readPinned() {
  try { return localStorage.getItem('dz-tl-open') === '1' } catch { return false }
}

// CPU busy per robot over the last 10 frames (1 s), one sample per tick
const history = new Map() // robot id -> { t, loads: [] }
function loadOf(r, time) {
  const h = history.get(r.id) ?? { t: -1, loads: [] }
  if (time !== h.t) {
    if (time < h.t) h.loads = [] // reset
    h.loads = [...h.loads, frameLoad(r.tasks ?? NONE)].slice(-10)
    h.t = time
    history.set(r.id, h)
  }
  return h.loads.length ? h.loads.reduce((a, b) => a + b, 0) / h.loads.length : 0
}

function Mini({ r, missed }) {
  const by = Object.fromEntries(TASK_ORDER.map((t) => [t, 0]))
  for (const t of r.tasks ?? NONE) by[t.name] = (by[t.name] ?? 0) + t.dur
  const busy = Math.round(Object.values(by).reduce((a, b) => a + b, 0))
  return (
    <div className={`tl-mini${missed ? ' miss' : ''}`} style={{ '--c': r.color }} title={`${r.name ?? r.id}: CPU busy ${busy}% of the last 100 ms`}>
      <i className="swatch" />
      <b>{r.id}</b>
      <span className="tl-stack">
        {TASK_ORDER.map((t) => by[t] > 0 && <i key={t} className={`task ${t}`} style={{ width: `${by[t]}%` }} />)}
      </span>
      <span className="mono">{busy}%</span>
    </div>
  )
}

function UtilBar({ u }) {
  const tone = u >= 1 ? 'over' : u > RM_BOUND ? 'warn' : ''
  return (
    <div className={`tl-util ${tone}`} title={`CPU busy over the last second: ${(u * 100).toFixed(0)}%. Rate monotonic scheduling guarantees every deadline while the load stays under ${RM_BOUND.toFixed(3)} for six tasks (Liu & Layland bound); above it, deadlines can be missed.`}>
      <span className="tl-util-bar"><i style={{ width: `${Math.min(100, u * 100)}%` }} /><b style={{ left: `${RM_BOUND * 100}%` }} /></span>
      <span className="mono">{u.toFixed(2)}</span>
      <span className="tl-util-bound mono">bound {RM_BOUND.toFixed(3)}</span>
    </div>
  )
}

function Gantt({ r, time, missedTask }) {
  const tasks = r.tasks ?? NONE
  const u = loadOf(r, time)
  return (
    <div className={`tl-gantt${missedTask ? ' miss' : ''}`} style={{ '--c': r.color }}>
      <div className="tl-gantt-head">
        <span className="tl-name"><i className="swatch" />{r.name ?? r.id}</span>
        <UtilBar u={u} />
        <span className={`tl-flag${missedTask ? ' on' : ''}`}>{missedTask ? `${TASK_INFO[missedTask]?.label ?? missedTask} missed its deadline` : 'all deadlines met'}</span>
      </div>
      {TASK_ORDER.map((name) => {
        const info = TASK_INFO[name]
        const slices = tasks.filter((t) => t.name === name)
        const missed = slices.some((t) => t.missed)
        return (
          <div key={name} className={`tl-lane${missed ? ' missed' : ''}`} title={`${info.label} · every ${info.period} ms, ${info.wcet} ms of CPU: ${info.why}`}>
            <span className="tl-lane-name">{info.label}</span>
            <div className="tl-lane-track">
              {deadlineTicks(time, info.period).map((p) => <i key={p} className="tl-tick" style={{ left: `${p}%` }} />)}
              {slices.map((t, i) => (
                <div key={i} className={`slice task ${name}${t.missed ? ' missed' : ''}`}
                     style={{ left: `${t.start}%`, width: `${Math.max(t.dur, 0.6)}%` }} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function Timeline() {
  const robots = useSim((s) => s.tick?.reality.robots) ?? NONE
  const time = useSim((s) => s.time)
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
        <button className="tl-title" onClick={toggle} aria-expanded={open} title={pinned ? 'Collapse the scheduler' : 'Keep the scheduler open'}>
          <b>Scheduler</b><i className={`tl-caret${open ? ' up' : ''}`} />
        </button>
        {!robots.length && <span className="muted">Waiting for robots</span>}
        {robots.map((r) => <Mini key={r.id} r={r} missed={!!missOf(r)} />)}
        {robots.length > 0 && <span className={`tl-status${worst ? ' bad' : ''}`}>
          <i />{worst ? `${worst.id}: ${TASK_INFO[missOf(worst)]?.label ?? missOf(worst)} missed a deadline` : 'All deadlines met'}
        </span>}
      </div>
      {open && (
        <div className="tl-body">
          <div className="tl-sub">
            <span className="muted" title="Fixed priorities by period: the task that must run most often always wins the CPU">
              Rate monotonic schedule · last 100 ms · ticks = job released and due{!pinned && !alert.length && followed.length ? ' · followed robot' : ''}
            </span>
            <div className="tl-legend">
              <span><i className="task missed" />missed deadline</span>
            </div>
          </div>
          {shown.map((r) => <Gantt key={r.id} r={r} time={time} missedTask={missOf(r)} />)}
          <div className="tl-axis mono"><span>0</span><span>25</span><span>50</span><span>75</span><span>100 ms</span></div>
        </div>
      )}
    </footer>
  )
}
