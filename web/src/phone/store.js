import { create } from 'zustand'
import { decodeMap } from '../store'

// Phone state. Phones only ever receive the Command view, never Reality.
export const usePhone = create((set) => ({
  connected: false,
  hello: null,       // { floorplan, grid, robots, plan, client, role, relay_id }
  view: null,        // delivered Command state: { robots, survivors, relays }
  map: null,         // Command occupancy grid (Uint8Array, row-major, row = y)
  mapVersion: 0,
  plan: null,        // shared draft from plan_state
  safety: null,      // last safety result
  error: null,       // last error frame { code, msg }
  time: 0,
  set,
}))

export function handlePhoneMessage(msg) {
  const { t, data, time } = msg
  const s = usePhone.getState()
  switch (t) {
    case 'hello':
      s.set({ hello: data, plan: data.plan, safety: null, error: null, time })
      break
    case 'cmd_view': {
      const { map, ...view } = data
      s.set({ view, map: decodeMap(map), mapVersion: s.mapVersion + 1, time })
      break
    }
    case 'plan_state':
      s.set({ plan: data })
      break
    case 'safety':
      s.set({ safety: data })
      break
    case 'error':
      s.set({ error: { ...data, at: Date.now() } })
      break
    default:
      break
  }
}
