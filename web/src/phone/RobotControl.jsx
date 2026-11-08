import { useEffect, useState } from 'react'
import { fieldUnitName, fmtClock } from '../format'
import { usePhone } from './store'
import { publicText, robotName } from './labels'
import { DARK_S, HEARTBEAT_MS, ackFor, claim, command, heartbeat, holder, isDark, lastFrame, release } from './control'

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
  const label = ACTION_LABEL[mine.action] ?? 'Instruction'
  const state = usePhone.getState()
  const name = robotName(robot, state.hello?.robots)
  const say = (value) => publicText(value, state.hello, state.draft)
  if (mine.status === 'refused') return <div role="status" className="cmd-status bad small">{label} refused: {say(mine.say ?? 'The safety check did not pass.')}</div>
  const ack = ackFor(view, mine.cmd_id)
  if (!ack) return <div role="status" className="cmd-status small">Sent to {name}. Waiting for an answer over the radio.</div>
  return (
    <div className={`cmd-status small ${ack.status === 'refused' ? 'bad' : 'ok'}`}>
      {name} {ack.status === 'refused' ? 'could not follow this instruction' : 'answered'}: {say(ack.say)}{ack.delay_s != null ? ` · answer took ${ack.delay_s}s` : ''}
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
    return <div className="control muted small" onClick={(e) => e.stopPropagation()}>Direct control is unavailable for this session. You can still view reports and send search plans.</div>
  }
  const run = async (fn, message) => {
    const epoch = usePhone.getState().hello?.plan_epoch
    setBusy(true)
    usePhone.getState().set({ notice: null, error: null })
    try {
      await fn()
      if (message && usePhone.getState().hello?.plan_epoch === epoch) usePhone.getState().set({ notice: { msg: message, at: Date.now() } })
    } catch (e) { if (usePhone.getState().hello?.plan_epoch === epoch) fail(e) }
    finally { setBusy(false) }
  }
  const send = (intent) => run(async () => {
    const epoch = usePhone.getState().hello?.plan_epoch
    const res = await command(meta.id, intent, token)
    const s = usePhone.getState()
    if (s.hello?.plan_epoch !== epoch) return
    s.set({ commands: { ...s.commands, [meta.id]: { cmd_id: res.cmd_id, action: intent.action, zone: intent.zone, status: res.status, say: res.say, at: Date.now() } }, notice: res.status === 'refused' ? null : { msg: `Sent to ${meta.name}. Waiting for an answer over the radio.`, at: Date.now() } })
  })
  const off = busy || !connected
  return (
    <div className="control" onClick={(e) => e.stopPropagation()}>
      <div className="control-row">
        {who === 'free' && <span className="muted small">No one is controlling {meta.name}</span>}
        {who === 'other' && <span className="chip bad">Another operator has control</span>}
        {who === 'me' && <span className="chip ok">You have control</span>}
        {who === 'free' && (
          <button className="filled small" disabled={off || !token} onClick={() => run(() => claim(meta.id, fieldUnitName(leases, client), token), `You now control ${meta.name}.`)}>Take control</button>
        )}
        {who === 'me' && <button className="text-btn" disabled={off} onClick={() => run(() => release(meta.id, token), `Control of ${meta.name} released.`)}>Release control</button>}
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
          {!voice && <div className="muted small">Only Resume is available in this session. Other instructions are unavailable.</div>}
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
  if (failed) return <div className="cam-empty">Image unavailable</div>
  return <img src={`/crops/${crop}`} alt="Last thermal image the robot delivered" onError={() => setFailed(true)} />
}

// The robot's camera, built only from what reached the command post. Out of contact it says
// so and how old the last frame is; it never draws a frame that was not delivered.
export function RobotCamera({ meta, report }) {
  const survivors = usePhone((s) => s.view?.survivors ?? NONE)
  const time = usePhone((s) => s.time)
  const f = lastFrame(report, survivors, meta.id)
  // a powered-down robot (Rayan's SHUTDOWN) sent its last bundle on purpose: not a lost signal
  const off = report?.state === 'SHUTDOWN'
  const dark = isDark(report)
  const age = f ? Math.max(0, Math.round(time - f.t)) : null
  return (
    <div className={`robot-cam${dark || off ? ' dark' : ''}`}>
      <div className="cam-view">
        {f?.kind === 'jpeg' && <img style={{ objectFit: 'contain' }} src={`data:image/jpeg;base64,${f.frame.jpeg}`} alt={`${meta.name} last received camera image`} />}
        {f?.kind === 'frame' && report?.pose && <FrameView frame={f.frame} pose={report.pose} />}
        {f?.kind === 'crop' && <CropImage crop={f.crop.crop} />}
        {!f && <div className="cam-empty">No camera image delivered yet</div>}
        {off && (
          <div className="cam-nosignal off">
            <b>Powered down</b>
            <span>Back at the command post. Camera off.</span>
          </div>
        )}
        {dark && !off && (
          <div className="cam-nosignal">
            <b>No signal</b>
            <span>{f ? `Last image ${age} seconds ago` : report ? `Last report ${Math.round(report.stale_s)} seconds ago` : 'No report yet'}</span>
          </div>
        )}
      </div>
      {f?.kind === 'frame' && f.frame.hits?.length > 0 && (
        <ul className="cam-hits">
          {f.frame.hits.map((h, i) => <li key={h.id ?? i} className={h.verdict}>{hitLabel(h)}</li>)}
        </ul>
      )}
      <div className="muted small">
        {f?.kind === 'jpeg' && `Camera image from ${meta.name}, taken T+${fmtClock(f.t)}`}
        {f?.kind === 'frame' && `Thermal image from ${meta.name}, taken T+${fmtClock(f.t)}${f.frame.hits?.length ? '' : ' · nothing warm in view'}`}
        {f?.kind === 'crop' && `Person${f.crop.conf != null ? ` ${Math.round(f.crop.conf * 100)}%` : ''} · last thermal image ${meta.name} delivered, taken T+${fmtClock(f.t)}`}
        {!f && (dark ? `${meta.name} has been out of contact for over ${DARK_S} s` : `Only images that reached the antenna are shown`)}
      </div>
    </div>
  )
}
