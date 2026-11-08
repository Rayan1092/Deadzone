import { create } from 'zustand'

// Events worth a toast on the big screen. replan, deadline_miss and deliveries
// fire too often and stay in the sidebar feed or the timeline.
const TOAST_KINDS = new Set(['survivor_found', 'survivor_reported', 'link_lost', 'link_restored',
  'relay_dropped', 'fault', 'rubble_fall', 'safety_reject', 'plan_dispatched', 'plan_applied', 'resumed',
  'rescue_route', 'rescue_route_reported', 'aftershock', 'relay_destroyed', 'mode_changed', 'rescue_route_blocked'])
const COLLAPSE_KINDS = new Set(['replan', 'deadline_miss'])
// Deliveries worth an antenna pulse; telemetry and map patches arrive several times a second.
const BIG_DELIVERIES = new Set(['survivor', 'rescue_route', 'fault'])
// Radio edges flap constantly and every CMD delivery is an event (several per second);
// keeping them would push the real stories out of the capped feed.
const SKIP_KINDS = new Set(['link_up', 'link_down', 'bundle_delivered'])
let eventId = 0
let planSavedAt = 0
const PRELOAD_WINDOW_MS = 1000
export const FOCUS_HOLD_MS = 12000 // how long the robot camera stays on a judged hot spot

function readPerf() {
  try { return localStorage.getItem('dz-perf') === '1' } catch { return false }
}

function readView() {
  try { return localStorage.getItem('dz-view') === 'gap' ? 'gap' : 'split' } catch { return 'split' }
}

// 'split' = Reality and Command side by side; 'gap' = one Reality view with what
// Command doesn't know yet drawn on it (Version 2 plan). M toggles.
export function setView(view) {
  try { localStorage.setItem('dz-view', view) } catch { /* storage blocked: session only */ }
  useSim.getState().set({ view })
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
  helpOpen: false,     // key list overlay (? key)
  joinUrl: null,       // phone join URL from /api/join
  showTruth: false,    // T key: faint truth survivors on the Reality pane only
  plan: null,          // shared search plan from plan_state (null when none)
  dispatchedPlans: [], // plan IDs with an accepted dispatch (plan_dispatched events)
  follow: null,        // robot id the cameras follow (keys 1-3), null = overview
  eyeRobot: null,      // robot whose forward camera is open (V key / card button)
  eyeThermal: false,   // thermal palette in the robot's-eye view
  labOpen: false,      // L key: AI Lab overlay
  eyeFocus: null,      // the hot spot the onboard classifier just judged: { kind, subject, robot, pos, conf, linked, born }
  mode: null,          // 'deadzone' | 'baseline' | 'mixed' from hello/control (Rayan's baseline mode)
  aftershock: null,    // { at, born } of the latest aftershock, for the shake and dust
  report: null,        // briefing from /api/report: { text, generated_at, source } | { loading } | { error }
  detector: null,      // { mode: 'model' | 'sim', reason } from hello, null until the server sends it
  detections: [],      // AI detection cards: { eid, side: 'reality' | 'command', verdict, crop, conf, ... }
  routes: {},          // Reality rescue routes from robot `rescue_route` events, by survivor id
  bigDeliveries: 0,    // count of survivor / route / fault reports delivered to CMD (antenna pulse)
  perf: readPerf(),    // P key: lighter rendering for a slow demo laptop (remembered per browser)
  view: readView(),    // M key: 'split' (two panes) or 'gap' (one view + Command gap), remembered
  recorder: null,      // ?record: { frames, ms, bytes } of the captured stream
  replay: null,        // ?replay: { loaded, playing, rate, pos, dur, ended }
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
              running: data.running, speed: data.speed, mode: data.mode ?? null, time,
              detector: data.detector ? { mode: data.detector, reason: data.detector_reason } : null,
              ...(reset ? { events: [], toasts: [], tick: null, plan: null, dispatchedPlans: [], detections: [], routes: {}, aftershock: null, eyeFocus: null } : {}) })
      break
    }
    case 'tick': {
      // No server event for relay power changes; derive them from consecutive Reality ticks
      // so "turn your phone relay off" shows up on the big screen.
      const was = Object.fromEntries((s.tick?.reality.relays ?? []).map((r) => [r.id, r.on]))
      const flips = data.reality.relays
        // a relay crushed by an aftershock has its own event; don't also call it "switched off"
        .filter((r) => r.id in was && was[r.id] !== r.on && !r.destroyed)
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
      if (data.kind === 'bundle_delivered' && BIG_DELIVERIES.has(data.bundle_kind)) {
        s.set({ bigDeliveries: s.bigDeliveries + 1 })
      }
      if (SKIP_KINDS.has(data.kind)) break
      // POST /api/plan saves and checks in one request, so its rejection lands right after
      // plan_state. That is the demo's laptop preload: keep it off screen so the judges'
      // own "Run safety check" is the first rejection anyone sees.
      if (data.kind === 'safety_reject' && Date.now() - planSavedAt < PRELOAD_WINDOW_MS) break
      // every robot reports the B switch; one line for the whole fleet
      if (data.kind === 'mode_changed' && s.events[0]?.kind === 'mode_changed' && s.events[0].mode === data.mode &&
          s.events[0].time === time) break
      // eid, not id: some events (relay_dropped) carry their own id field
      const ev = { ...data, time, eid: ++eventId }
      // a second route for the same survivor is a replan, not a new rescue
      if ((ev.kind === 'rescue_route' || ev.kind === 'rescue_route_reported') &&
          s.events.some((e) => e.kind === ev.kind && e.survivor === ev.survivor)) ev.updated = true
      // every robot that sees a survivor reports it; only the first sighting is news
      const repeat = ev.kind === 'survivor_found' &&
        s.events.some((e) => e.kind === 'survivor_found' && e.survivor === ev.survivor)
      // replans and deadline misses repeat every second; fold a run into one line with a count
      const top = s.events[0]
      const fold = COLLAPSE_KINDS.has(ev.kind) && top && top.kind === ev.kind && top.robot === ev.robot &&
        top.reason === ev.reason && top.task === ev.task
      const events = fold ? [{ ...ev, count: (top.count ?? 1) + 1 }, ...s.events.slice(1)] : [ev, ...s.events]
      if (ev.kind === 'plan_dispatched') s.set({ dispatchedPlans: [...s.dispatchedPlans, ev.plan_id] })
      // the 3D view shakes and throws up a dust cloud where the ceiling came down (Reality only)
      if (ev.kind === 'aftershock') s.set({ aftershock: { at: ev.at, born: performance.now() } })
      // the robot's own route (Reality knowledge); Command draws only delivered command.routes
      if (ev.kind === 'rescue_route') {
        // a newer route for the same survivor replaces the old one; an older one is ignored
        const old = s.routes[ev.survivor]
        if (!old || (ev.t ?? 0) >= (old.t ?? 0)) s.set({ routes: { ...s.routes, [ev.survivor]: ev } })
      }
      // AI showcase: open that robot's camera on the hot spot its classifier just judged
      // (first sighting of each survivor, first rejection of each decoy). A showcase that
      // is still playing is not interrupted.
      const firstReject = ev.kind === 'hotspot_rejected' &&
        !s.events.some((e) => e.kind === 'hotspot_rejected' && e.id === ev.id)
      if ((ev.kind === 'survivor_found' && !repeat) || firstReject) {
        const busy = s.eyeFocus && performance.now() - s.eyeFocus.born < FOCUS_HOLD_MS
        if (!busy) {
          s.set({ eyeRobot: ev.robot, eyeFocus: { kind: ev.kind === 'survivor_found' ? 'person' : 'decoy',
            subject: ev.survivor ?? ev.id, robot: ev.robot, pos: ev.pos, conf: ev.conf, linked: ev.linked,
            born: performance.now() } })
        }
      }
      const card = detectionCard(ev, repeat, s.tick)
      if (card) s.set({ detections: [...s.detections, card].slice(-6) })
      s.set({ events: events.slice(0, 40),
              ...(TOAST_KINDS.has(ev.kind) && !repeat ? { toasts: [...s.toasts, { ...ev, at: Date.now() }].slice(-8) } : {}) })
      break
    }
    case 'report':
      s.set({ report: data })
      break
    case 'plan_state':
      planSavedAt = Date.now()
      s.set({ plan: data })
      break
    case 'control':
      s.set({ running: data.running, speed: data.speed, ...(data.mode ? { mode: data.mode } : {}) })
      break
    case 'error': {
      // a director key the server refused (e.g. aftershock without DZ_AFTERSHOCK=1)
      const ev = { kind: 'control_error', code: data.code, msg: data.msg, time: s.time, eid: ++eventId, at: Date.now() }
      s.set({ toasts: [...s.toasts, ev].slice(-8) })
      break
    }
    default:
      break
  }
}
