import { create } from 'zustand'

// Events worth a toast on the big screen. replan, deadline_miss and deliveries
// fire too often and stay in the sidebar feed or the timeline.
const TOAST_KINDS = new Set(['survivor_found', 'survivor_reported', 'link_lost', 'link_restored',
  'relay_dropped', 'fault', 'rubble_fall', 'safety_reject'])
const COLLAPSE_KINDS = new Set(['replan', 'deadline_miss'])
let eventId = 0

// One store for everything streamed from the sim. Components select what they need.
export const useSim = create((set) => ({
  connected: false,
  running: false,
  speed: 2,
  floorplan: null,
  grid: null,
  robotsMeta: [],
  time: 0,
  tick: null,          // { reality, command, stats }
  maps: { reality: null, command: null, version: 0 },
  events: [],          // newest first, capped
  toasts: [],          // { id, kind, ... } oldest first, removed by Toasts after a few seconds
  joinOpen: false,     // full screen QR overlay (Q key)
  joinUrl: null,       // phone join URL from /api/join
  showTruth: false,    // T key: faint truth survivors on the Reality pane only
  set,
}))

export function decodeMap(b64) {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

export function handleMessage(msg) {
  const { t, data, time } = msg
  const s = useSim.getState()
  switch (t) {
    case 'hello': {
      // hello also arrives after a rubble drop; only a reset (time going back) clears history
      const reset = time < s.time
      s.set({ floorplan: data.floorplan, grid: data.grid, robotsMeta: data.robots,
              running: data.running, speed: data.speed, time,
              ...(reset ? { events: [], toasts: [], tick: null } : {}) })
      break
    }
    case 'tick':
      s.set({ tick: data, time })
      break
    case 'maps':
      s.set({ maps: { reality: decodeMap(data.reality), command: decodeMap(data.command),
                      version: s.maps.version + 1 } })
      break
    case 'event': {
      // eid, not id: some events (relay_dropped) carry their own id field
      const ev = { ...data, time, eid: ++eventId }
      // every robot that sees a survivor reports it; only the first sighting is news
      const repeat = ev.kind === 'survivor_found' &&
        s.events.some((e) => e.kind === 'survivor_found' && e.survivor === ev.survivor)
      // replans and deadline misses repeat every second; fold a run into one line with a count
      const top = s.events[0]
      const fold = COLLAPSE_KINDS.has(ev.kind) && top && top.kind === ev.kind && top.robot === ev.robot &&
        top.reason === ev.reason && top.task === ev.task
      const events = fold ? [{ ...ev, count: (top.count ?? 1) + 1 }, ...s.events.slice(1)] : [ev, ...s.events]
      s.set({ events: events.slice(0, 40),
              ...(TOAST_KINDS.has(ev.kind) && !repeat ? { toasts: [...s.toasts, { ...ev, at: Date.now() }].slice(-5) } : {}) })
      break
    }
    case 'control':
      s.set({ running: data.running, speed: data.speed })
      break
    default:
      break
  }
}
