import { usePhone } from './store'
import { sendPhone } from './socket'

// Shared draft editing for planner phones. The server keeps one draft
// (last write wins) and broadcasts it as plan_state to every phone.

export const RULE_LABEL = {
  battery_reserve: 'Battery reserve too low',
  capability: 'Robot cannot do this',
  no_go_overlap: 'Overlaps a no-go area',
  zone_unreachable: 'Zone unreachable',
  comms_plan: 'Dead zone with no relay plan',
}

export const MIN_SIDE = 1 // m, smallest zone you can draw
export const snap = (v) => Math.round(v * 2) / 2

export function rectPoly([ax, ay], [bx, by]) {
  const x0 = Math.min(ax, bx)
  const x1 = Math.max(ax, bx)
  const y0 = Math.min(ay, by)
  const y1 = Math.max(ay, by)
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
}

export function pointInPoly([x, y], poly) {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i]
    const [xj, yj] = poly[j]
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

function nextId(prefix, draft) {
  const taken = new Set([...draft.zones, ...draft.no_go].map((r) => r.id))
  let n = 1
  while (taken.has(`${prefix}${n}`)) n++
  return `${prefix}${n}`
}

function bumpPlanId(id) {
  const n = parseInt(id?.match(/(\d+)$/)?.[1] ?? '0', 10)
  return `P-${n + 1}`
}

const emptyDraft = () => ({ plan_id: 'P-1', zones: [], no_go: [], lost_link_budget_s: 60 })

// ------------------------------------------------------------------ edits
let timer = null

// Apply a change locally now; send it shortly after so sliders don't flood the socket.
export function commit(change) {
  const s = usePhone.getState()
  const draft = structuredClone(s.draft ?? emptyDraft())
  // A dispatched plan ID is immutable on the server, so edits start a new plan.
  if (s.dispatched.includes(draft.plan_id)) draft.plan_id = bumpPlanId(draft.plan_id)
  change(draft)
  s.set({ draft, safety: null, pending: true })
  clearTimeout(timer)
  timer = setTimeout(flush, 250)
}

export function flush() {
  clearTimeout(timer)
  timer = null
  const s = usePhone.getState()
  s.set({ pending: false })
  // The server requires at least one zone; no-go-only drafts stay local until then.
  if (!s.draft?.zones.length) return
  const { plan_id, zones, no_go, lost_link_budget_s } = s.draft
  sendPhone('plan_edit', { plan_id, zones, no_go, lost_link_budget_s })
}

export function addRegion(kind, poly) {
  let id = null
  commit((d) => {
    if (kind === 'zone') {
      const robots = usePhone.getState().hello?.robots ?? []
      const used = new Set(d.zones.map((z) => z.robot))
      const robot = (robots.find((r) => !used.has(r.id)) ?? robots[0])?.id ?? 'R1'
      id = nextId('Z', d)
      d.zones.push({ id, robot, priority: Math.min(10, d.zones.length + 1), poly, comms: 'relay' })
    } else {
      id = nextId('NG', d)
      d.no_go.push({ id, poly, reason: 'Responder no-go area' })
    }
  })
  usePhone.getState().set({ selected: id, mode: 'view' })
}

export function updateZone(id, fields) {
  commit((d) => {
    const z = d.zones.find((r) => r.id === id)
    if (z) Object.assign(z, fields)
  })
}

export function removeRegion(id) {
  commit((d) => {
    d.zones = d.zones.filter((r) => r.id !== id)
    d.no_go = d.no_go.filter((r) => r.id !== id)
  })
  usePhone.getState().set({ selected: null })
}

export function setBudget(seconds) {
  commit((d) => { d.lost_link_budget_s = seconds })
}

// The server answered that this ID was already dispatched (by another phone).
export function forkDispatched() {
  const s = usePhone.getState()
  if (!s.draft) return
  s.set({ dispatched: [...new Set([...s.dispatched, s.draft.plan_id])] })
  commit(() => {})
}

// ------------------------------------------------------------------ check + dispatch
export function checkPlan() {
  flush()
  const { draft, set } = usePhone.getState()
  if (!draft?.zones.length) return
  set({ checking: true, safety: null })
  sendPhone('plan_submit', { plan_id: draft.plan_id })
}

export async function dispatchPlan() {
  flush()
  const { draft, set } = usePhone.getState()
  if (!draft?.zones.length) return
  set({ checking: true })
  try {
    const res = await fetch('/api/dispatch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: draft.plan_id }),
    })
    const body = await res.json()
    if (!res.ok) throw new Error(body.detail?.msg ?? 'Dispatch failed')
    const s = usePhone.getState()
    if (body.ok) s.set({ dispatched: [...new Set([...s.dispatched, body.plan_id])], checking: false })
    else s.set({ safety: body, checking: false }) // rechecked against newer Command knowledge and rejected
  } catch (err) {
    usePhone.getState().set({ checking: false, error: { code: 'dispatch', msg: err.message, at: Date.now() } })
  }
}
