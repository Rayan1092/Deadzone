import test, { before, after, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { canSendPlan } from './sync.js'

// Load the actual phone actions/store through Vite (extensionless app imports).
// Middleware mode + disabled HMR never starts a network listener.
let vite, phone, plan, seed, requests, reply, originalFetch
const populated = () => ({ plan_id: 'P-1', zones: [], no_go: [{ id: 'NG1' }], lost_link_budget_s: 60 })
before(async () => {
  vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  phone = await vite.ssrLoadModule('/src/phone/store.js')
  plan = await vite.ssrLoadModule('/src/phone/plan.js')
  seed = { ...phone.usePhone.getState() }
  originalFetch = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    const body = JSON.parse(options.body)
    requests.push({ path, body })
    return { ok: true, json: async () => path === '/api/dispatch' ? reply(body) : { saved: true } }
  }
})
beforeEach(() => {
  requests = []
  reply = (body) => ({ ok: true, plan_id: body.plan_id })
  phone.usePhone.setState({ ...seed, connected: true, hello: {
    client: 'phone-1', plan_epoch: 'incident-a', robots: [{ id: 'R1' }, { id: 'R2' }, { id: 'R3' }],
  }, draft: populated(), pending: true, dispatched: [], lastDispatch: null })
})
after(async () => { globalThis.fetch = originalFetch; await vite?.close() })

test('deleting the last dispatched no-go saves a new empty ID before sending to the whole fleet', async () => {
  await plan.dispatchPlan()
  assert.equal(phone.usePhone.getState().lastDispatch.hasContent, true)
  plan.removeRegion('NG1')
  const empty = phone.usePhone.getState()
  assert.equal(empty.draft.plan_id, 'P-2')
  assert.equal(canSendPlan(empty), true)
  requests = []
  await plan.dispatchPlan()
  assert.deepEqual(requests.map((r) => r.path), ['/api/plan?check=false', '/api/dispatch'])
  assert.deepEqual(requests[0].body.no_go, [])
  assert.deepEqual(requests[0].body.zones, [])
  assert.equal(requests[1].body.plan_id, 'P-2')
  assert.deepEqual(phone.usePhone.getState().lastDispatch, { plan_id: 'P-2', hasContent: false, robots: 3 })
})

test('Clear all removes zones and no-go areas and immediately dispatches an empty plan', async () => {
  phone.usePhone.getState().draft.zones = [{ id: 'Z1', robot: 'R1' }]
  await plan.dispatchPlan()
  requests = []
  await plan.clearAll()
  assert.deepEqual(requests[0].body.zones, [])
  assert.deepEqual(requests[0].body.no_go, [])
  assert.equal(requests[1].path, '/api/dispatch')
  assert.equal(phone.usePhone.getState().lastDispatch.robots, 3)
  // Repeating Clear all must fork the immutable accepted ID too.
  await plan.clearAll()
  assert.equal(phone.usePhone.getState().lastDispatch.plan_id, 'P-3')
})

test('a pristine empty draft has no implicit send, but explicit Clear all can clear an unknown older plan', async () => {
  phone.usePhone.setState({ draft: { ...populated(), no_go: [] } })
  assert.equal(canSendPlan(phone.usePhone.getState()), false)
  await plan.dispatchPlan()
  assert.equal(requests.length, 0)
  await plan.clearAll()
  assert.equal(requests.at(-1).path, '/api/dispatch')
})

test('refused and failed clears keep the previous dispatch and show the refusal instead of success', async () => {
  await plan.dispatchPlan()
  const previous = phone.usePhone.getState().lastDispatch
  reply = () => ({ ok: false, plan_id: 'P-2', violations: [{ msg: 'Command refused' }] })
  await plan.clearAll()
  assert.equal(phone.usePhone.getState().lastDispatch, previous)
  assert.match(phone.usePhone.getState().refusal.msg, /Command refused/)
  reply = () => { throw new Error('Network failed') }
  await plan.dispatchPlan()
  assert.equal(phone.usePhone.getState().lastDispatch, previous)
  assert.match(phone.usePhone.getState().refusal.msg, /Network failed/)
})

test('offline Clear all makes no edits or requests', async () => {
  phone.usePhone.setState({ connected: false })
  const draft = phone.usePhone.getState().draft
  await plan.clearAll()
  assert.equal(phone.usePhone.getState().draft, draft)
  assert.equal(requests.length, 0)
})

test('failed saves never dispatch a clear or show a clear receipt', async () => {
  const transport = globalThis.fetch
  globalThis.fetch = async () => { throw new Error('Save failed') }
  try {
    await plan.clearAll()
    assert.equal(phone.usePhone.getState().lastDispatch, null)
    assert.equal(phone.usePhone.getState().pending, true)
    assert.equal(phone.usePhone.getState().checking, false)
    assert.equal(requests.length, 0)
  } finally { globalThis.fetch = transport }
})

test('a dispatch from another phone establishes the content needed to clear on this phone', async () => {
  phone.usePhone.setState({ pending: false })
  phone.handlePhoneMessage({ t: 'event', data: { kind: 'plan_dispatched', plan_id: 'P-1' } })
  plan.removeRegion('NG1')
  assert.equal(canSendPlan(phone.usePhone.getState()), true)
  await plan.dispatchPlan()
  assert.equal(phone.usePhone.getState().lastDispatch.hasContent, false)
})

test('reconnect retains clear eligibility, and a new incident removes old dispatch history', async () => {
  await plan.dispatchPlan()
  plan.removeRegion('NG1')
  await plan.flush()
  const s = phone.usePhone.getState()
  phone.handlePhoneMessage({ t: 'hello', time: 1, data: { ...s.hello, plan: s.draft, dispatched_plan_ids: ['P-1'] } })
  assert.equal(canSendPlan(phone.usePhone.getState()), true)
  phone.handlePhoneMessage({ t: 'hello', time: 0, data: { ...s.hello, plan_epoch: 'incident-b', plan: null, dispatched_plan_ids: [] } })
  assert.equal(phone.usePhone.getState().lastDispatch, null)
  assert.equal(canSendPlan(phone.usePhone.getState()), false)
})

test('a reset during dispatch cannot publish an old clear confirmation', async () => {
  let release
  reply = () => new Promise((resolve) => { release = resolve })
  const sending = plan.clearAll()
  while (!release) await new Promise((resolve) => setImmediate(resolve))
  const s = phone.usePhone.getState()
  phone.handlePhoneMessage({ t: 'hello', time: 0, data: { ...s.hello, plan_epoch: 'incident-b', plan: null, dispatched_plan_ids: [] } })
  release({ ok: true, plan_id: 'P-1' })
  await sending
  assert.equal(phone.usePhone.getState().lastDispatch, null)
  assert.deepEqual(phone.usePhone.getState().dispatched, [])
})
