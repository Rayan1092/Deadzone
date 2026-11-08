import { create } from 'zustand'
import { decodeMap } from '../store'
import { phoneHelloState } from './sync'
import { retainPhoneFrames } from './control'

// Phone state. Phones only ever receive the Command view, never Reality.
export const usePhone = create((set) => ({
  connected: false,
  hello: null,       // { floorplan, grid, robots, plan, client, role, relay_id }
  view: null,        // delivered Command state: { robots, survivors, relays, faults? }
  map: null,         // Command occupancy grid (Uint8Array, row-major, row = y)
  mapVersion: 0,
  draft: null,       // shared search plan being edited (server plan_state, or local edits)
  pending: false,    // edits waiting for a save acknowledgment; keep them across reconnects
  selected: null,    // zone or no-go id open in the editor
  mode: 'view',      // 'view' | 'zone' | 'nogo' (drawing on the map) | 'place' (moving my relay)
  relay: null,       // relay role: my node's relay_state { id, on, pos, queue, neighbors }
  relayPending: null, // power value sent but not yet confirmed by relay_state
  safety: null,      // last safety result
  checking: false,   // waiting for a safety or dispatch answer
  dispatched: [],    // plan IDs this phone dispatched or saw rejected as dispatched
  error: null,       // last error frame { code, msg, at }
  leases: null,      // server lease table { enabled, ttl_s, robots: [{ robot, controller, expires_at }] }
  token: null,       // this phone's controller token (planner role, leases on); new on every connect
  commands: {},      // robot -> my latest command { cmd_id, action, zone, status, say, at }
  refusal: null,     // the server refused a plan: { msg, code, at }, a red banner until tapped
  time: 0,
  set,
}))

export function handlePhoneMessage(msg) {
  const { t, data, time } = msg
  const s = usePhone.getState()
  switch (t) {
    case 'hello':
      // a new connection is a new controller: any lease and command from before are gone
      s.set({ ...phoneHelloState(s, data, time), leases: data.leases ?? null, token: data.controller_token ?? null, commands: {} })
      break
    case 'leases':
      s.set({ leases: data })
      break
    case 'cmd_view': {
      const { map, ...view } = data
      s.set({ view: retainPhoneFrames(s.view, view, Boolean(s.hello?.phone_frames), time),
              map: decodeMap(map), mapVersion: s.mapVersion + 1, time })
      break
    }
    case 'plan_state': {
      // Keep the local edit until its save is acknowledged (whole-draft last write wins).
      if (s.pending) break
      const theirs = data?.author !== s.hello?.client
      s.set({ draft: data, ...(theirs ? { safety: null } : {}) })
      break
    }
    case 'relay_state':
      s.set({ relay: data, relayPending: s.relayPending === data.on ? null : s.relayPending })
      break
    case 'safety':
      // Our check uses its HTTP response so another phone cannot answer it.
      break
    case 'event':
      if (data.kind === 'plan_dispatched') {
        s.set({ dispatched: [...new Set([...s.dispatched, data.plan_id])] })
      }
      break
    case 'error':
      s.set({ error: { ...data, at: Date.now() }, checking: false, relayPending: null })
      break
    default:
      break
  }
}
