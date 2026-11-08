import test from 'node:test'
import assert from 'node:assert/strict'
import { createDraftSync, phoneHelloState } from '../src/phone/sync.js'

function state() {
  const s = {
    connected: true, pending: true, hello: { client: 'phone-a', plan_epoch: 'incident-a' },
    draft: { plan_id: 'P-1', zones: [], no_go: [{ id: 'NG1', poly: [[1, 1], [2, 1], [2, 2]] }], lost_link_budget_s: 60 },
    dispatched: [], selected: 'NG1', time: .1, view: { robots: [] }, map: new Uint8Array([1]),
  }
  s.set = (patch) => Object.assign(s, patch)
  return s
}
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('no-go-only and cleared drafts wait for an acknowledgment before becoming saved', async () => {
  const s = state()
  const ack = deferred()
  const requests = []
  const flush = createDraftSync(() => s, async (path, body) => {
    requests.push({ path, body })
    await ack.promise
  })
  const saved = flush()
  assert.equal(s.pending, true)
  ack.resolve()
  assert.equal(await saved, true)
  assert.equal(s.pending, false)
  assert.equal(requests[0].body.author, 'phone-a')
  assert.equal(requests[0].body.plan_epoch, 'incident-a')
  assert.equal(requests[0].body.no_go.length, 1)
  s.draft = { ...s.draft, no_go: [] }
  s.pending = true
  assert.equal(await flush(), true)
  assert.deepEqual(requests[1].body.zones, [])
  assert.deepEqual(requests[1].body.no_go, [])
})

test('disconnects and failed HTTP saves keep edits available for retry', async () => {
  const s = state()
  s.connected = false
  let calls = 0
  const flush = createDraftSync(() => s, async () => { calls++; throw new Error('Network failed') })
  assert.equal(await flush(), false)
  assert.equal(calls, 0)
  s.connected = true
  assert.equal(await flush(), false)
  assert.equal(s.pending, true)
  assert.equal(s.draft.no_go[0].id, 'NG1')
  assert.equal(s.error.msg, 'Network failed')
})

test('edits during a save are serialized, and callers wait for the newest draft', async () => {
  const s = state()
  const a = deferred(), b = deferred()
  const requests = []
  const flush = createDraftSync(() => s, async (path, body) => {
    requests.push(body)
    await (requests.length === 1 ? a.promise : b.promise)
  })
  const saved = flush()
  const waitingCheck = flush()
  assert.equal(saved, waitingCheck)
  s.draft = { ...s.draft, lost_link_budget_s: 90 }
  a.resolve()
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(requests.length, 2)
  assert.equal(requests[1].lost_link_budget_s, 90)
  assert.equal(s.pending, true)
  b.resolve()
  assert.equal(await waitingCheck, true)
  assert.equal(s.pending, false)
})

test('an old incident save cannot clear or report errors on the new incident', async () => {
  for (const fail of [false, true]) {
    const s = state(), ack = deferred()
    const saved = createDraftSync(() => s, () => ack.promise)()
    s.hello = { client: 'phone-a', plan_epoch: 'incident-b' }
    s.draft = null
    s.pending = false
    if (fail) ack.reject(new Error('Old incident failed'))
    else ack.resolve()
    assert.equal(await saved, false)
    assert.equal(s.error, undefined)
    assert.equal(s.draft, null)
  }
})

test('reconnect preserves unsaved edits only within the same incident', () => {
  const s = state()
  const hello = { ...s.hello, plan: { plan_id: 'server-plan' }, dispatched_plan_ids: ['P-1'] }
  const restored = phoneHelloState(s, hello, .1)
  assert.equal(restored.draft, s.draft)
  assert.equal(restored.pending, true)
  assert.deepEqual(restored.dispatched, ['P-1'])
  const reset = phoneHelloState(s, { ...hello, plan_epoch: 'incident-b', plan: null, dispatched_plan_ids: [] }, .1)
  assert.equal(reset.pending, false)
  assert.equal(reset.draft, null)
  assert.equal(reset.map, null)
  assert.equal(reset.view, null)
  assert.deepEqual(reset.dispatched, [])
})
