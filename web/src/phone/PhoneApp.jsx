import { useEffect, useState } from 'react'
import { FAULT_LABEL, STATE_LABEL, fmtClock } from '../format'
import { usePhone } from './store'
import { connectPhone, roleFromUrl } from './socket'
import { forkDispatched } from './plan'
import PlanMap from './PlanMap'
import PlanEditor from './PlanEditor'
import SafetyCard from './SafetyCard'
import RelayPanel from './RelayPanel'
import AskCard from './AskCard'
import './phone.css'

// Stable fallback: zustand selectors must not return a new [] on every call.
const NONE = []

// Keep the screen on while a responder has the page open (Safari 16.4+, Chrome).
function useWakeLock(active) {
  useEffect(() => {
    if (!active || !navigator.wakeLock) return
    let lock = null
    const request = () => navigator.wakeLock.request('screen').then((l) => { lock = l }).catch(() => {})
    const onVisible = () => document.visibilityState === 'visible' && request()
    request()
    document.addEventListener('visibilitychange', onVisible)
    return () => { document.removeEventListener('visibilitychange', onVisible); lock?.release() }
  }, [active])
}

function Landing({ onPick }) {
  return (
    <div className="phone-app landing">
      <div className="landing-head">
        <div className="brand">DEADZONE</div>
        <h1>Join the rescue</h1>
        <p className="muted">Robots are searching a collapsed building. Pick how you want to help.</p>
      </div>
      <button className="role-card" onClick={() => onPick('planner')}>
        <span className="role-icon planner" aria-hidden />
        <span>
          <b>Plan the search</b>
          <span className="muted">Draw zones, assign robots, run the safety check</span>
        </span>
      </button>
      <button className="role-card" onClick={() => onPick('relay')}>
        <span className="role-icon relay" aria-hidden />
        <span>
          <b>Be a relay</b>
          <span className="muted">Your phone carries robot data to the command post</span>
        </span>
      </button>
    </div>
  )
}

function Legend() {
  return (
    <div className="legend">
      <span><i className="sw scanned" />Scanned</span>
      <span><i className="sw hazard" />Hazard</span>
      <span><i className="sw relay" />Relay</span>
      <span><i className="sw survivor" />Survivor</span>
      <span><i className="sw ghost" />Old report</span>
      <span><i className="sw route" />Rescue route</span>
    </div>
  )
}

// The newest delivered survivor report from this robot, with the crop its detector judged.
function LastCrop({ robot, survivors }) {
  const last = survivors.filter((s) => s.by === robot).sort((a, b) => b.reported_t - a.reported_t)[0]
  const [failed, setFailed] = useState(false)
  if (!last) return <div className="last-crop empty muted small">No survivor reports from {robot} yet</div>
  return (
    <div className="last-crop">
      {last.crop && !failed
        ? <img src={`/crops/${last.crop}`} alt={`Thermal crop of ${last.id}`} onError={() => setFailed(true)} />
        : <div className="crop-ph" aria-hidden>thermal</div>}
      <div>
        <b>{last.id} · person{last.conf != null ? ` ${Math.round(last.conf * 100)}%` : ''}</b>
        <div className="muted small">Last thermal crop {robot} reported, T+{fmtClock(last.reported_t)}</div>
      </div>
    </div>
  )
}

function RobotList() {
  const robots = usePhone((s) => s.hello?.robots ?? NONE)
  const reported = usePhone((s) => s.view?.robots ?? NONE)
  const faults = usePhone((s) => s.view?.faults ?? NONE)
  const survivors = usePhone((s) => s.view?.survivors ?? NONE)
  const [open, setOpen] = useState(null)
  const byId = Object.fromEntries(reported.map((r) => [r.id, r]))
  const faultById = Object.fromEntries(faults.map((f) => [f.robot, f]))
  return robots.map((meta) => {
    const r = byId[meta.id]
    const fault = faultById[meta.id]
    const caps = meta.capabilities ?? {}
    const isOpen = open === meta.id
    return (
      <div key={meta.id} className={`m3-card robot${isOpen ? ' open' : ''}`} style={{ '--c': meta.color }}
           role="button" tabIndex={0} aria-expanded={isOpen}
           onClick={() => setOpen(isOpen ? null : meta.id)}>
        <div className="robot-row">
          <i className="swatch" />
          <b>{meta.name}</b>
          <span className="muted">{meta.id}</span>
          <span className={`chip ${r ? (r.stale_s > 3 ? 'warn' : 'ok') : ''}`}>
            {r ? (r.stale_s > 3 ? `${Math.round(r.stale_s)}s old` : 'Reporting') : 'No report yet'}
          </span>
        </div>
        {r ? (
          <>
            <div className="robot-state">{STATE_LABEL[r.state] ?? r.state}</div>
            {r.plan_id && (
              <div className="following small">Following {r.plan_id}{r.zone ? ` · zone ${r.zone}` : ''} (last report)</div>
            )}
            <div className="bar"><div className="fill" style={{ width: `${r.battery_pct}%` }} /></div>
            <div className="muted small">{Math.round(r.battery_pct)}% battery at last report</div>
            {fault && (
              <div className="reported-fault small">
                Reported fault: {FAULT_LABEL[fault.fault] ?? fault.fault} at T+{fmtClock(fault.reported_t)}
              </div>
            )}
          </>
        ) : (
          <div className="muted small">Waiting for this robot's first report to reach the antenna</div>
        )}
        {isOpen && <LastCrop robot={meta.id} survivors={survivors} />}
        <div className="caps muted small">
          {caps.stairs ? 'Can climb stairs' : 'No stairs'} · {caps.max_rubble_height ? `Rubble up to ${caps.max_rubble_height} m` : 'No rubble climbing'}
          <span className="tap-hint">{isOpen ? 'Tap to close' : 'Tap for last crop'}</span>
        </div>
      </div>
    )
  })
}

function Survivors() {
  const survivors = usePhone((s) => s.view?.survivors ?? NONE)
  if (!survivors.length) {
    return <div className="m3-card empty muted">None reported yet. Robots hold findings until they get signal.</div>
  }
  return survivors.map((s) => (
    <div key={s.id} className="m3-card survivor">
      <i className="dot-red" />
      <div>
        <b>{s.id}</b> <span className="muted">found by {s.by}</span>
        <div className="muted small">
          Reported at T+{fmtClock(s.reported_t)} · {s.delay_s}s after detection
        </div>
      </div>
    </div>
  ))
}

function Snackbar() {
  const error = usePhone((s) => s.error)
  const [shown, setShown] = useState(null)
  useEffect(() => {
    if (!error) return
    setShown(error)
    const id = setTimeout(() => setShown(null), 4000)
    return () => clearTimeout(id)
  }, [error])
  return shown ? <div className="snackbar">{shown.msg}</div> : null
}

function Shell({ role }) {
  const hello = usePhone((s) => s.hello)
  const error = usePhone((s) => s.error)
  const checking = usePhone((s) => s.checking)
  // Another phone dispatched this plan ID first; keep editing under a new ID.
  useEffect(() => { if (!checking && error?.code === 'plan_dispatched') forkDispatched() }, [error, checking])
  const connected = usePhone((s) => s.connected)
  const time = usePhone((s) => s.time)
  return (
    <div className="phone-app">
      <header className="appbar">
        <div className="appbar-title">
          <div className="brand">DEADZONE</div>
          <div className="incident">{hello?.floorplan.name ?? 'Connecting…'}</div>
        </div>
        <span className="mono clock">T+{fmtClock(time)}</span>
        <span className={`chip ${connected ? 'ok' : 'bad'}`}>{connected ? 'Live' : 'Offline'}</span>
      </header>

      {role === 'relay' && <RelayPanel />}

      <section className="m3-card map-card">
        <div className="card-head">
          <b>Command view</b>
          <span className="muted small">Only what reached the antenna</span>
        </div>
        <PlanMap />
        <Legend />
      </section>

      {role === 'planner' && <PlanEditor />}
      {role === 'planner' && <SafetyCard />}

      <AskCard />


      <h2 className="section-title">Robots</h2>
      <RobotList />

      <h2 className="section-title">Survivors reported</h2>
      <Survivors />

      <footer className="phone-foot muted small">
        {hello ? `${hello.client} · ${hello.role}` : role}
      </footer>
      <Snackbar />
    </div>
  )
}

export default function PhoneApp() {
  const [role, setRole] = useState(roleFromUrl)
  useEffect(() => (role ? connectPhone(role) : undefined), [role])
  useWakeLock(Boolean(role))
  if (!role) {
    return (
      <Landing onPick={(picked) => {
        const url = new URL(location.href)
        url.searchParams.set('role', picked)
        history.replaceState(null, '', url)
        setRole(picked)
      }} />
    )
  }
  return <Shell role={role} />
}
