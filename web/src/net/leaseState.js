// Pure pieces of the presenter lock (no imports, so Node can test them). See presenter.js.

export const PRESENTER_NAME = 'Presenter'

// The screen's hello carries this socket's private controller token. Take it out before the
// frame is recorded or reaches the store: a credential never goes into a recording, a replay,
// storage or shared state. Returns { msg, token } (token null when there is none).
export function redactHello(msg) {
  if (msg?.t !== 'hello' || !msg.data || !('controller_token' in msg.data)) return { msg, token: null }
  const { controller_token: token, ...data } = msg.data
  return { msg: { ...msg, data }, token: typeof token === 'string' && token ? token : null }
}

// Lease tables arrive by broadcast and as request answers; an older revision must never overwrite
// a newer one. A table from a new connection (hello) always replaces the old one.
export const newerTable = (old, next) => Boolean(next) && (!old || !(next.revision < old.revision))

// The presenter's claim is tracked locally (names are labels, not proof of ownership), and is
// lost as soon as the table shows one of its robots free or held under another name.
export function lostFleet(presenter, table) {
  if (!presenter?.held || !table) return false
  return presenter.robots.some((id) => {
    const entry = table.robots.find((r) => r.robot === id)
    return !entry?.controller || entry.controller.name !== PRESENTER_NAME
  })
}

// Keys and buttons that need the fleet: B (every robot) and U / resume (its target).
export const gated = (leases, presenter) => Boolean(leases?.enabled) && !presenter?.held

// Robots someone other than this presenter holds, for the lock chip and the robot cards.
export const heldByOthers = (leases, presenter) => (leases?.robots ?? []).filter((r) =>
  r.controller && !(presenter?.held && presenter.robots.includes(r.robot)))
