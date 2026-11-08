import { Fragment, useEffect, useState } from 'react'
import { setLayout, setNight, setPerf, setView, useSim } from '../store'
import { control } from '../net/socket'
import { FAULT_LABEL, describeEvent, fmtClock as fmt, latestRoutes, planCaption, robotStateLabel, unitName } from '../format'
import { lastContact, linkQuality, linkText } from './robotCard'
import { FILTERS, eventCategory, feedParts, readFilters, robotIds, saveFilters, visibleEvents } from './eventFeed'
import { JoinButton } from './JoinPanel'
import { requestReport } from './ReportPanel'
import { ReplayChip } from './ReplayPanel'
import { RECORDING, REPLAY, saveRecording } from '../net/replay'
import { followRobot, frameCommandPost, overview, resetOverview } from '../three/camera'
import { pickAftershock } from '../quake'
import { lock, presenterLocked, unlock } from '../net/presenter'
import { heldByOthers } from '../net/leaseState'
import { missingPeople, missingText } from '../three/beliefRamp'
import { ping, setSound, soundOn } from '../audio'

// Every line in sentence case, in the words the screen itself uses (no flags, no script words).
export const KEYS = [
  ['Space', 'Start / pause'], ['1–9', 'Follow that robot (or click its card)'], ['0', 'Overview'],
  ['R', 'Drop rubble ahead of the followed robot (robot 1 on the overview)'], ['F', 'Wheel overcurrent on the followed robot'], ['O', 'Perception overload on the followed robot'],
  ['U', 'Resume the followed robot after a safe stop'], ['A', 'Aftershock at a random spot (when aftershocks are turned on for this run)'], ['⇧A', 'Strong aftershock: three areas, two relays'], ['N', 'New random building'], ['⇧N', 'Back to the main building'], ['B', 'Baseline: robots without Deadzone (press Unlock first when the Operator lock is shown)'], ['L', 'Model Lab: how the detector was trained'], ['K', 'Night operations lighting'], ['D', 'Auto camera (director)'], ['V', "Robot's camera"], ['G', 'Briefing'], ['T', 'Truth overlay'],
  ['M', 'One view / split view'], ['C', 'One view: swap the command post inset and the main view · Split view: top-down on the command post'], ['Y', 'Belief map: where survivors may still be'], ['E', 'Operator view / Engineering view (sidebar, scheduler, legends)'], ['X', 'Sound cues on / off'], ['P', 'Performance mode'], ['Q', 'Join on phone (QR code)'], ['S', 'Save the mission recording (when this page is recording)'],
  ['J', 'Model test: guess before the AI on a held-out thermal image'], ['I', 'Under the hood: live system counters'],
  ['+ / −', 'Speed'], ['⌫', 'Reset'], ['?', 'This list'],
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
  // the command post's own estimate (what it can act on); the tooltip has the team's too
  const missing = useSim((s) => s.maps.missing)
  const unaccounted = missingPeople(missing?.command ?? missing?.reality)
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
      {unaccounted != null && (
        <div className="rs-cell missing" title={`Belief map estimate (${missingText(missing.command ?? missing.reality)}). Team: ${missing.reality?.toFixed?.(1) ?? '?'}, command post: ${missing.command?.toFixed?.(1) ?? '?'}`}>
          <b className="mono">≈{unaccounted}</b><span>still<br />unaccounted for</span>
        </div>
      )}
      <div className="rs-cell time"><b className="mono">{fmt(time)}</b><span>since collapse</span></div>
    </div>
  )
}

// Operator lock (control leases on): locked until this console takes the fleet; while it holds
// it, phones see every robot locked ("Console has control"). Shows who else holds a robot.
// Hidden when leases are off.
function PresenterLock() {
  const leases = useSim((s) => s.leases)
  const p = useSim((s) => s.presenter)
  const connected = useSim((s) => s.connected)
  if (!leases?.enabled) return null
  const others = heldByOthers(leases, p)
  return (
    <span className={`lock-chip ${p.held ? 'open' : 'locked'}`} role="status">
      <i />
      {p.held ? 'Console has control · field units locked out' : 'Operator lock'}
      {others.length > 0 && <small>{others.map((r) => `${r.robot}: ${unitName(r.controller.name)}`).join(' · ')}</small>}
      {!REPLAY && (
        <button disabled={p.pending || !connected} onClick={p.held ? lock : unlock}
                title={p.held ? 'Release the robots so field units can take them' : 'Take every robot for this console (needed for baseline mode and for resuming a stopped robot)'}>
          {p.pending ? '…' : p.held ? 'Lock' : 'Unlock'}
        </button>
      )}
    </span>
  )
}

export function TopBar() {
  const fp = useSim((s) => s.floorplan)
  const connected = useSim((s) => s.connected)
  const running = useSim((s) => s.running)
  const speed = useSim((s) => s.speed)
  const detector = useSim((s) => s.detector)
  const perf = useSim((s) => s.perf)
  const set = useSim((s) => s.set)
  const view = useSim((s) => s.view)
  const mode = useSim((s) => s.mode)
  const night = useSim((s) => s.night)
  const offline = !connected && !REPLAY
  return (
    <header className={`topbar${offline ? ' offline' : ''}`}>
      <div className="brand">DEADZONE</div>
      <div className="incident">{fp ? fp.name : 'Waiting for sim'}</div>
      {/* the run clock lives in the Rescue Status strip ("since collapse"); one clock on screen */}
      {detector && !offline && (
        <span className={`detector-chip ${detector.mode}`} title={detector.reason ?? ''}>
          Detector: {detector.mode === 'model' ? 'AI model' : 'simulated sensor (no AI model)'}
        </span>
      )}
      <ReplayChip />
      <PresenterLock />
      {perf && <span className="perf-chip" title="Press P to turn off">Performance mode</span>}
      {night && <span className="perf-chip" title="Press K to turn off">Night ops</span>}
      {mode === 'baseline' && (
        <span className="baseline-chip" title="Press B to switch Deadzone back on">Baseline · without Deadzone</span>
      )}
      <div className="controls">
        {/* with the server gone these do nothing, so they are disabled rather than silently ignored */}
        <button disabled={offline} onClick={() => control(running ? 'pause' : 'start')}>{running ? 'Pause' : 'Start'}</button>
        <button disabled={offline} title="Slower (−)" aria-label="Slower" onClick={() => control('speed', speed / 2)}>−</button>
        <span className="mono">{speed}x</span>
        <button disabled={offline} title="Faster (+)" aria-label="Faster" onClick={() => control('speed', speed * 2)}>+</button>
        <button disabled={offline} onClick={() => control('reset')}>Reset</button>
        <button className="view-btn" title="Switch layout (M)" onClick={toggleView}>
          {view === 'gap' ? 'One view' : 'Split view'}
        </button>
        {!REPLAY && <JoinButton />}
        <button className="icon-btn" title="Keys (?)" onClick={() => set({ helpOpen: true })}>?</button>
        <button title="Model test on a held-out thermal sample (J)" onClick={() => set({ judgeOpen: true, hoodOpen: false, labOpen: false })}>J · Model test</button>
        <button title="Live system counters (I)" onClick={() => set({ hoodOpen: true, judgeOpen: false, labOpen: false })}>I · Under the hood</button>
        {!REPLAY && (
          <span className={connected ? 'conn ok' : 'conn bad'} role="status"
                title={connected ? 'Connected to the simulator' : 'The simulator server is not answering; this screen reconnects by itself'}>
            {connected ? 'Live' : 'Server disconnected · reconnecting…'}
          </span>
        )}
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
  const q = linkQuality(link)
  return (
    <span className={`link-q ${q.cls}`} title="Best radio link to the command post">
      {n > 0 && <span className="sig">{[1, 2, 3, 4].map((i) => <i key={i} className={i <= n ? 'on' : ''} />)}</span>}
      <span className="link-word">{linkText(link)}</span>
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
  const leases = useSim((s) => s.leases)
  const leaseHolder = Object.fromEntries((leases?.enabled ? leases.robots : []).filter((l) => l.controller).map((l) => [l.robot, unitName(l.controller.name)]))
  const dispatched = useSim((s) => s.dispatchedPlans)
  const plan = useSim((s) => s.plan)
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
            </div>
            {leaseHolder[r.id] && <div className="lease-holder">{leaseHolder[r.id]} has control</div>}
            <div className="state">
              <span className="state-text">
                {robotStateLabel(r)}
                {r.fault && <span className={`fault-pill ${r.fault === 'SAFE_STOP' ? 'stop' : ''}`}>{FAULT_LABEL[r.fault] ?? r.fault}</span>}
              </span>
              <Signal link={r.link} />
            </div>
            {(() => {
              // the plan in plain words: "Scout 2 → Zone 3", or "plan pending · robot dark" (holding is the state line)
              const c = planCaption(r, { dispatched, plan })
              return c && c.kind !== 'holding' ? <div className={`plan-line ${c.kind}`}>{c.text}</div> : null
            })()}
            {lastContact(r.link, cmd, time) && (
              <div className="last-contact">Out of contact · last report {lastContact(r.link, cmd, time)} ago</div>
            )}
            {r.fault === 'SAFE_STOP' && (
              // goes out as a radio command bundle; the robot needs a route to CMD to get it
              <button className="resume-btn" onClick={(e) => { e.stopPropagation(); if (!presenterLocked()) control('director', { do: 'resume', robot: r.id }) }}>
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
      <EventFeed events={events} />
    </aside>
  )
}

// Plain-English event lines with each robot's name in its own colour, filtered by group.
function EventFeed({ events }) {
  const meta = useSim((s) => s.robotsMeta)
  const [active, setActive] = useState(readFilters)
  const toggle = (id) => {
    const next = new Set(active)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    saveFilters(next)
    setActive(next)
  }
  const counts = {}
  for (const e of events) {
    const c = eventCategory(e.kind)
    if (c) counts[c] = (counts[c] ?? 0) + 1
  }
  const shown = visibleEvents(events, active)
  return (
    <>
      <div className="feed-head">
        <h3>Events</h3>
        <div className="feed-chips" role="group" aria-label="Filter events">
          {FILTERS.map((f) => (
            <button key={f.id} className={`feed-chip ${f.id}${active.has(f.id) ? ' on' : ''}`} aria-pressed={active.has(f.id)}
                    onClick={(e) => { e.stopPropagation(); toggle(f.id) }}>
              {f.label}{counts[f.id] ? <small>{counts[f.id]}</small> : null}
            </button>
          ))}
        </div>
      </div>
      <div className="events">
        {shown.length === 0 && <div className="muted small">{active.size ? 'Nothing in these groups yet' : 'Pick a group to see its events'}</div>}
        {shown.map((e) => (
          <div key={e.eid} className={`event ${e.kind} cat-${eventCategory(e.kind) ?? 'note'}`}>
            <i /><span className="mono muted">{fmt(e.time)}</span>
            <span className="ev-text">
              {feedParts(describeEvent(e), robotIds(e), meta).map((p, i) => (p.robot
                ? <b key={i} className="ev-robot" style={{ '--c': p.robot.color }}>{p.robot.name}</b>
                : <Fragment key={i}>{p.text}</Fragment>))}
            </span>
            {e.count > 1 && <span className="count">×{e.count}</span>}
          </div>
        ))}
      </div>
    </>
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

// Key N: a new random building (Q&A only). Once the server can generate buildings
// (`generator: true` in /api/scenarios, reset with a seed) every press builds one from a fresh
// seed, and the "NEW SCENARIO" banner names it with that seed so it can be replayed. Until then
// it picks a random registered building. Shift+N goes back to the main building for the run.
const MAIN_SCENARIO = 'collapse_01'
const MAX_SEED = 99999

async function nextScenario(home) {
  const s = useSim.getState()
  const note = (msg) => s.set({ toasts: [...s.toasts, { kind: 'control_error', code: 'scenario', msg, time: s.time, eid: -Date.now(), at: Date.now() }].slice(-8) })
  let cat
  try {
    const res = await fetch('/api/scenarios')
    if (!res.ok) throw new Error(String(res.status))
    cat = await res.json()
  } catch {
    note('This server cannot switch buildings')
    return
  }
  const ids = (cat.floorplans ?? []).map((f) => f.id)
  if (home) {
    const main = ids.includes(MAIN_SCENARIO) ? MAIN_SCENARIO : ids[0]
    if (main) control('reset', { floorplan: main, timeline: false })
    else note('No building is registered on this server')
    return
  }
  if (cat.generator) {
    control('reset', { seed: 1 + Math.floor(Math.random() * MAX_SEED), timeline: false })
    return
  }
  const pool = ids.filter((id) => id !== cat.selected && id !== MAIN_SCENARIO)
  if (!pool.length) { note('No other building is registered on this server'); return }
  control('reset', { floorplan: pool[Math.floor(Math.random() * pool.length)], timeline: false })
}

export function useKeyboard() {
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest?.('input, textarea, select, [contenteditable="true"]')) return
      const s = useSim.getState()
      const robots = s.tick?.reality.robots ?? []
      // director keys act on the followed robot, else the first one
      const target = robots.find((r) => r.id === s.follow) ?? robots[0]
      const key = e.key.toLowerCase()
      // A modal's buttons keep their native Space/Enter behavior; data panels never drive the sim.
      if ((s.judgeOpen || s.hoodOpen) && !['escape', 'j', 'i'].includes(key)) return
      if (key === 'q') s.set({ joinOpen: !s.joinOpen })
      if (e.key === 'Escape') s.set({ joinOpen: false, report: null, eyeRobot: null, helpOpen: false, labOpen: false, introOpen: false, judgeOpen: false, hoodOpen: false })
      if (key === 'l') s.set({ labOpen: !s.labOpen, judgeOpen: false, hoodOpen: false })
      if (key === 'j' && !e.repeat) s.set({ judgeOpen: !s.judgeOpen, hoodOpen: false, labOpen: false })
      if (key === 'i' && !e.repeat) s.set({ hoodOpen: !s.hoodOpen, judgeOpen: false, labOpen: false })
      if (key === 'k') setNight(!s.night)
      if (key === 'd') { if (s.director) overview(); s.set({ director: !s.director, shot: null }) }
      if (e.key === '?' || key === 'h') s.set({ helpOpen: !s.helpOpen })
      if (key === 'v' && target) s.set({ eyeRobot: s.eyeRobot === target.id ? null : target.id })
      if (key === 'p') setPerf(!s.perf)
      if (key === 'm') toggleView()
      if (key === 'c' && !e.repeat) {
        if (s.view === 'gap') s.set({ insetSwap: !s.insetSwap })
        else frameCommandPost() // split view: top-down on the command post, again for the overview
      }
      if (key === 'y') { const on = !s.beliefOn; try { localStorage.setItem('dz-belief', on ? '1' : '0') } catch { /* session only */ } s.set({ beliefOn: on }) }
      if (key === 'e') {
        const next = s.layout === 'judge' ? 'full' : 'judge' // 'judge' is the stored id of the Operator view
        setLayout(next)
        s.set({ toasts: [...s.toasts, { kind: 'note', msg: next === 'judge' ? 'Operator view: map first, panels on hover' : 'Engineering view: every panel', time: s.time, eid: -Date.now(), at: Date.now() }].slice(-8) })
      }
      if (key === 'x') {
        setSound(!soundOn())
        s.set({ toasts: [...s.toasts, { kind: 'note', msg: soundOn() ? 'Sound cues on' : 'Sound cues off', time: s.time, eid: -Date.now(), at: Date.now() }].slice(-8) })
        if (soundOn()) ping()
      }
      if (key === 's' && RECORDING) saveRecording()
      if (key === 't') s.set({ showTruth: !s.showTruth })
      if (e.code === 'Space') { e.preventDefault(); control('toggle') }
      if (e.code === 'Backspace') control('reset')
      if (e.key === '+' || e.key === '=') control('speed', s.speed * 2)
      if (e.key === '-') control('speed', s.speed / 2)
      if (/^[1-9]$/.test(e.key) && robots[Number(e.key) - 1]) followRobot(robots[Number(e.key) - 1].id)
      if (e.key === '0') overview()
      if (key === 'r' && !e.repeat) {
        // rubble ahead of the robot the camera follows (1-3): Rayan's control {action: 'rubble',
        // robot}; on the overview no robot (the server means R1). With DZ_SMART_RUBBLE=1 it lands on
        // that robot's planned path 3-4 m ahead at a spot that traps nobody.
        const followed = robots.find((r) => r.id === s.follow)
        s.set({ rubbleAimed: { robot: followed?.id ?? 'R1', at: Date.now() }, pressedAt: { ...s.pressedAt, rubble: Date.now() } })
        control('rubble', undefined, followed ? { robot: followed.id } : {})
      }
      if (key === 'f' && target) control('director', { do: 'overcurrent', robot: target.id })
      if (key === 'o' && target) control('director', { do: 'overload', robot: target.id })
      if (key === 'u' && target && !presenterLocked()) control('director', { do: 'resume', robot: target.id })
      // server picks the spot: the first powered relay (crushing it), else the corridor
      if (key === 'a') s.set({ pressedAt: { ...s.pressedAt, aftershock: Date.now() } })
      if (key === 'a') control('director', { do: 'aftershock', ...(e.shiftKey ? { strength: 'strong' } : {}), ...pickAftershock(s) })
      if (key === 'n') nextScenario(e.shiftKey)
      // "without Deadzone": robots stop and wait whenever they lose the link
      if (key === 'b' && !presenterLocked()) control('mode', s.mode === 'baseline' ? 'deadzone' : 'baseline')
      if (key === 'g') {
        if (s.report && !s.report.loading) s.set({ report: null })
        else requestReport()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
