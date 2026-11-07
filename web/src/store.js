import { create } from 'zustand'

// Events worth a toast on the big screen. replan, deadline_miss and deliveries
// fire too often and stay in the sidebar feed or the timeline.
const TOAST_KINDS = new Set(['survivor_found', 'survivor_reported', 'link_lost', 'link_restored',
  'relay_dropped', 'fault', 'rubble_fall', 'safety_reject', 'plan_dispatched', 'plan_applied', 'resumed',
  'rescue_route', 'rescue_route_reported'])
const COLLAPSE_KINDS = new Set(['replan', 'deadline_miss'])
// Radio edges flap constantly and every CMD delivery is an event (several per second);
// keeping them would push the real stories out of the capped feed.
const SKIP_KINDS = new Set(['link_up', 'link_down', 'bundle_delivered'])
let eventId = 0

function readPerf() {
  try { return localStorage.getItem('dz-perf') === '1' } catch { return false }
}

export function setPerf(on) {
  try { localStorage.setItem('dz-perf', on ? '1' : '0') } catch { /* storage blocked: session only */ }
  useSim.getState().set({ perf: on })
}

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
  eyeRobot: null,      // robot whose forward camera is open (V key / card button)
  eyeThermal: false,   // thermal palette in the robot's-eye view
  report: null,        // briefing from /api/report: { text, generated_at, source } | { loading } | { error }
  detector: null,      // { mode: 'model' | 'sim', reason } from hello, null until the server sends it
  detections: [],      // AI detection cards: { eid, side: 'reality' | 'command', verdict, crop, conf, ... }
  routes: {},          // Reality rescue routes from robot `rescue_route` events, by survivor id
  perf: readPerf(),    // P key: lighter rendering for a slow demo laptop (remembered per browser)
  set,
}))

// What the detector judged, as a card. Reality cards come straight from the robot's
// event; the Command card only appears once the survivor report is delivered.
function detectionCard(ev, repeat, tick) {
  const base = { eid: ev.eid, at: Date.now(), robot: ev.robot ?? ev.by }
  if (ev.kind === 'survivor_found' && !repeat) {
    return { ...base, side: 'reality', verdict: 'person', crop: ev.crop, conf: ev.conf, subject: ev.survivor, linked: ev.linked }
  }
  if (ev.kind === 'hotspot_rejected') {
    return { ...base, side: 'reality', verdict: 'rejected', crop: ev.crop, conf: ev.conf, subject: ev.id }
  }
  if (ev.kind === 'survivor_reported') {
    const rec = tick?.command.survivors.find((r) => r.id === ev.survivor)
    return { ...base, side: 'command', verdict: 'person', crop: rec?.crop, conf: rec?.conf, subject: ev.survivor,
             robot: ev.by, delay: ev.delay_s }
  }
  return null
}

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
              detector: data.detector ? { mode: data.detector, reason: data.detector_reason } : null,
              ...(reset ? { events: [], toasts: [], tick: null, plan: null, dispatchedPlans: [], detections: [], routes: {} } : {}) })
      break
    }
    case 'tick': {
      // No server event for relay power changes; derive them from consecutive Reality ticks
      // so "turn your phone relay off" shows up on the big screen.
      const was = Object.fromEntries((s.tick?.reality.relays ?? []).map((r) => [r.id, r.on]))
      const flips = data.reality.relays
        .filter((r) => r.id in was && was[r.id] !== r.on)
        .map((r) => ({ kind: 'relay_power', id: r.id, on: r.on, phone: r.phone, owner: r.owner, time, eid: ++eventId, at: Date.now() }))
      s.set({ tick: data, time, ...(flips.length ? {
        events: [...flips, ...s.events].slice(0, 40), toasts: [...s.toasts, ...flips].slice(-5) } : {}) })
      break
    }
    case 'maps':
      s.set({ maps: { reality: decodeMap(data.reality), command: decodeMap(data.command),
                      version: s.maps.version + 1 } })
      break
    case 'event': {
      if (SKIP_KINDS.has(data.kind)) break
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
      // the robot's own route (Reality knowledge); Command draws only delivered command.routes
      if (ev.kind === 'rescue_route') s.set({ routes: { ...s.routes, [ev.survivor]: ev } })
      const card = detectionCard(ev, repeat, s.tick)
      if (card) s.set({ detections: [...s.detections, card].slice(-6) })
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
