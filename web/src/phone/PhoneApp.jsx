import { useEffect, useState } from 'react'
import { FAULT_LABEL, fmtClock, robotStateLabel } from '../format'
import { usePhone } from './store'
import { connectPhone, roleFromUrl } from './socket'
import { forkDispatched } from './plan'
import PlanMap from './PlanMap'
import PlanEditor from './PlanEditor'
import SafetyCard from './SafetyCard'
import RelayPanel from './RelayPanel'
import AskCard from './AskCard'
import { ControlPanel, RobotCamera, useLeaseHeartbeat } from './RobotControl'
import { isDark } from './control'
import { connectionLabel, probeServer, publicText, robotName } from './labels'
import './phone.css'

const NONE = []

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

function Header({ title, status, children }) {
  return <header className="appbar">
    <div className="appbar-title"><div className="brand">Deadzone</div><h1>{title}</h1></div>
    <span className={`chip ${status === 'live' ? 'ok' : 'warn'}`}>{connectionLabel(status)}</span>
    {children}
  </header>
}

function ConnectionBanner({ status }) {
  if (status === 'live') return null
  return <section className="m3-card connection-banner" role="status" aria-live="polite">
    <b>{connectionLabel(status)}</b>
    <p>{status === 'connecting' ? 'Connecting to the command post. Please wait.'
      : status === 'reconnecting' ? 'Connection lost. Reconnecting automatically. Your unsaved plan stays on this phone.'
      : 'The server is not responding. Use the same Wi-Fi as the laptop or open its tunnel link. We will keep trying.'}</p>
  </section>
}

function Landing({ onPick }) {
  const [status, setStatus] = useState('connecting')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let closed = false, next, ctrl
    const check = async () => {
      ctrl = new AbortController()
      const timeout = setTimeout(() => ctrl.abort(), 5000)
      const ok = await probeServer(ctrl.signal)
      clearTimeout(timeout)
      if (closed) return
      setStatus(ok ? 'live' : 'unreachable')
      next = setTimeout(check, 5000)
    }
    setStatus('connecting')
    check()
    return () => { closed = true; clearTimeout(next); ctrl?.abort() }
  }, [retry])
  return <div className="phone-app landing">
    <Header title="Join the rescue" status={status} />
    <ConnectionBanner status={status} />
    <div className="landing-head"><h2>How would you like to help?</h2><p className="muted">Choose a robot, plan the search or help carry radio messages.</p></div>
    {[
      ['Control a robot', 'View its last camera image and send instructions.', 'planner', 'robots'],
      ['Plan the search', 'Draw search areas and keep robots out of unsafe areas.', 'planner', 'plan'],
      ['Extend radio coverage', 'Use this phone as a relay for robot messages.', 'relay', 'relay'],
    ].map(([title, detail, role, page]) => <button className="role-card" key={page} disabled={status !== 'live'} onClick={() => onPick(role, page)}>
      <span className={`role-icon ${role}`} aria-hidden="true" /><span><b>{title}</b><span className="muted">{detail}</span></span>
    </button>)}
    {status === 'unreachable' && <button className="text-btn" onClick={() => setRetry((n) => n + 1)}>Try again</button>}
    <p className="hint">No app to install. Keep this page open while you help.</p>
  </div>
}

function MapSection() {
  return <section className="m3-card map-card" aria-label="Search map">
    <div className="card-head"><b>Search map</b><span className="muted small">Reports received at the command post</span></div>
    <PlanMap />
    <div className="legend">{[['scanned', 'Mapped'], ['hazard', 'No-go'], ['relay', 'Relay'], ['survivor', 'Survivor'], ['ghost', 'Last known position'], ['route', 'Rescue route']].map(([kind, title]) => <span key={kind}><i className={`sw ${kind}`} />{title}</span>)}</div>
  </section>
}

function RobotPicker({ onPick }) {
  const robots = usePhone((s) => s.hello?.robots ?? NONE)
  const reports = usePhone((s) => s.view?.robots ?? NONE)
  if (!robots.length) return <section className="m3-card" role="status">Waiting for the robot list.</section>
  return <div className="robot-picker">{robots.map((meta) => {
    const r = reports.find((report) => report.id === meta.id)
    return <button key={meta.id} className="m3-card robot-choice" style={{ '--c': meta.color }} onClick={() => onPick(meta.id)}>
      <i className="robot-dot" /><span><b>{meta.name}</b><span className="muted small">{r ? robotStateLabel(r) : 'Waiting for a report'}</span></span>
      <span className={`chip ${isDark(r) ? 'warn' : 'ok'}`}>{isDark(r) ? 'Robot dark' : 'In contact'}</span>
      <span aria-hidden="true">›</span>
    </button>
  })}</div>
}

function RobotScreen({ meta, onBack }) {
  const report = usePhone((s) => s.view?.robots?.find((r) => r.id === meta.id))
  const fault = usePhone((s) => s.view?.faults?.find((r) => r.robot === meta.id))
  return <>
    <button className="text-btn" onClick={onBack}>Back to robots</button>
    <section className="m3-card robot-detail" style={{ '--c': meta.color }}>
      <div className="card-head"><h2>{meta.name}</h2><span className={`chip ${isDark(report) ? 'warn' : 'ok'}`}>{isDark(report) ? 'Robot dark' : 'In contact'}</span></div>
      {isDark(report) && <p className="hint">{report ? `Last contact ${Math.round(report.stale_s)} seconds ago. The image and position are from that report.` : 'No report has reached the command post yet.'}</p>}
      {report && <><p>{robotStateLabel(report)}</p><progress max="100" value={report.battery_pct} aria-label="Last reported battery" /><p className="hint">{Math.round(report.battery_pct)}% battery at last report</p></>}
      {fault && <p className="reported-fault">{FAULT_LABEL[fault.fault] ?? 'A fault was reported'} at {fmtClock(fault.reported_t)}</p>}
      <RobotCamera meta={meta} report={report} />
      <ControlPanel meta={meta} />
    </section>
  </>
}

function Survivors() {
  const survivors = usePhone((s) => s.view?.survivors ?? NONE)
  const robots = usePhone((s) => s.hello?.robots ?? NONE)
  return <section className="m3-card"><h2>Survivors reported</h2>{!survivors.length
    ? <p className="muted">No survivors reported yet. Robots keep findings until they regain signal.</p>
    : survivors.map((s, i) => <div key={s.id} className="survivor"><i className="dot-red" /><div><b>Survivor {i + 1}</b><p className="hint">Reported by {robotName(s.by, robots)} at {fmtClock(s.reported_t)}.</p></div></div>)}</section>
}

function Feedback() {
  const error = usePhone((s) => s.error)
  const refusal = usePhone((s) => s.refusal)
  const notice = usePhone((s) => s.notice)
  const hello = usePhone((s) => s.hello)
  const draft = usePhone((s) => s.draft)
  const set = usePhone((s) => s.set)
  return <>
    {(refusal || error) && <div className="refusal-banner" role="alert"><b>{refusal ? 'Plan not sent' : 'Action not completed'}</b><span>{publicText((refusal ?? error).msg, hello, draft)}</span><button className="text-btn" onClick={() => set({ refusal: null, error: null })}>Dismiss</button></div>}
    {notice && <div className="m3-card confirmation" role="status" aria-live="polite"><span>{publicText(notice.msg, hello, draft)}</span><button className="text-btn" onClick={() => set({ notice: null })}>Dismiss</button></div>}
  </>
}

function Shell({ role, initialPage, onJoin }) {
  const [page, setPage] = useState(initialPage)
  const [selected, setSelected] = useState(null)
  const hello = usePhone((s) => s.hello)
  const connection = usePhone((s) => s.connection)
  const error = usePhone((s) => s.error)
  const checking = usePhone((s) => s.checking)
  useLeaseHeartbeat()
  useEffect(() => { if (!checking && error?.code === 'plan_dispatched') forkDispatched() }, [error, checking])
  const meta = hello?.robots?.find((r) => r.id === selected)
  const changePage = (next) => { setSelected(null); setPage(next); usePhone.getState().set({ mode: 'view', selected: null }) }
  return <div className="phone-app">
    <Header title={meta ? (role === 'planner' ? 'Control' : 'Robot report') : page === 'robots' ? 'Pick a robot' : page === 'plan' ? 'Plan' : 'Radio relay'} status={connection}><button className="text-btn" onClick={onJoin}>Join</button></Header>
    <ConnectionBanner status={connection} />
    <nav className="phone-nav" aria-label="Phone screens">{(role === 'planner' ? [['robots', 'Robots'], ['plan', 'Plan']] : [['relay', 'Radio relay'], ['robots', 'Robots']]).map(([key, name]) => <button key={key} aria-current={page === key ? 'page' : undefined} onClick={() => changePage(key)}>{name}</button>)}</nav>
    <Feedback />
    {hello && <p className="incident-name muted small">{hello.floorplan.name}</p>}
    {page === 'robots' && (meta ? <RobotScreen meta={meta} onBack={() => setSelected(null)} /> : <><RobotPicker onPick={setSelected} /><Survivors /><AskCard /></>)}
    {page === 'plan' && <><PlanEditor><MapSection /></PlanEditor><SafetyCard /><AskCard /></>}
    {page === 'relay' && <><RelayPanel /><MapSection /></>}
    <footer className="phone-foot muted small">Only reports received at the command post are shown.</footer>
  </div>
}

export default function PhoneApp() {
  const [role, setRole] = useState(roleFromUrl)
  const [initialPage, setInitialPage] = useState(() => role === 'relay' ? 'relay' : 'robots')
  useEffect(() => (role ? connectPhone(role) : undefined), [role])
  useWakeLock(Boolean(role))
  const pick = (nextRole, page) => {
    const url = new URL(location.href)
    if (nextRole) url.searchParams.set('role', nextRole)
    else url.searchParams.delete('role')
    history.replaceState(null, '', url)
    setInitialPage(page)
    setRole(nextRole)
  }
  return role ? <Shell key={role} role={role} initialPage={initialPage} onJoin={() => pick(null, 'robots')} /> : <Landing onPick={pick} />
}
