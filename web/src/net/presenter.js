import { useSim } from '../store'
import { REPLAY } from './replay'
import { PRESENTER_NAME } from './leaseState'

// Presenter lock for Aziz's control leases (DZ_CONTROL_LEASES=1, docs/PRESENTER-LEASE-HANDOFF.md).
// The big screen starts locked: B and U need leases on the robots, so they are refused with a
// hint. Unlock takes the whole fleet in one atomic group claim (it fails whole if a phone holds a
// robot), renewed every 5 s; while the presenter holds it, every phone sees the robots locked.
// Lock releases the fleet so phones can take robots (Q&A). Never claims by itself: a reconnect or
// reset needs Unlock again. Flag off: nothing here runs and the screen behaves as before.
//
// The controller token is this socket's private credential: module memory only, never the
// store, a URL, storage, a log or a recording.
export const HEARTBEAT_MS = 5000
let token = null
let heart = null

export function setControllerToken(t) {
  token = t
  if (!t) { stopHeart(); dropFleet(null) }
}
export const controllerToken = () => token

function note(msg) {
  const s = useSim.getState()
  s.set({ toasts: [...s.toasts, { kind: 'note', msg, time: s.time, eid: -Date.now(), at: Date.now() }].slice(-8) })
}

function dropFleet(msg) {
  const s = useSim.getState()
  if (s.presenter.held) s.set({ presenter: { held: false, robots: [], pending: false } })
  if (msg) note(msg)
}

async function leaseCall(path, body) {
  const res = await fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Controller-Token': token }, body: JSON.stringify(body),
  })
  let data = null
  try { data = await res.json() } catch { /* empty */ }
  if (!res.ok) {
    const d = data?.detail
    const error = new Error(typeof d === 'string' ? d : d?.msg ?? `Request failed (${res.status})`)
    error.code = d?.code ?? 'request'
    throw error
  }
  return data
}

function applyTable(table) {
  if (!table) return
  const s = useSim.getState()
  if (!s.leases || !(table.revision < s.leases.revision)) s.set({ leases: table })
}

function stopHeart() { clearInterval(heart); heart = null }
function startHeart() {
  stopHeart()
  heart = setInterval(async () => {
    const s = useSim.getState()
    if (!token || !s.presenter.held) { stopHeart(); return }
    try { applyTable(await leaseCall('/api/leases/group/heartbeat', { robots: s.presenter.robots })) } catch (e) {
      stopHeart()
      dropFleet(e.code === 'lease_required' ? 'Presenter control expired: press Unlock to take the robots again' : `Presenter heartbeat failed: ${e.message}`)
    }
  }, HEARTBEAT_MS)
}

export async function unlock() {
  const s = useSim.getState()
  if (REPLAY || !token || s.presenter.pending || s.presenter.held) return
  const robots = s.robotsMeta.map((r) => r.id)
  if (!robots.length) return
  s.set({ presenter: { ...s.presenter, pending: true } })
  try {
    applyTable(await leaseCall('/api/leases/group/claim', { robots, name: PRESENTER_NAME }))
    useSim.getState().set({ presenter: { held: true, robots, pending: false } })
    startHeart()
  } catch (e) {
    useSim.getState().set({ presenter: { held: false, robots: [], pending: false } })
    note(e.code === 'robot_controlled' ? `Can't unlock: ${e.message}. Ask them to release it on their phone.` : `Unlock failed: ${e.message}`)
  }
}

export async function lock() {
  const s = useSim.getState()
  if (REPLAY || !token || s.presenter.pending || !s.presenter.held) return
  s.set({ presenter: { ...s.presenter, pending: true } })
  stopHeart()
  try {
    applyTable(await leaseCall('/api/leases/group/release', { robots: s.presenter.robots }))
  } catch (e) {
    note(`Release failed: ${e.message}`)
  }
  useSim.getState().set({ presenter: { held: false, robots: [], pending: false } })
}

// B / U / resume: refused with a hint while locked (control leases on, fleet not held).
export function presenterLocked() {
  const s = useSim.getState()
  if (!s.leases?.enabled || s.presenter.held) return false
  note('Presenter controls are locked: press Unlock in the top bar to take the robots first')
  return true
}
