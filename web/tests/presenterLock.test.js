import test from 'node:test'
import assert from 'node:assert/strict'
import { gated, heldByOthers, lostFleet, newerTable, redactHello, PRESENTER_NAME } from '../src/net/leaseState.js'

const table = (rev, holders) => ({ enabled: true, revision: rev, robots: ['R1', 'R2', 'R3'].map((robot) => ({ robot, controller: holders[robot] ? { client: 'x', name: holders[robot] } : null })) })

test('the controller token never reaches a recording or the store', () => {
  const { msg, token } = redactHello({ t: 'hello', data: { controller_token: 'secret', leases: { enabled: true }, robots: [] } })
  assert.equal(token, 'secret')
  assert.ok(!JSON.stringify(msg).includes('secret'))
  assert.deepEqual(msg.data.leases, { enabled: true })
  const tick = { t: 'tick', data: { controller_token: 'not-a-hello' } }
  assert.equal(redactHello(tick).msg, tick)          // only the hello carries the credential
  assert.equal(redactHello({ t: 'hello', data: { robots: [] } }).token, null)
})

test('an older lease table never overwrites a newer one', () => {
  assert.equal(newerTable(table(5, {}), table(4, {})), false)
  assert.equal(newerTable(table(5, {}), table(6, {})), true)
  assert.equal(newerTable(null, table(0, {})), true)
})

test('the presenter keeps the fleet only while every robot shows it as holder', () => {
  const held = { held: true, robots: ['R1', 'R2', 'R3'] }
  const all = { R1: PRESENTER_NAME, R2: PRESENTER_NAME, R3: PRESENTER_NAME }   // "Console"
  assert.equal(lostFleet(held, table(3, all)), false)
  assert.equal(lostFleet(held, table(4, { ...all, R2: null })), true)          // expired or reset
  assert.equal(lostFleet(held, table(4, { ...all, R3: 'phone-ab12' })), true)  // taken over
  assert.equal(lostFleet({ held: false, robots: [] }, table(4, {})), false)
})

test('B/U are gated only when leases are on and the presenter is not holding the fleet', () => {
  assert.equal(gated({ enabled: false }, { held: false }), false)   // flag off: nothing changes
  assert.equal(gated(null, { held: false }), false)
  assert.equal(gated({ enabled: true }, { held: false }), true)
  assert.equal(gated({ enabled: true }, { held: true }), false)
  const others = heldByOthers(table(2, { R2: 'phone-ab12' }), { held: false, robots: [] })
  assert.deepEqual(others.map((r) => r.robot), ['R2'])
})
