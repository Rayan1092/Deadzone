import test from 'node:test'
import assert from 'node:assert/strict'
import { CONFIRMED, beliefPixel, missingText } from '../src/three/beliefRamp.js'

test('one colour ramp: nothing where nobody is likely, brighter and more opaque where someone may be', () => {
  assert.deepEqual(beliefPixel(0), [0, 0, 0, 0])
  const low = beliefPixel(20)
  const high = beliefPixel(254)
  assert.ok(high[3] > low[3] && low[3] > 0)
  assert.ok(high[0] > low[0] && high[1] > low[1])             // lighter violet at the top of the ramp
})

test('a confirmed survivor cell is a distinct teal marker, not the heat colour', () => {
  const mark = beliefPixel(CONFIRMED)
  assert.deepEqual(mark.slice(0, 3), [45, 212, 191])
  assert.ok(mark[3] > 200)
})

test('the estimate reads in whole people, and stays hidden without one', () => {
  assert.equal(missingText(2.3), 'about 2 people')
  assert.equal(missingText(0.6), 'about 1 person')
  assert.equal(missingText(0.2), 'about 0 people')
  assert.equal(missingText(null), null)
  assert.equal(missingText(NaN), null)
})
