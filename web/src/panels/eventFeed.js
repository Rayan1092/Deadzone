// Event feed helpers for the big-screen sidebar (pure, so they can be checked without a DOM).
// The words come from format.js describeEvent (shared with the phone); this file only sorts
// events into the four filter groups and puts each robot's name, in its own colour, where the
// line names a robot id.

export const FILTERS = [
  { id: 'ai', label: 'AI' },
  { id: 'radio', label: 'Radio' },
  { id: 'faults', label: 'Faults' },
  { id: 'plans', label: 'Plans' },
]

const CATEGORY = {
  // what the onboard detector decided
  survivor_found: 'ai', hotspot_unsure: 'ai', hotspot_rejected: 'ai',
  // links, relays, and what reached the command post over the radio
  link_lost: 'radio', link_restored: 'radio', relay_dropped: 'radio', relay_power: 'radio',
  relay_destroyed: 'radio', survivor_reported: 'radio', rescue_route_reported: 'radio',
  command_ack_reported: 'radio',
  // things going wrong, and the robot coping
  fault: 'faults', fault_injected: 'faults', deadline_miss: 'faults', resumed: 'faults',
  robot_contact: 'faults', aftershock: 'faults', rubble_fall: 'faults', replan: 'faults',
  rescue_route_blocked: 'faults',
  // the mission: plans, rescue routes, commands, modes
  plan_dispatched: 'plans', plan_applied: 'plans', safety_reject: 'plans', rescue_route: 'plans',
  command_received: 'plans', mode_changed: 'plans', robot_shutdown: 'plans',
}

// null = always shown (presenter notes, control errors): never hidden by a filter
export function eventCategory(kind) {
  return CATEGORY[kind] ?? null
}

export function visibleEvents(events, active, limit = 10) {
  const out = []
  for (const e of events) {
    const cat = eventCategory(e.kind)
    if (cat === null || active.has(cat)) out.push(e)
    if (out.length === limit) break
  }
  return out
}

// Robot ids an event is about (owner may also be a phone label, so only R<n> counts).
export function robotIds(e) {
  const ids = [e.robot, e.by, e.a, e.b, e.owner].filter((v) => typeof v === 'string' && /^R\d+$/.test(v))
  return [...new Set(ids)]
}

// Split a line into text and robot parts: [{ text } | { robot: { id, name, color } }].
export function feedParts(text, ids, meta) {
  const known = ids.map((id) => meta.find((m) => m.id === id)).filter(Boolean)
  if (!known.length) return [{ text }]
  const byId = Object.fromEntries(known.map((m) => [m.id, m]))
  const re = new RegExp(`\\b(${known.map((m) => m.id).join('|')})\\b`, 'g')
  const parts = []
  let last = 0
  for (const m of text.matchAll(re)) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index) })
    parts.push({ robot: byId[m[1]] })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last) })
  // the line is about a robot but does not name it (e.g. "S1 reached the command post"): lead with it
  if (last === 0) return [{ robot: known[0] }, { text: `: ${text}` }]
  return parts
}

const KEY = 'dz-feed-filters'
export function readFilters() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    if (Array.isArray(saved) && saved.every((f) => FILTERS.some((x) => x.id === f))) return new Set(saved)
  } catch { /* storage blocked or bad value: defaults */ }
  return new Set(FILTERS.map((f) => f.id))
}
export function saveFilters(active) {
  try { localStorage.setItem(KEY, JSON.stringify([...active])) } catch { /* session only */ }
}
