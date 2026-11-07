import { useEffect } from 'react'
import { useSim } from '../store'
import { control } from '../net/socket'
import { FAULT_LABEL, STATE_LABEL, describeEvent, fmtClock as fmt } from '../format'
import { JoinCard } from './JoinPanel'
import { requestReport } from './ReportPanel'
import { followRobot, overview } from '../three/camera'

// Radio edges flap constantly and deliveries happen every tick; the feed shows stories.
const HIDDEN_EVENTS = new Set(['link_up', 'link_down', 'bundle_delivered'])

export function TopBar() {
  const fp = useSim((s) => s.floorplan)
  const time = useSim((s) => s.time)
  const stats = useSim((s) => s.tick?.stats)
  const found = useSim((s) => new Set(s.tick?.reality.survivors_found.map((f) => f.id)).size)
  const reported = useSim((s) => s.tick?.command.survivors.length ?? 0)
  const connected = useSim((s) => s.connected)
  const running = useSim((s) => s.running)
  const speed = useSim((s) => s.speed)
  return (
    <header className="topbar">
      <div className="brand">DEADZONE</div>
      <div className="incident">{fp ? fp.name : 'Waiting for sim'}</div>
      <div className="clock mono">T+{fmt(time)}</div>
      <div className="survivor-count" title="Found by robots vs known at the command post">
        <span><b>{found}</b> found</span>
        <span className={reported < found ? 'gap' : ''}><b>{reported}</b> reported</span>
      </div>
      <div className="stats">
        <span><b>{stats?.robots ?? 0}</b> robots</span>
        <span><b>{stats?.relays ?? 0}</b> relays</span>
        <span><b>{stats?.links_up ?? 0}</b> links up</span>
        <span><b>{stats?.in_flight ?? 0}</b> bundles waiting</span>
        <span><b>{stats?.delivered ?? 0}</b> delivered</span>
      </div>
      <div className="controls">
        <button onClick={() => control(running ? 'pause' : 'start')}>{running ? 'Pause' : 'Start'}</button>
        <button onClick={() => control('speed', speed / 2)}>-</button>
        <span className="mono">{speed}x</span>
        <button onClick={() => control('speed', speed * 2)}>+</button>
        <button onClick={() => control('reset')}>Reset</button>
        <span className={connected ? 'conn ok' : 'conn bad'}>{connected ? 'live' : 'offline'}</span>
      </div>
    </header>
  )
}

export function Sidebar() {
  const tick = useSim((s) => s.tick)
  const time = useSim((s) => s.time)
  const events = useSim((s) => s.events)
  const follow = useSim((s) => s.follow)
  const robots = tick?.reality.robots ?? []
  const cmdRobots = Object.fromEntries((tick?.command.robots ?? []).map((r) => [r.id, r]))
  return (
    <aside className="sidebar">
      <JoinCard />
      <h3>Robots</h3>
      {robots.map((r) => {
        const pct = r.battery.pct
        const low = pct < r.battery.reserve_needed_pct + 5
        const cmd = cmdRobots[r.id]
        return (
          <div key={r.id} className={`robot-card${r.id === follow ? ' followed' : ''}`} style={{ '--c': r.color }}
               onClick={() => (r.id === follow ? overview() : followRobot(r.id))}>
            <div className="row">
              <span className="swatch" />
              <b>{r.name}</b>
              <span className={`pill ${r.link.up ? 'ok' : 'bad'}`}>{r.link.up ? `${r.link.rssi} dBm` : 'No link'}</span>
            </div>
            <div className="state">
              {STATE_LABEL[r.state] ?? r.state}
              {r.fault && <span className={`fault-pill ${r.fault === 'SAFE_STOP' ? 'stop' : ''}`}>{FAULT_LABEL[r.fault] ?? r.fault}</span>}
            </div>
            {r.plan_id && <div className="following muted small">Following {r.plan_id}{r.zone ? ` · zone ${r.zone}` : ''}</div>}
            <div className="bar"><div className={low ? 'fill low' : 'fill'} style={{ width: `${pct}%` }} /></div>
            <div className="row muted small">
              <span>{pct.toFixed(0)}% battery</span>
              {r.wheel_a != null && (
                <span className={`amps ${r.wheel_a >= 6 ? 'bad' : r.wheel_a >= 4 ? 'warn' : ''}`}>{r.wheel_a.toFixed(1)} A</span>
              )}
              <span title="Relays still carried">{'◆'.repeat(r.relays_left ?? 0) || 'no'} relays</span>
            </div>
            <div className="row muted small">
              <span>{r.outbox} queued</span>
              <span>cmd sees {cmd ? `${(time - cmd.last_seen).toFixed(0)}s old` : 'nothing'}</span>
            </div>
          </div>
        )
      })}
      <h3>Events</h3>
      <div className="events">
        {events.filter((e) => !HIDDEN_EVENTS.has(e.kind)).slice(0, 14).map((e) => (
          <div key={e.eid} className={`event ${e.kind}`}>
            <i /><span className="mono muted">{fmt(e.time)}</span> {describeEvent(e)}
            {e.count > 1 && <span className="count">×{e.count}</span>}
          </div>
        ))}
      </div>
    </aside>
  )
}

export function useKeyboard() {
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT') return
      const s = useSim.getState()
      const robots = s.tick?.reality.robots ?? []
      // director keys act on the followed robot, else the first one
      const target = robots.find((r) => r.id === s.follow) ?? robots[0]
      const key = e.key.toLowerCase()
      if (key === 'q') s.set({ joinOpen: !s.joinOpen })
      if (e.key === 'Escape') s.set({ joinOpen: false, report: null })
      if (key === 't') s.set({ showTruth: !s.showTruth })
      if (e.code === 'Space') { e.preventDefault(); control('toggle') }
      if (e.code === 'Backspace') control('reset')
      if (e.key === '+' || e.key === '=') control('speed', s.speed * 2)
      if (e.key === '-') control('speed', s.speed / 2)
      if (/^[1-9]$/.test(e.key) && robots[Number(e.key) - 1]) followRobot(robots[Number(e.key) - 1].id)
      if (e.key === '0') overview()
      if (key === 'r' && target) {
        // drop rubble 1.5 m ahead of the robot
        const [x, y, th] = target.pose
        control('director', { do: 'rubble', at: [x + Math.cos(th) * 1.5, y + Math.sin(th) * 1.5] })
      }
      if (key === 'f' && target) control('director', { do: 'overcurrent', robot: target.id })
      if (key === 'g') {
        if (s.report && !s.report.loading) s.set({ report: null })
        else requestReport()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
