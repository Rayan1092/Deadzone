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

export function fmtClock(t) {
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
