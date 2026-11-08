import { useEffect, useState } from 'react'
import { fmtClock } from '../format'
import { usePhone } from './store'
import { DARK_S, HEARTBEAT_MS, ackFor, claim, command, heartbeat, holder, isDark, lastFrame, leaseOf, release } from './control'

const NONE = []
const ACTION_LABEL = { hold: 'Hold', resume: 'Resume', return_home: 'Return home', explore_zone: 'Explore' }

const fail = (e) => usePhone.getState().set({ error: { code: e.code, msg: e.message, at: Date.now() } })

// Keeps every lease this phone holds alive (the server drops it after 15 s without one).
export function useLeaseHeartbeat() {
  useEffect(() => {
    const id = setInterval(() => {
      const s = usePhone.getState()
      if (!s.connected || !s.token || !s.leases?.enabled) return
      for (const r of s.leases.robots) {
        if (r.controller?.client !== s.hello?.client) continue
        // an expired lease shows up as free in the next lease broadcast; no error needed
        heartbeat(r.robot, s.token).catch((e) => { if (e.code !== 'lease_required') fail(e) })
      }
    }, HEARTBEAT_MS)
    return () => clearInterval(id)
  }, [])
}

function CommandStatus({ robot }) {
  const mine = usePhone((s) => s.commands[robot])
  const view = usePhone((s) => s.view)
  if (!mine) return null
  const label = `${ACTION_LABEL[mine.action] ?? mine.action}${mine.zone ? ` ${mine.zone}` : ''}`
  if (mine.status === 'refused') return <div className="cmd-status bad small">{label} refused: {mine.say ?? 'safety check failed'}</div>
  const ack = ackFor(view, mine.cmd_id)
  if (!ack) return <div className="cmd-status small">{label} sent · waiting for {robot}'s answer (it needs radio contact)</div>
  return (
    <div className={`cmd-status small ${ack.status === 'refused' ? 'bad' : 'ok'}`}>
      {robot} {ack.status}: {ack.say}{ack.delay_s != null ? ` · answer took ${ack.delay_s}s` : ''}
    </div>
  )
}

// Take or release control of one robot, and send it a command while you hold it.
export function ControlPanel({ meta }) {
  const leases = usePhone((s) => s.leases)
  const token = usePhone((s) => s.token)
  const client = usePhone((s) => s.hello?.client)
  const role = usePhone((s) => s.hello?.role)
  const voice = usePhone((s) => Boolean(s.hello?.voice?.enabled))
  const rooms = usePhone((s) => s.hello?.floorplan?.rooms ?? NONE)
  const connected = usePhone((s) => s.connected)
  const [busy, setBusy] = useState(false)
  const [zone, setZone] = useState('')
  if (role !== 'planner') return null
  const who = holder(leases, meta.id, client)
  if (who === 'off') {
    return <div className="control muted small" onClick={(e) => e.stopPropagation()}>Direct control is off on this server (DZ_CONTROL_LEASES=1 turns it on)</div>
  }
  const lease = leaseOf(leases, meta.id)
  const run = async (fn) => {
    setBusy(true)
    try { await fn() } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const send = (intent) => run(async () => {
    const res = await command(meta.id, intent, token)
    const s = usePhone.getState()
    s.set({ commands: { ...s.commands, [meta.id]: { cmd_id: res.cmd_id, action: intent.action, zone: intent.zone, status: res.status, say: res.say, at: Date.now() } } })
  })
  const off = busy || !connected
  return (
    <div className="control" onClick={(e) => e.stopPropagation()}>
      <div className="control-row">
        {who === 'free' && <span className="muted small">No one is controlling {meta.name}</span>}
        {who === 'other' && <span className="chip bad">Locked · {lease.controller.name} has control</span>}
        {who === 'me' && <span className="chip ok">You have control</span>}
        {who === 'free' && (
          <button className="filled small" disabled={off || !token} onClick={() => run(() => claim(meta.id, client ?? 'phone', token))}>Take control</button>
        )}
        {who === 'me' && <button className="text-btn" disabled={off} onClick={() => run(() => release(meta.id, token))}>Release</button>}
      </div>
      {who === 'me' && (
        <>
          <div className="control-row cmds">
            {['hold', 'resume', 'return_home'].map((a) => (
              <button key={a} className="chip-btn" disabled={off || (a !== 'resume' && !voice)} onClick={() => send({ action: a })}>{ACTION_LABEL[a]}</button>
            ))}
          </div>
          {rooms.length > 0 && (
            <div className="control-row cmds">
              <select className="room-pick" value={zone} disabled={off || !voice} onChange={(e) => setZone(e.target.value)} aria-label="Room to explore">
                <option value="">Explore a room…</option>
                {rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <button className="chip-btn" disabled={off || !voice || !zone} onClick={() => send({ action: 'explore_zone', zone })}>Send</button>
            </div>
          )}
          {!voice && <div className="muted small">This server only allows Resume; Hold, Return home and Explore need DZ_VOICE=1.</div>}
          <CommandStatus robot={meta.id} />
        </>
      )}
    </div>
  )
}

// Rayan's camera contract (telemetry `camera` under DZ_CAMERA_TELEMETRY=1): what the thermal
// camera saw in that bundle's second and what the onboard detector said about it.
const hitLabel = (h) => {
  const p = h.conf != null ? ` ${Math.round(h.conf * 100)}%` : ''
  return h.verdict === 'person' ? `Person${p}` : h.verdict === 'unsure' ? `AI unsure${p}, moving closer` : `Not a person${p}`
}

// A delivered camera frame drawn from above: the thermal cone and the hot spots the robot
// judged in it, at their reported positions relative to the robot's delivered pose.
function FrameView({ frame, pose }) {
  const [x, y, th] = frame.pose ?? pose
  const R = 5   // m, the thermal camera's range
  const S = 80 / R
  const half = Math.PI / 3   // 120 degree field of view
  const cone = `M50 92 L${50 - Math.sin(half) * 80} ${92 - Math.cos(half) * 80} A80 80 0 0 1 ${50 + Math.sin(half) * 80} ${92 - Math.cos(half) * 80} Z`
  return (
    <svg className="cam-frame" viewBox="0 0 100 100" role="img" aria-label="Delivered thermal camera frame">
      <path d={cone} className="cam-cone" />
      {(frame.hits ?? []).map((h, i) => {
        const dx = h.pos[0] - x
        const dy = h.pos[1] - y
        // robot frame: forward is up on screen
        const fwd = dx * Math.cos(th) + dy * Math.sin(th)
        const left = -dx * Math.sin(th) + dy * Math.cos(th)
        const px = 50 - left * S
        const py = 92 - fwd * S
        return (
          <g key={h.id ?? i} className={`cam-hit ${h.verdict}`}>
            <circle cx={px} cy={py} r="4" />
            <text x={px} y={py - 6} textAnchor="middle">{h.conf != null ? `${Math.round(h.conf * 100)}%` : h.verdict}</text>
          </g>
        )
      })}
      <circle cx="50" cy="92" r="3" className="cam-robot" />
    </svg>
  )
}

function CropImage({ crop }) {
  const [failed, setFailed] = useState(false)
  if (failed) return <div className="cam-empty">thermal</div>
  return <img src={`/crops/${crop}`} alt="Last thermal image the robot delivered" onError={() => setFailed(true)} />
}

// The robot's camera, built only from what reached the command post. Out of contact it says
// so and how old the last frame is; it never draws a frame that was not delivered.
export function RobotCamera({ meta, report }) {
  const survivors = usePhone((s) => s.view?.survivors ?? NONE)
  const time = usePhone((s) => s.time)
  const f = lastFrame(report, survivors, meta.id)
  const dark = isDark(report)
  const age = f ? Math.max(0, Math.round(time - f.t)) : null
  return (
    <div className={`robot-cam${dark ? ' dark' : ''}`}>
      <div className="cam-view">
        {f?.kind === 'frame' && report?.pose && <FrameView frame={f.frame} pose={report.pose} />}
        {f?.kind === 'crop' && <CropImage crop={f.crop.crop} />}
        {!f && <div className="cam-empty">No camera image delivered yet</div>}
        {dark && (
          <div className="cam-nosignal">
            <b>NO SIGNAL</b>
            <span>{f ? `last frame ${age} s ago` : report ? `last report ${Math.round(report.stale_s)} s ago` : 'no report yet'}</span>
          </div>
        )}
      </div>
      {f?.kind === 'frame' && f.frame.hits?.length > 0 && (
        <ul className="cam-hits">
          {f.frame.hits.map((h, i) => <li key={h.id ?? i} className={h.verdict}>{h.id ? `${h.id} · ` : ''}{hitLabel(h)}</li>)}
        </ul>
      )}
      <div className="muted small">
        {f?.kind === 'frame' && `Thermal camera frame from ${meta.id}, taken T+${fmtClock(f.t)}${f.frame.hits?.length ? '' : ' · nothing warm in view'}`}
        {f?.kind === 'crop' && `${f.crop.id} · person${f.crop.conf != null ? ` ${Math.round(f.crop.conf * 100)}%` : ''} · last thermal image ${meta.id} delivered, taken T+${fmtClock(f.t)}`}
        {!f && (dark ? `${meta.id} has been out of contact for over ${DARK_S} s` : `Only images that reached the antenna are shown`)}
      </div>
    </div>
  )
}
