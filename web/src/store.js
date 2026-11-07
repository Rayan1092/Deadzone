import { create } from 'zustand'

// Events worth a toast on the big screen. replan, deadline_miss and deliveries
// fire too often and stay in the sidebar feed or the timeline.
const TOAST_KINDS = new Set(['survivor_found', 'survivor_reported', 'link_lost', 'link_restored',
  'relay_dropped', 'fault', 'rubble_fall', 'safety_reject', 'plan_dispatched', 'plan_applied', 'resumed'])
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
  plan: null,          // shared search plan from plan_state (null when none)
  dispatchedPlans: [], // plan IDs with an accepted dispatch (plan_dispatched events)
  follow: null,        // robot id the cameras follow (keys 1-3), null = overview
  report: null,        // briefing from /api/report: { text, generated_at, source } | { loading } | { error }
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
              ...(reset ? { events: [], toasts: [], tick: null, plan: null, dispatchedPlans: [] } : {}) })
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
      if (ev.kind === 'plan_dispatched') s.set({ dispatchedPlans: [...s.dispatchedPlans, ev.plan_id] })
      s.set({ events: events.slice(0, 40),
              ...(TOAST_KINDS.has(ev.kind) && !repeat ? { toasts: [...s.toasts, { ...ev, at: Date.now() }].slice(-5) } : {}) })
      break
    }
    case 'report':
      s.set({ report: data })
      break
    case 'plan_state':
      s.set({ plan: data })
      break
    case 'control':
      s.set({ running: data.running, speed: data.speed })
      break
    default:
      break
  }
}
