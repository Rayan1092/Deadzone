import { useEffect } from 'react'
import { useSim } from '../store'
import { control } from '../net/socket'
import { STATE_LABEL, fmtClock as fmt } from '../format'
import { JoinCard } from './JoinPanel'

export function TopBar() {
  const fp = useSim((s) => s.floorplan)
  const time = useSim((s) => s.time)
  const stats = useSim((s) => s.tick?.stats)
  const connected = useSim((s) => s.connected)
  const running = useSim((s) => s.running)
  const speed = useSim((s) => s.speed)
  return (
    <header className="topbar">
      <div className="brand">DEADZONE</div>
      <div className="incident">{fp ? fp.name : 'Waiting for sim'}</div>
      <div className="clock mono">T+{fmt(time)}</div>
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
          <div key={r.id} className="robot-card" style={{ '--c': r.color }}>
            <div className="row">
              <span className="swatch" />
              <b>{r.name}</b>
              <span className={`pill ${r.link.up ? 'ok' : 'bad'}`}>{r.link.up ? `${r.link.rssi} dBm` : 'No link'}</span>
            </div>
            <div className="state">{STATE_LABEL[r.state] ?? r.state}{r.fault ? ` · ${r.fault}` : ''}</div>
            <div className="bar"><div className={low ? 'fill low' : 'fill'} style={{ width: `${pct}%` }} /></div>
            <div className="row muted small">
              <span>{pct.toFixed(0)}% battery</span>
              <span>{r.outbox} queued</span>
              <span>cmd sees {cmd ? `${(time - cmd.last_seen).toFixed(0)}s old` : 'nothing'}</span>
            </div>
          </div>
        )
      })}
      <h3>Events</h3>
      <div className="events">
        {events.filter((e) => !['link_up', 'link_down'].includes(e.kind)).slice(0, 14).map((e, i) => (
          <div key={i} className={`event ${e.kind}`}>
            <span className="mono muted">{fmt(e.time)}</span> {describe(e)}
          </div>
        ))}
      </div>
    </aside>
  )
}

function describe(e) {
  switch (e.kind) {
    case 'survivor_found': return `${e.robot} found ${e.survivor}${e.linked ? '' : ' (no link, holding report)'}`
    case 'survivor_reported': return `${e.survivor} reached command post (${e.delay_s}s after detection)`
    case 'link_lost': return `${e.robot} lost link, keeps exploring`
    case 'link_restored': return `${e.robot} link restored`
    case 'replan': return `${e.robot} replanned`
    case 'fault': return `${e.robot} fault: ${e.fault}`
    case 'rubble_fall': return 'Rubble fell'
    default: return e.kind
  }
}

export function useKeyboard() {
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT') return
      const s = useSim.getState()
      if (e.key === 'q' || e.key === 'Q') s.set({ joinOpen: !s.joinOpen })
      if (e.key === 'Escape') s.set({ joinOpen: false })
      if (e.code === 'Space') { e.preventDefault(); control('toggle') }
      if (e.code === 'Backspace') control('reset')
      if (e.key === '+' || e.key === '=') control('speed', s.speed * 2)
      if (e.key === '-') control('speed', s.speed / 2)
      if (e.key === 'r' || e.key === 'R') {
        // drop rubble 1.5 m ahead of the first robot (director key)
        const r = s.tick?.reality.robots[0]
        if (r) control('director', { do: 'rubble', at: [r.pose[0] + Math.cos(r.pose[2]) * 1.5, r.pose[1] + Math.sin(r.pose[2]) * 1.5] })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
