import { test } from 'node:test'
import assert from 'node:assert/strict'
import { CONTACT_STALE_S, FRESH_DELIVERY_S, freshDelivery, lastContact } from '../src/format.js'

test('last contact counts whole seconds, then minutes', () => {
  assert.equal(lastContact(0.4), '0 s')
  assert.equal(lastContact(12.9), '12 s')
  assert.equal(lastContact(59.99), '59 s')
  assert.equal(lastContact(65), '1 min 05 s')
  assert.equal(lastContact(-2), '0 s')
  assert.ok(CONTACT_STALE_S > 0)
})

test('a survivor pulses only when its report just arrived', () => {
  assert.equal(freshDelivery({ id: 'S1', reported_t: 100 }, 101), true)
  assert.equal(freshDelivery({ id: 'S1', reported_t: 100 }, 100 + FRESH_DELIVERY_S), true)
  // already known when the page loaded: no pulse
  assert.equal(freshDelivery({ id: 'S1', reported_t: 100 }, 100 + FRESH_DELIVERY_S + 1), false)
  assert.equal(freshDelivery({ id: 'S1' }, 5), false)
  assert.equal(freshDelivery(null, 5), false)
})
