import { usePhone } from './store'
import { createDraftSync, postJSON } from './sync'
import { pickRobot } from './zones'

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
  if (s.checking) return
  const draft = structuredClone(s.draft ?? emptyDraft())
  // A dispatched plan ID is immutable on the server, so edits start a new plan.
  while (s.dispatched.includes(draft.plan_id)) draft.plan_id = bumpPlanId(draft.plan_id)
  draft.author = s.hello?.client
  change(draft)
  s.set({ draft, safety: null, pending: true })
  clearTimeout(timer)
  timer = setTimeout(flush, 250)
}

const saveDraft = createDraftSync(usePhone.getState)

export function flush() {
  clearTimeout(timer)
  timer = null
  return saveDraft()
}

export function addRegion(kind, poly) {
  let id = null
  commit((d) => {
    if (kind === 'zone') {
      const s = usePhone.getState()
      const robot = pickRobot(d.zones, s.hello?.robots ?? [], s.view?.robots, poly)
      for (const z of d.zones) if (z.robot === robot) z.priority = Math.min(10, z.priority + 1)
      id = nextId('Z', d)
      d.zones.push({ id, robot, priority: 1, poly, comms: 'relay' })
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
export async function checkPlan() {
  return planAction('/api/plan/check')
}

export async function dispatchPlan() {
  return planAction('/api/dispatch')
}

async function planAction(path) {
  const initial = usePhone.getState()
  if (initial.checking || !initial.draft?.zones.length) return
  initial.set({ checking: true, safety: null })
  const epoch = initial.hello?.plan_epoch
  let draft = null
  try {
    if (!await flush()) return
    if (usePhone.getState().hello?.plan_epoch !== epoch) return
    draft = usePhone.getState().draft
    const body = await postJSON(path, { plan_id: draft.plan_id, plan_epoch: epoch })
    const s = usePhone.getState()
    if (s.hello?.plan_epoch !== epoch || s.draft !== draft) return
    if (path === '/api/dispatch' && body.ok) {
      s.set({ dispatched: [...new Set([...s.dispatched, body.plan_id])] })
    } else s.set({ safety: body })
  } catch (err) {
    if (usePhone.getState().hello?.plan_epoch === epoch) {
      usePhone.getState().set({ error: { code: err.code ?? 'plan', msg: err.message, at: Date.now() } })
    }
  } finally {
    if (usePhone.getState().hello?.plan_epoch === epoch) usePhone.getState().set({ checking: false })
  }
}
