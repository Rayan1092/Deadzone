// Labels and formatting shared by the big screen and the phone.

export const STATE_LABEL = {
  DEPLOYING: 'Deploying',
  EXPLORING: 'Exploring',
  LOST_LINK_EXPLORING: 'No link, keeps searching',
  RETURNING_TO_SIGNAL: 'Heading back to radio range',
  RETURNING_HOME: 'Returning home',
  REPLANNING: 'Replanning',
  FAULT: 'Fault',
  DONE: 'Done',
  GOING_TO_POINT: 'Going to point',
  HOLDING: 'Holding',
  WAITING_FOR_LINK: 'No link, waiting', // baseline mode: no Deadzone, the robot stops until it hears CMD
  SHUTDOWN: 'Back at command, powered down', // Rayan's SHUTDOWN after DONE
  WAITING: 'Holding · no-go blocks all routes', // Rayan's P0: a no-go left nothing reachable; it resumes when the no-go changes
}

// A robot's state in plain words. Holding because a no-go left it nothing reachable says so,
// so it reads as obeying the responders, not as a frozen robot.
export const NO_GO_HOLD = 'Holding · no-go blocks all routes'
export function robotStateLabel(r) {
  if (!r) return ''
  if (r.state === 'WAITING' || /no reachable area/i.test(r.plan_state ?? '')) return NO_GO_HOLD
  return STATE_LABEL[r.state] ?? r.state
}

export const FAULT_LABEL = {
  OVERCURRENT: 'Wheel overcurrent',
  STUCK: 'Stuck',
  LOW_BATTERY: 'Low battery',
  TRAPPED: 'Trapped',
  SAFE_STOP: 'Safe stop',
}

const REPLAN_REASON = {
  no_route: 'no route',
  obstacle: 'obstacle ahead',
  overcurrent: 'wheel overcurrent',
  stuck: 'stuck',
  resume: 'resuming after safe stop',
}

export function fmtClock(t) {
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// One line per event, used by the sidebar feed and the toasts.
export function describeEvent(e) {
  switch (e.kind) {
    case 'survivor_found': return `${e.robot} found ${e.survivor}, confirmed by onboard AI${e.looked_closer ? ' after a closer look' : ''}${e.linked ? '' : ' (no link, holding the report)'}`
    case 'hotspot_unsure': return `${e.robot}: ${e.say ?? 'AI unsure, moving closer'} (hot spot ${e.id})`
    case 'survivor_reported': return `${e.survivor} reached the command post (${e.delay_s}s after detection)`
    case 'link_lost': return `${e.robot} lost link, keeps exploring`
    case 'link_restored': return e.dark_s ? `${e.robot} back online after ${Math.round(e.dark_s)}s dark` : `${e.robot} link restored`
    case 'replan': return `${e.robot} replanned${e.reason ? `: ${REPLAN_REASON[e.reason] ?? e.reason}` : ''}`
    case 'fault': return `${e.robot} fault: ${FAULT_LABEL[e.fault] ?? e.fault}`
    case 'relay_dropped': // owner is a robot id, a relay phone's client label, or null
      if (e.beacon_for) return `Radio beacon left with survivor ${e.beacon_for} (${e.id})`
      if (/^R\d+$/.test(e.owner ?? '')) return `${e.owner} left a radio relay (${e.id})`
      return e.owner ? `${unitName(e.owner)} joined as relay ${e.id}` : `Relay ${e.id} placed`
    case 'relay_power': return `${e.phone ? `Field unit relay ${e.id}` : `Relay ${e.id}`} switched ${e.on ? 'on' : 'off'}`
    case 'hotspot_rejected': return `${e.robot}'s detector rejected hot spot ${e.id}: not a person${e.looked_closer ? ', after a closer look' : ''}`
    case 'rescue_route': return e.updated
      ? `Route for rescuers to ${e.survivor} redrawn around new rubble · ${Math.round(e.length_m)} m`
      : `Route for rescuers to ${e.survivor} · ${Math.round(e.length_m)} m, avoids no-go zones${e.beacon ? `, radio beacon ${e.beacon}` : ''}`
    case 'rescue_route_blocked': return `Rescuers' route to ${e.survivor} is blocked, no safe path right now`
    case 'rescue_route_reported': return `${e.updated ? 'Updated route' : 'Route'} to ${e.survivor} reached the command post · ${Math.round(e.length_m)} m`
    case 'deadline_miss': return `${e.robot} missed a ${e.task} deadline`
    case 'rubble_fall': return e.cause === 'collapse' ? `Secondary collapse: rubble across ${e.robot ?? 'a robot'}'s path`
      : e.cause === 'key' ? `Rubble dropped ahead of ${e.robot ?? 'the robot'}` : 'Rubble fell'
    case 'mode_changed': return e.mode === 'baseline'
      ? 'Baseline mode: without Deadzone, robots stop and wait when they lose the link'
      : 'Deadzone on: robots keep exploring in the dark'
    case 'aftershock': return `Aftershock: ceiling collapsed${e.destroyed_relay ? `, relay ${e.destroyed_relay} crushed` : ''}`
    case 'relay_destroyed': return `Relay ${e.id} ${e.cause === 'radio_fail' ? 'lost its radio' : 'destroyed'}${e.lost_bundles ? `, ${e.lost_bundles} bundles lost with it` : ''}`
    case 'radio_fail': return `Relay ${e.relay}'s radio failed${e.lost_bundles ? ` · ${e.lost_bundles} bundles lost` : ''}`
    case 'control_error': return e.code === 'feature_disabled' ? 'Aftershock is off: start the server with DZ_AFTERSHOCK=1' : e.msg
    case 'note': return e.msg
    case 'robot_shutdown': return `${e.robot} back at command, ${(e.found ?? []).length} survivor${(e.found ?? []).length === 1 ? '' : 's'} found, powered down`
    case 'robot_contact': return `${e.a} and ${e.b} bumped into each other and stopped`
    case 'command_received': return `${e.robot} got the ${String(e.cmd).replace(/_/g, ' ')} command: ${e.say}`
    case 'command_ack_reported': return `${e.robot}'s answer reached command: ${e.status} ${String(e.cmd).replace(/_/g, ' ')}${e.delay_s != null ? ` (${e.delay_s}s)` : ''}`
    case 'plan_dispatched': return `Plan ${e.plan_id} dispatched to the robots`
    case 'plan_applied': return `${e.robot} is following ${e.plan_id}${e.zones?.length ? ` (${e.zones.join(', ')})` : ''}`
    case 'resumed': return `${e.robot} resumed after safe stop`
    case 'fault_injected': return `Director: ${e.type} injected on ${e.robot}`
    case 'safety_reject': return `Plan ${e.plan_id} rejected: ${e.violations?.[0]?.msg ?? 'safety check failed'}`
    default: return e.kind
  }
}

// One route per survivor: a newer route (larger t, e.g. replanned after an aftershock)
// replaces the old one on screen instead of being drawn as a second route.
const routeCache = new WeakMap()
export function latestRoutes(list) {
  if (!list?.length) return list ?? []
  if (routeCache.has(list)) return routeCache.get(list)
  const best = new Map()
  for (const r of list) {
    const cur = best.get(r.survivor)
    if (!cur || (r.t ?? 0) >= (cur.t ?? 0)) best.set(r.survivor, r)
  }
  const out = [...best.values()]
  routeCache.set(list, out)
  return out
}

// Every AI image on screen says what it is (Rayan's trust rule).
export const AI_CAPTION = 'Real thermal camera image, Teledyne FLIR dataset: the same input a thermal camera on a rescue robot produces.'

// Command post inset: a robot with no report for this long is drawn dark with a counter.
export const CONTACT_STALE_S = 3

// "12 s", then "1 min 05 s" (sim seconds since the robot's last delivered report)
export function lastContact(age) {
  const s = Math.max(0, Math.floor(age))
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`
}

// A survivor report counts as just delivered (pulse) when it reached the command post within
// the last few sim seconds; one already known when the page loads does not pulse.
export const FRESH_DELIVERY_S = 6
export function freshDelivery(survivor, now) {
  const t = survivor?.reported_t
  return typeof t === 'number' && now - t <= FRESH_DELIVERY_S
}

// Rayan's rubble causes (DZ_SMART_RUBBLE=1): the scripted secondary collapse (no key, sim 162.5 on
// collapse_01) gets a big alert banner; an R press a smaller one naming the robot it landed in
// front of. Other rubble (an aftershock's own) has no cause and its own banner. `robot` is the
// server's (the robot the drop was aimed at), else the robot the screen aimed it at.
export function rubbleBanner(ev, aimed, scenario = false) {
  if (ev?.kind !== 'rubble_fall') return null
  const robot = ev.robot ?? aimed ?? null
  if (ev.cause === 'collapse') {
    return { title: 'SECONDARY COLLAPSE', sub: `${SCENARIO_TAG} · ${robot ? `${robot} blocked` : 'a robot is blocked'}`, tone: 'alert', size: 'major' }
  }
  // the floor plan's timeline dropping rubble (no cause): named as the scenario's doing
  if (!ev.cause) return scenario ? { title: 'RUBBLE', sub: `${SCENARIO_TAG} · part of the ceiling came down`, tone: 'warn', size: 'minor', ms: 3500 } : null
  return { title: 'RUBBLE', sub: robot ? `Dropped ahead of ${robot}` : 'Dropped ahead of the robot', tone: 'warn', size: 'minor', ms: 3500 }
}

export function polyCenter(poly) {
  if (!poly?.length) return null
  return [poly.reduce((t, p) => t + p[0], 0) / poly.length, poly.reduce((t, p) => t + p[1], 0) / poly.length]
}

// Field units: phones show as "Field unit N". A phone claims robots under the lowest number no
// other holder in the shared lease table uses (so every screen shows the same name); a raw client
// label (phone-4, phone-k3f2) is shown the same way wherever it appears.
export function unitName(label) {
  if (typeof label !== 'string' || !label) return 'A field unit'
  const m = label.match(/^phone-(.+)$/)
  if (!m) return label
  return `Field unit ${/^\d+$/.test(m[1]) ? m[1] : m[1].toUpperCase()}`
}
export function fieldUnitName(leases, client) {
  const held = (leases?.robots ?? []).filter((r) => r.controller)
  const mine = held.find((r) => r.controller.client === client && /^Field unit \d+$/.test(r.controller.name))
  if (mine) return mine.controller.name
  const used = new Set(held.filter((r) => r.controller.client !== client).map((r) => r.controller.name))
  let n = 1
  while (used.has(`Field unit ${n}`)) n++
  return `Field unit ${n}`
}

// Scenario events: what the building's scenario makes happen on its own, not a key on this console.
// Rayan's floor plan `events` (collapse, aftershock, radio_fail; PLAN.md "Scenario events") fire at
// their `t`: an event whose type and sim time match a scheduled entry is one (an A-key aftershock
// looks the same on the wire, so the schedule decides). The secondary collapse and a radio failure
// always are (no key makes either). With the opt-in `timeline` player on, an aftershock or rubble
// this screen did not just ask for is one too; so is anything the server marks.
const SCENARIO_TYPE = (ev) => (ev.kind === 'rubble_fall' ? (ev.cause === 'collapse' ? 'collapse' : ev.cause ? null : 'aftershock')
  : ev.kind === 'aftershock' ? 'aftershock'
  : ev.kind === 'radio_fail' || (ev.kind === 'relay_destroyed' && ev.cause === 'radio_fail') ? 'radio_fail'
  : ev.kind === 'relay_destroyed' ? 'aftershock' : null)
export function scheduledScenario(ev, time, events) {
  const type = ev && SCENARIO_TYPE(ev)
  if (!type || !Array.isArray(events)) return null
  return events.find((e) => e?.type === type && Math.abs((e.t ?? -1e9) - time) <= 0.6) ?? null
}
export function isScenarioEvent(ev, { timeline = false, pressedRecently = false, scheduled = null } = {}) {
  if (!ev) return false
  if (scheduled || ev.scenario === true || ev.source === 'timeline' || ev.source === 'scenario') return true
  if (ev.kind === 'radio_fail' || (ev.kind === 'relay_destroyed' && ev.cause === 'radio_fail')) return true
  if (ev.kind === 'rubble_fall' && ev.cause === 'collapse') return true
  if (ev.kind === 'rubble_fall' && ev.cause === 'key') return false
  return timeline && !pressedRecently && (ev.kind === 'aftershock' || ev.kind === 'rubble_fall' || ev.kind === 'radio_fail')
}
export const SCENARIO_TAG = 'Scenario event'
export function radioFailBanner(ev, label) {
  const lost = ev.lost_bundles ? ` · ${ev.lost_bundles} bundle${ev.lost_bundles === 1 ? '' : 's'} lost` : ''
  return { title: 'RADIO FAILURE', sub: `${SCENARIO_TAG} · ${label || `relay ${ev.relay} lost its radio`}${lost}`, tone: 'alert' }
}

// ------------------------------------------------------------------ plan captions
// "Zone 3" for a zone id Z3, else "Zone ZNE"
export function zoneLabel(id) {
  if (!id) return null
  const m = /^Z(\d+)$/i.exec(id)
  return `Zone ${m ? m[1] : id}`
}

// What a robot card and the robot's on-scene caption say about the search plan (Reality: the
// robot's own telemetry). Holding (a no-go left nothing reachable) comes first; then a dispatched
// plan that gives this robot a zone but has not reached it ("plan pending · robot dark" while it
// has no link); then the zone it is searching ("Scout 2 → Zone 3"). null when there is nothing to say.
// `dispatched`: plan ids with an accepted dispatch; `plan`: the shared plan (its zones name robots).
export function planCaption(r, { dispatched = [], plan = null } = {}) {
  if (!r) return null
  if (r.state === 'WAITING' || /no reachable area/i.test(r.plan_state ?? '')) return { kind: 'holding', text: NO_GO_HOLD }
  const latest = dispatched.at(-1)
  const assigned = latest && plan?.plan_id === latest && (plan.zones ?? []).some((z) => z.robot === r.id)
  if (assigned && r.plan_id !== latest) {
    return { kind: 'pending', text: r.link?.up === false ? 'plan pending · robot dark' : 'plan pending' }
  }
  if (r.plan_id && r.zone) return { kind: 'zone', text: `${r.name ?? r.id} → ${zoneLabel(r.zone)}` }
  return null
}

// ------------------------------------------------------------------ robot identity label
// The floating label over a robot in Reality: "R1 · LINK −76 dBm" while it has a radio route,
// "R1 · NO LINK · 12 s" once it is dark (seconds since Command last heard from it, Command's own
// record). `dark` turns the tag red on grey. "R1 · POWERED DOWN" after the mission.
export function robotTag(r, cmd, time) {
  if (!r) return { text: '', dark: false }
  if (r.state === 'SHUTDOWN' || r.lights === false) return { text: `${r.id} · POWERED DOWN`, dark: false }
  if (r.link?.up) {
    const dbm = Number.isFinite(r.link.rssi) ? ` ${String(Math.round(r.link.rssi)).replace('-', '−')} dBm` : ''
    return { text: `${r.id} · LINK${dbm}`, dark: false }
  }
  const age = cmd?.last_seen != null ? ` · ${Math.max(0, Math.floor(time - cmd.last_seen))} s` : ''
  return { text: `${r.id} · NO LINK${age}`, dark: true }
}
