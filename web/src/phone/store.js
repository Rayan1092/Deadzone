import { create } from 'zustand'
import { decodeMap } from '../store'

// Phone state. Phones only ever receive the Command view, never Reality.
export const usePhone = create((set) => ({
  connected: false,
  hello: null,       // { floorplan, grid, robots, plan, client, role, relay_id }
  view: null,        // delivered Command state: { robots, survivors, relays, faults? }
  map: null,         // Command occupancy grid (Uint8Array, row-major, row = y)
  mapVersion: 0,
  draft: null,       // shared search plan being edited (server plan_state, or local edits)
  pending: false,    // local edits not sent yet, so our own plan_state echoes are ignored
  selected: null,    // zone or no-go id open in the editor
  mode: 'view',      // 'view' | 'zone' | 'nogo' (drawing on the map) | 'place' (moving my relay)
  relay: null,       // relay role: my node's relay_state { id, on, pos, queue, neighbors }
  relayPending: null, // power value sent but not yet confirmed by relay_state
  safety: null,      // last safety result
  checking: false,   // waiting for a safety or dispatch answer
  dispatched: [],    // plan IDs this phone dispatched or saw rejected as dispatched
  error: null,       // last error frame { code, msg, at }
  time: 0,
  set,
}))

export function handlePhoneMessage(msg) {
  const { t, data, time } = msg
  const s = usePhone.getState()
  switch (t) {
    case 'hello':
      s.set({ hello: data, draft: data.plan, selected: null, mode: 'view', safety: null, relay: null, relayPending: null,
              checking: false, error: null, time, ...(time < s.time ? { dispatched: [] } : {}) })
      break
    case 'cmd_view': {
      const { map, ...view } = data
      s.set({ view, map: decodeMap(map), mapVersion: s.mapVersion + 1, time })
      break
    }
    case 'plan_state': {
      // Our own edit echoing back while newer local edits wait to be sent: keep local.
      if (s.pending && data?.author === s.hello?.client) break
      const theirs = data?.author !== s.hello?.client
      s.set({ draft: data, ...(theirs ? { safety: null } : {}) })
      break
    }
    case 'relay_state':
      s.set({ relay: data, relayPending: s.relayPending === data.on ? null : s.relayPending })
      break
    case 'safety':
      s.set({ safety: data, checking: false })
      break
    case 'error':
      s.set({ error: { ...data, at: Date.now() }, checking: false, relayPending: null })
      break
    default:
      break
  }
}
