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
    case 'relay_dropped': return e.owner ? `${e.owner} dropped relay ${e.id}` : `Relay ${e.id} placed`
    case 'deadline_miss': return `${e.robot} missed a ${e.task} deadline`
    case 'rubble_fall': return 'Rubble fell'
    case 'safety_reject': return `Plan ${e.plan_id} rejected: ${e.violations?.[0]?.msg ?? 'safety check failed'}`
    default: return e.kind
  }
}
