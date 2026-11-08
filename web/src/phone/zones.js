// A new zone goes to the robot with the fewest zones (nearest by its last delivered position on
// a tie) and is searched first: robots work their zones in priority order, so a new zone at the
// back of the queue looked like nothing happened. The editor opens on it to change the robot.
export function pickRobot(zones, robots, reported, poly) {
  const load = Object.fromEntries(robots.map((r) => [r.id, 0]))
  for (const z of zones) if (z.robot in load) load[z.robot]++
  const cx = poly.reduce((t, p) => t + p[0], 0) / poly.length
  const cy = poly.reduce((t, p) => t + p[1], 0) / poly.length
  const pose = Object.fromEntries((reported ?? []).map((r) => [r.id, r.pose]))
  const far = (id) => (pose[id] ? Math.hypot(pose[id][0] - cx, pose[id][1] - cy) : Infinity)
  return [...robots].sort((a, b) => load[a.id] - load[b.id] || far(a.id) - far(b.id))[0]?.id ?? 'R1'
}

// A plan worth checking and dispatching: search zones, or no-go areas alone (Rayan's P0: the
// server keeps the current assignments, sends the exclusion to every robot and they route around).
export const hasPlanContent = (draft) => Boolean(draft && (draft.zones?.length || draft.no_go?.length))

// What the red refusal banner says: the server's own words, plus the safety rules a dispatch broke.
export function refusalText(path, { message, violations } = {}) {
  const what = path === '/api/dispatch' ? 'Dispatch refused' : 'Check refused'
  const rules = (violations ?? []).map((v) => v.msg).filter(Boolean)
  return `${what}: ${rules.length ? rules.join('; ') : message ?? 'The server did not accept this plan.'}`
}
