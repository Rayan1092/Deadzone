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

test('inset size: default about a fifth, clamped, remembered, bad values fall back', async () => {
  const { INSET_DEFAULT, INSET_KEY, clampInset, loadInset, saveInset } = await import('../src/three/insetSize.js')
  const mem = new Map()
  const storage = { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, v) }
  assert.deepEqual(loadInset(storage), INSET_DEFAULT)
  assert.ok(INSET_DEFAULT.w < 0.46 && INSET_DEFAULT.h < 0.48, 'smaller than before')
  // never smaller than the header needs, never over the pane
  assert.deepEqual(clampInset({ w: 0.01, h: 0.01 }, 1920, 1080), { w: 260 / 1920, h: 180 / 1080 })
  assert.deepEqual(clampInset({ w: 2, h: 2 }, 1920, 1080), { w: 0.9, h: 0.85 })
  saveInset(storage, { w: 0.25, h: 0.3 })
  assert.deepEqual(loadInset(storage), { w: 0.25, h: 0.3 })
  mem.set(INSET_KEY, 'not json')
  assert.deepEqual(loadInset(storage), INSET_DEFAULT)
  mem.set(INSET_KEY, '{"w":-1,"h":0.3}')
  assert.deepEqual(loadInset(storage), INSET_DEFAULT)
  const broken = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') } }
  assert.deepEqual(loadInset(broken), INSET_DEFAULT)
  saveInset(broken, { w: 0.3, h: 0.3 }) // does not throw
})
