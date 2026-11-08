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
  WAITING: 'Holding: no-go blocks all routes', // Rayan's P0: a no-go left nothing reachable; it resumes when the no-go changes
}

// A robot's state in judge words. Holding because a no-go left it nothing reachable says so,
// so it reads as obeying the responders, not as a frozen robot.
export const NO_GO_HOLD = 'Holding: no-go blocks all routes'
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
      return e.owner ? `Phone ${e.owner} joined as relay ${e.id}` : `Relay ${e.id} placed`
    case 'relay_power': return `${e.phone ? `Phone relay ${e.id}` : `Relay ${e.id}`} switched ${e.on ? 'on' : 'off'}`
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
    case 'relay_destroyed': return `Relay ${e.id} destroyed${e.lost_bundles ? `, ${e.lost_bundles} bundles lost with it` : ''}`
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
export function rubbleBanner(ev, aimed) {
  if (ev?.kind !== 'rubble_fall' || !ev.cause) return null
  const robot = ev.robot ?? aimed ?? null
  if (ev.cause === 'collapse') {
    return { title: 'SECONDARY COLLAPSE', sub: robot ? `${robot} blocked` : 'A robot is blocked', tone: 'alert', size: 'major' }
  }
  return { title: 'RUBBLE', sub: robot ? `Dropped ahead of ${robot}` : 'Dropped ahead of the robot', tone: 'warn', size: 'minor', ms: 3500 }
}

export function polyCenter(poly) {
  if (!poly?.length) return null
  return [poly.reduce((t, p) => t + p[0], 0) / poly.length, poly.reduce((t, p) => t + p[1], 0) / poly.length]
}
