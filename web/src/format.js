// Labels and formatting shared by the big screen and the phone.

export const STATE_LABEL = {
  DEPLOYING: 'Deploying',
  EXPLORING: 'Exploring',
  LOST_LINK_EXPLORING: 'No link, exploring',
  RETURNING_TO_SIGNAL: 'Returning to signal',
  RETURNING_HOME: 'Returning home',
  REPLANNING: 'Replanning',
  FAULT: 'Fault',
  DONE: 'Done',
  GOING_TO_POINT: 'Going to point',
  HOLDING: 'Holding',
  WAITING_FOR_LINK: 'No link, waiting', // baseline mode: no Deadzone, the robot stops until it hears CMD
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
    case 'survivor_found': return `${e.robot} found ${e.survivor}${e.linked ? '' : ' (no link, holding report)'}`
    case 'survivor_reported': return `${e.survivor} reached the command post (${e.delay_s}s after detection)`
    case 'link_lost': return `${e.robot} lost link, keeps exploring`
    case 'link_restored': return e.dark_s ? `${e.robot} back online after ${Math.round(e.dark_s)}s dark` : `${e.robot} link restored`
    case 'replan': return `${e.robot} replanned${e.reason ? `: ${REPLAN_REASON[e.reason] ?? e.reason}` : ''}`
    case 'fault': return `${e.robot} fault: ${FAULT_LABEL[e.fault] ?? e.fault}`
    case 'relay_dropped': // owner is a robot id, a relay phone's client label, or null
      if (/^R\d+$/.test(e.owner ?? '')) return `${e.owner} dropped relay ${e.id}`
      return e.owner ? `Phone ${e.owner} joined as relay ${e.id}` : `Relay ${e.id} placed`
    case 'relay_power': return `${e.phone ? `Phone relay ${e.id}` : `Relay ${e.id}`} switched ${e.on ? 'on' : 'off'}`
    case 'hotspot_rejected': return `${e.robot}'s detector rejected hot spot ${e.id}: not a person`
    case 'rescue_route': return e.updated
      ? `${e.robot} replanned the route to ${e.survivor} · ${Math.round(e.length_m)} m`
      : `${e.robot} planned a safe route to ${e.survivor} · ${Math.round(e.length_m)} m${e.beacon ? `, beacon ${e.beacon}` : ''}`
    case 'rescue_route_blocked': return `${e.robot}: route to ${e.survivor} blocked, no safe path right now`
    case 'rescue_route_reported': return `${e.updated ? 'Updated route' : 'Route'} to ${e.survivor} reached the command post · ${Math.round(e.length_m)} m`
    case 'deadline_miss': return `${e.robot} missed a ${e.task} deadline`
    case 'rubble_fall': return 'Rubble fell'
    case 'mode_changed': return e.mode === 'baseline'
      ? 'Baseline mode: without Deadzone, robots stop and wait when they lose the link'
      : 'Deadzone on: robots keep exploring in the dark'
    case 'aftershock': return `Aftershock: ceiling collapsed${e.destroyed_relay ? `, relay ${e.destroyed_relay} crushed` : ''}`
    case 'relay_destroyed': return `Relay ${e.id} destroyed${e.lost_bundles ? `, ${e.lost_bundles} bundles lost with it` : ''}`
    case 'control_error': return e.code === 'feature_disabled' ? 'Aftershock is off: start the server with DZ_AFTERSHOCK=1' : e.msg
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
