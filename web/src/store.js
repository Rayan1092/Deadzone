import { create } from 'zustand'
import { useRef } from 'react'
import { alarm, chime, confirm, ping, rumble } from './audio'
import { lostFleet, newerTable } from './net/leaseState'
import { pushTraffic, resetTraffic } from './net/traffic'

// Events worth a toast on the big screen. replan, deadline_miss and deliveries
// fire too often and stay in the sidebar feed or the timeline.
const TOAST_KINDS = new Set(['survivor_found', 'survivor_reported', 'link_lost', 'link_restored',
  'relay_dropped', 'fault', 'rubble_fall', 'safety_reject', 'plan_dispatched', 'plan_applied', 'resumed',
  'rescue_route', 'rescue_route_reported', 'aftershock', 'relay_destroyed', 'mode_changed', 'rescue_route_blocked',
  'robot_shutdown', 'robot_contact', 'command_ack_reported'])
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

// K key: night operations lighting (dark interior, headlights, emergency lights). Off by
// default until a dry run passes; remembered per browser.
function readNight() {
  try { return localStorage.getItem('dz-night') !== '0' } catch { return true }
}
export function setNight(on) {
  try { localStorage.setItem('dz-night', on ? '1' : '0') } catch { /* storage blocked: session only */ }
  useSim.getState().set({ night: on })
}

// E key: 'judge' (the default: the map, robots, survivors and the Rescue Status strip; the
// sidebar, scheduler, legends and top-bar controls appear on hover) or 'full' (everything
// always on). Remembered per browser.
function readLayout() {
  try { return localStorage.getItem('dz-layout') === 'full' ? 'full' : 'judge' } catch { return 'judge' }
}
export function setLayout(layout) {
  try { localStorage.setItem('dz-layout', layout) } catch { /* storage blocked: session only */ }
  useSim.getState().set({ layout })
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
  maps: { reality: null, command: null, version: 0, commandVersion: 0 }, // commandVersion: only when Command's map changed
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
  introOpen: false,    // first-glance explainer (once per session, or from the ? overlay)
  labOpen: false,      // L key: AI Lab overlay
  judgeOpen: false,    // J: held-out thermal judge challenge, after the close
  hoodOpen: false,     // I: actual simulator counters, after the close
  eyeFocus: null,      // the hot spot the onboard classifier just judged: { kind, subject, robot, pos, conf, linked, born }
  mode: null,          // 'deadzone' | 'baseline' | 'mixed' from hello/control (Rayan's baseline mode)
  aftershock: null,    // { at, born, rubble } of the latest aftershock, for the shake, slabs and dust
  banner: null,        // { title, sub, tone, at }: AFTERSHOCK / NEW SCENARIO over the main view
  traffic: false,      // network traffic events seen (DZ_NETWORK_TRAFFIC): packets and live line widths
  leases: null,        // public control-lease table (DZ_CONTROL_LEASES=1): { enabled, revision, robots: [{ robot, controller }] }
  presenter: { held: false, robots: [], pending: false }, // this screen's own fleet claim (net/presenter.js)
  report: null,        // briefing from /api/report: { text, generated_at, source } | { loading } | { error }
  detector: null,      // { mode: 'model' | 'sim', reason } from hello, null until the server sends it
  detections: [],      // AI detection cards: { eid, side: 'reality' | 'command', verdict, crop, conf, ... }
  routes: {},          // Reality rescue routes from robot `rescue_route` events, by survivor id
  bigDeliveries: 0,    // count of survivor / route / fault reports delivered to CMD (antenna pulse)
  director: false,     // D key: auto-director camera
  shot: null,          // { caption, at } of the director's current shot
  night: readNight(),  // night operations lighting is the default scene; K switches to day
  perf: readPerf(),    // P key: lighter rendering for a slow demo laptop (remembered per browser)
  view: readView(),    // M key: 'split' (two panes) or 'gap' (one view + Command gap), remembered
  layout: readLayout(), // E key: 'judge' (map first, chrome on hover) or 'full'
  recorder: null,      // ?record: { frames, ms, bytes } of the captured stream
  replay: null,        // ?replay: { loaded, playing, rate, pos, dur, ended }
  set,
}))

// What the detector judged, as a card. Reality cards come straight from the robot's
// event; the Command card only appears once the survivor report is delivered.
// A doubtful score from afar (Rayan's look-closer, 0.35 to 0.75) holds its card while the robot
// drives in (up to 20 s); the decision card then replaces it, showing far -> close.
const UNSURE_CARD_MS = 22000
function detectionCard(ev, repeat, tick) {
  const base = { eid: ev.eid, at: Date.now(), robot: ev.robot ?? ev.by }
  const closer = { confFar: ev.conf_far, closer: ev.looked_closer }
  if (ev.kind === 'hotspot_unsure') {
    return { ...base, side: 'reality', verdict: 'unsure', crop: ev.crop, conf: ev.conf, subject: ev.id, say: ev.say, ttl: UNSURE_CARD_MS }
  }
  if (ev.kind === 'survivor_found' && !repeat) {
    return { ...base, side: 'reality', verdict: 'person', crop: ev.crop, conf: ev.conf, subject: ev.survivor, linked: ev.linked, ...closer }
  }
  if (ev.kind === 'hotspot_rejected') {
    return { ...base, side: 'reality', verdict: 'rejected', crop: ev.crop, conf: ev.conf, subject: ev.id, ...closer }
  }
  if (ev.kind === 'survivor_reported') {
    const rec = tick?.command.survivors.find((r) => r.id === ev.survivor)
    return { ...base, side: 'command', verdict: 'person', crop: rec?.crop, conf: rec?.conf, subject: ev.survivor,
             robot: ev.by, delay: ev.delay_s }
  }
  return null
}

// A store value that keeps its identity while its content is unchanged: every tick brings new
// arrays, and a new array in a canvas component re-renders it, which redraws the whole canvas.
// The component re-renders only when keyOf(value) changes (JSON by default; keep values small).
export function useStable(selector, keyOf = JSON.stringify) {
  const memo = useRef({ key: undefined, value: undefined })
  const key = useSim((s) => keyOf(selector(s)))
  if (memo.current.key !== key) memo.current = { key, value: selector(useSim.getState()) }
  return memo.current.value
}

export function decodeMap(b64) {
  if (b64 instanceof Uint8Array) return b64
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
      // a different building, or the same building with the survivors moved (key N variants):
      // say so, so nobody thinks the run is scripted
      const prev = s.floorplan
      const changed = prev && data.floorplan && (prev.id !== data.floorplan.id || prev.name !== data.floorplan.name ||
        (reset && JSON.stringify(prev.survivors?.map((x) => x.pos)) !== JSON.stringify(data.floorplan.survivors?.map((x) => x.pos))))
      if (changed) s.set({ banner: { title: 'NEW SCENARIO', tone: 'info', at: Date.now(),
        sub: prev.id !== data.floorplan.id || prev.name !== data.floorplan.name ? data.floorplan.name : `${data.floorplan.name} · survivors and decoys shuffled, new seed` } })
      s.set({ floorplan: data.floorplan, grid: data.grid, robotsMeta: data.robots,
              running: data.running, speed: data.speed, mode: data.mode ?? null, time,
              detector: data.detector ? { mode: data.detector, reason: data.detector_reason } : null,
              ...(data.leases ? { leases: data.leases } : {}),
              // a reset frees every lease on the server: the presenter has to Unlock again
              ...(reset ? (resetTraffic(), {}) : {}),
              ...(reset ? { events: [], toasts: [], tick: null, plan: null, dispatchedPlans: [], detections: [], routes: {}, aftershock: null, eyeFocus: null,
                            presenter: { held: false, robots: [], pending: false } } : {}) })
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
    case 'maps': {
      // the Command pane redraws only when its own map changed (maps arrive several times a second)
      const command = decodeMap(data.command)
      const old = s.maps.command
      const same = old && old.length === command.length && old.every((v, i) => v === command[i])
      s.set({ maps: { reality: decodeMap(data.reality), command, version: s.maps.version + 1,
                      commandVersion: same ? s.maps.commandVersion : s.maps.commandVersion + 1 } })
      break
    }
    case 'event': {
      if (data.kind === 'bundle_delivered' && BIG_DELIVERIES.has(data.bundle_kind)) {
        s.set({ bigDeliveries: s.bigDeliveries + 1 })
      }
      // network traffic (DZ_NETWORK_TRAFFIC): several a second, drawn as packets, never in the feed
      if (data.kind === 'bundle_hop' || data.kind === 'bundle_held') {
        pushTraffic(data)
        if (!s.traffic) s.set({ traffic: true })
        break
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
      if (ev.kind === 'aftershock') {
        s.set({ aftershock: { at: ev.at, born: performance.now(), rubble: ev.rubble ?? [] },
          banner: { title: 'AFTERSHOCK', tone: 'alert', at: Date.now(),
            sub: ev.destroyed_relay ? `Part of the building came down · relay ${ev.destroyed_relay} crushed · robots rerouting` : 'Part of the building came down · robots rerouting' } })
        rumble(5) // only audible after a user gesture (the A key counts)
      }
      // sound cues (X turns them off): news only, a repeat sighting stays quiet
      if (ev.kind === 'survivor_found' && !repeat) ping()
      if (ev.kind === 'survivor_reported') confirm()
      if (ev.kind === 'fault') alarm()
      if (ev.kind === 'link_restored') chime()
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
      // a doubtful hot spot is shown too (the robot drives closer); its decision then takes over
      // the camera even while the unsure shot is still playing
      // (every robot re-checks a doubtful hot spot itself: only the first doubt is shown, and
      // the decision of the robot being shown always completes its shot)
      const subject = ev.survivor ?? ev.id
      const unsure = ev.kind === 'hotspot_unsure' && !s.events.some((e) => e.kind === 'hotspot_unsure' && e.id === ev.id)
      const follows = (ev.kind === 'survivor_found' || ev.kind === 'hotspot_rejected') &&
        s.eyeFocus?.kind === 'unsure' && s.eyeFocus.subject === subject && s.eyeFocus.robot === ev.robot
      if ((ev.kind === 'survivor_found' && !repeat) || firstReject || unsure || follows) {
        const busy = s.eyeFocus && performance.now() - s.eyeFocus.born < FOCUS_HOLD_MS && !follows
        if (!busy) {
          s.set({ eyeRobot: ev.robot, eyeFocus: { kind: unsure ? 'unsure' : ev.kind === 'survivor_found' ? 'person' : 'decoy',
            subject, robot: ev.robot, pos: ev.pos, conf: ev.conf, linked: ev.linked,
            confFar: ev.conf_far, closer: ev.looked_closer, born: performance.now() } })
        }
      }
      const card = detectionCard(ev, repeat, s.tick)
      if (card) {
        const kept = card.verdict === 'unsure' ? s.detections
          : s.detections.filter((c) => !(c.verdict === 'unsure' && c.subject === card.subject))
        s.set({ detections: [...kept, card].slice(-6) })
      }
      s.set({ events: events.slice(0, 40),
              ...(TOAST_KINDS.has(ev.kind) && !repeat ? { toasts: [...s.toasts, { ...ev, at: Date.now() }].slice(-8) } : {}) })
      break
    }
    case 'leases': {
      // newest revision wins; the presenter's claim ends when one of its robots shows free or taken
      if (!newerTable(s.leases, data)) break
      const lost = lostFleet(s.presenter, data)
      s.set({ leases: data, ...(lost ? { presenter: { held: false, robots: [], pending: false },
        toasts: [...s.toasts, { kind: 'note', msg: 'Presenter control ended: press Unlock to take the robots again', time: s.time, eid: -Date.now(), at: Date.now() }].slice(-8) } : {}) })
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

// dev aid: inspect or poke the store from the console (window.__dz.getState())
if (typeof window !== 'undefined') window.__dz = useSim
