import { Fragment, useEffect } from 'react'
import { setNight, setPerf, setView, useSim } from '../store'
import { control } from '../net/socket'
import { FAULT_LABEL, STATE_LABEL, describeEvent, fmtClock as fmt, latestRoutes } from '../format'
import { JoinButton } from './JoinPanel'
import { requestReport } from './ReportPanel'
import { ReplayChip } from './ReplayPanel'
import { RECORDING, REPLAY, saveRecording } from '../net/replay'
import { followRobot, overview, resetOverview } from '../three/camera'

export const KEYS = [
  ['Space', 'start / pause'], ['1–3', 'follow robot (or click its card)'], ['0', 'overview'],
  ['R', 'rubble ahead of the robot'], ['F', 'wheel overcurrent'], ['O', 'perception overload'],
  ['U', 'resume after safe stop'], ['A', 'aftershock (server needs DZ_AFTERSHOCK=1)'], ['B', 'baseline: robots without Deadzone'], ['L', 'AI Lab: how the detector was trained'], ['K', 'night operations lighting'], ['D', 'auto camera (director)'], ['V', "robot's camera"], ['G', 'briefing'], ['T', 'truth overlay'],
  ['M', 'one view / split view'], ['P', 'performance mode'], ['Q', 'phone join QR'], ['S', 'save recording (?record)'],
  ['+ / −', 'speed'], ['⌫', 'reset'], ['?', 'this list'],
]

function toggleView() {
  resetOverview()
  setView(useSim.getState().view === 'gap' ? 'split' : 'gap')
}

// Rescue Status: the first thing a judge reads, in plain words. Found = the robots' own
// sightings (Reality); confirmed = those the onboard classifier scored as a person; reported
// and routes = only what reached the command post.
const AI_THRESHOLD = 0.6
const NONE_LIST = []
export function RescueStatus() {
  const time = useSim((s) => s.time)
  const found = useSim((s) => s.tick?.reality.survivors_found ?? NONE_LIST)
  const reported = useSim((s) => s.tick?.command.survivors.length ?? 0)
  const routes = useSim((s) => latestRoutes(s.tick?.command.routes ?? NONE_LIST).length)
  const ids = new Set(found.map((f) => f.id))
  const confirmed = new Set(found.filter((f) => (f.conf ?? 1) >= AI_THRESHOLD).map((f) => f.id)).size
  return (
    <div className="rescue-status" aria-label="Rescue status">
      <div className="rs-cell found"><b>{ids.size}</b><span>survivors found</span></div>
      <div className="rs-cell ai"><b>{confirmed}</b><span>confirmed by onboard AI</span></div>
      <div className={`rs-cell cmd${reported < ids.size ? ' behind' : ''}`}><b>{reported}</b><span>reported to command</span></div>
      <div className="rs-cell route"><b>{routes}</b><span>rescue routes ready</span></div>
      <div className="rs-cell time"><b className="mono">{fmt(time)}</b><span>since collapse</span></div>
    </div>
  )
}

export function TopBar() {
  const fp = useSim((s) => s.floorplan)
  const time = useSim((s) => s.time)
  const connected = useSim((s) => s.connected)
  const running = useSim((s) => s.running)
  const speed = useSim((s) => s.speed)
  const detector = useSim((s) => s.detector)
  const perf = useSim((s) => s.perf)
  const set = useSim((s) => s.set)
  const view = useSim((s) => s.view)
  const mode = useSim((s) => s.mode)
  const night = useSim((s) => s.night)
  return (
    <header className="topbar">
      <div className="brand">DEADZONE</div>
      <div className="incident">{fp ? fp.name : 'Waiting for sim'}</div>
      <div className="clock mono">T+{fmt(time)}</div>
      {detector && (
        <span className={`detector-chip ${detector.mode}`} title={detector.reason ?? ''}>
          Detector: {detector.mode === 'model' ? 'AI model' : 'sim fallback'}
        </span>
      )}
      <ReplayChip />
      {perf && <span className="perf-chip" title="Press P to turn off">Performance mode</span>}
      {night && <span className="perf-chip" title="Press K to turn off">Night ops</span>}
      {mode === 'baseline' && (
        <span className="baseline-chip" title="Press B to switch Deadzone back on">Baseline · without Deadzone</span>
      )}
      <div className="controls">
        <button onClick={() => control(running ? 'pause' : 'start')}>{running ? 'Pause' : 'Start'}</button>
        <button onClick={() => control('speed', speed / 2)}>-</button>
        <span className="mono">{speed}x</span>
        <button onClick={() => control('speed', speed * 2)}>+</button>
        <button onClick={() => control('reset')}>Reset</button>
        <button className="view-btn" title="Switch layout (M)" onClick={toggleView}>
          {view === 'gap' ? 'One view' : 'Split view'}
        </button>
        {!REPLAY && <JoinButton />}
        <button className="icon-btn" title="Keys (?)" onClick={() => set({ helpOpen: true })}>?</button>
        {!REPLAY && <span className={connected ? 'conn ok' : 'conn bad'}>{connected ? 'live' : 'offline'}</span>}
      </div>
    </header>
  )
}

function bars(link) {
  if (!link.up) return 0
  return link.rssi > -60 ? 4 : link.rssi > -70 ? 3 : link.rssi > -80 ? 2 : 1
}

function Signal({ link }) {
  const n = bars(link)
  return (
    <span className={`sig${n ? "" : " none"}`} title={link.up ? `${link.rssi} dBm` : 'No link'}>
      {n ? [1, 2, 3, 4].map((i) => <i key={i} className={i <= n ? 'on' : ''} />) : 'no link'}
    </span>
  )
}

// Compact robot cards; the followed robot's card opens up with the numbers.
export function Sidebar() {
  const tick = useSim((s) => s.tick)
  const time = useSim((s) => s.time)
  const events = useSim((s) => s.events)
  const follow = useSim((s) => s.follow)
  const eye = useSim((s) => s.eyeRobot)
  const robots = tick?.reality.robots ?? []
  const cmdRobots = Object.fromEntries((tick?.command.robots ?? []).map((r) => [r.id, r]))
  return (
    <aside className="sidebar">
      <h3>Robots</h3>
      {robots.map((r) => {
        const pct = r.battery.pct
        const low = pct < r.battery.reserve_needed_pct + 5
        const cmd = cmdRobots[r.id]
        const open = r.id === follow
        return (
          <div key={r.id} className={`robot-card${open ? ' followed' : ''}`} style={{ '--c': r.color }}
               title={open ? 'Click to stop following' : 'Click to follow'}
               onClick={() => (open ? overview() : followRobot(r.id))}>
            <div className="row">
              <span className="swatch" />
              <b>{r.name}</b>
              <button className={`cam-btn${eye === r.id ? ' on' : ''}`} title="Robot's camera (V)"
                      onClick={(e) => { e.stopPropagation(); useSim.getState().set({ eyeRobot: eye === r.id ? null : r.id }) }}>
                Camera
              </button>
              <Signal link={r.link} />
            </div>
            <div className="state">
              {STATE_LABEL[r.state] ?? r.state}
              {r.fault && <span className={`fault-pill ${r.fault === 'SAFE_STOP' ? 'stop' : ''}`}>{FAULT_LABEL[r.fault] ?? r.fault}</span>}
            </div>
            {r.fault === 'SAFE_STOP' && (
              // goes out as a radio command bundle; the robot needs a route to CMD to get it
              <button className="resume-btn" onClick={(e) => { e.stopPropagation(); control('director', { do: 'resume', robot: r.id }) }}>
                Send resume command
              </button>
            )}
            <div className="bar"><div className={low ? 'fill low' : 'fill'} style={{ width: `${pct}%` }} /></div>
            {open && (
              <div className="robot-detail muted small">
                {r.plan_id && <div className="following">Following {r.plan_id}{r.zone ? ` · zone ${r.zone}` : ''}</div>}
                <div className="row">
                  <span>{pct.toFixed(0)}% battery</span>
                  {r.wheel_a != null && (
                    <span className={`amps ${r.wheel_a >= 6 ? 'bad' : r.wheel_a >= 4 ? 'warn' : ''}`}>{r.wheel_a.toFixed(1)} A</span>
                  )}
                  <span title="Relays still carried">{'◆'.repeat(r.relays_left ?? 0) || 'no'} relays</span>
                </div>
                <div className="row">
                  <span>{r.outbox} queued</span>
                  <span>Command sees {cmd ? `${(time - cmd.last_seen).toFixed(0)}s old` : 'nothing'}</span>
                </div>
              </div>
            )}
          </div>
        )
      })}
      <h3>Events</h3>
      <div className="events">
        {events.slice(0, 10).map((e) => (
          <div key={e.eid} className={`event ${e.kind}`}>
            <i /><span className="mono muted">{fmt(e.time)}</span> {describeEvent(e)}
            {e.count > 1 && <span className="count">×{e.count}</span>}
          </div>
        ))}
      </div>
    </aside>
  )
}

export function HelpOverlay() {
  const open = useSim((s) => s.helpOpen)
  const set = useSim((s) => s.set)
  if (!open) return null
  return (
    <div className="help-overlay" onClick={() => set({ helpOpen: false })}>
      <div className="help-box">
        <b>Keys</b>
        <div className="keys">
          {KEYS.map(([k, what]) => <Fragment key={k}><kbd>{k}</kbd><span>{what}</span></Fragment>)}
        </div>
        <button className="text-link" onClick={(e) => { e.stopPropagation(); set({ helpOpen: false, introOpen: true }) }}>How to read this screen</button>
        <span className="muted small">Click anywhere or press Esc to close</span>
      </div>
    </div>
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
      if (e.key === 'Escape') s.set({ joinOpen: false, report: null, eyeRobot: null, helpOpen: false, labOpen: false, introOpen: false })
      if (key === 'l') s.set({ labOpen: !s.labOpen })
      if (key === 'k') setNight(!s.night)
      if (key === 'd') { if (s.director) overview(); s.set({ director: !s.director, shot: null }) }
      if (e.key === '?' || key === 'h') s.set({ helpOpen: !s.helpOpen })
      if (key === 'v' && target) s.set({ eyeRobot: s.eyeRobot === target.id ? null : target.id })
      if (key === 'p') setPerf(!s.perf)
      if (key === 'm') toggleView()
      if (key === 's' && RECORDING) saveRecording()
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
      if (key === 'o' && target) control('director', { do: 'overload', robot: target.id })
      if (key === 'u' && target) control('director', { do: 'resume', robot: target.id })
      // server picks the spot: the first powered relay (crushing it), else the corridor
      if (key === 'a') control('director', { do: 'aftershock' })
      // "without Deadzone": robots stop and wait whenever they lose the link
      if (key === 'b') control('mode', s.mode === 'baseline' ? 'deadzone' : 'baseline')
      if (key === 'g') {
        if (s.report && !s.report.loading) s.set({ report: null })
        else requestReport()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
