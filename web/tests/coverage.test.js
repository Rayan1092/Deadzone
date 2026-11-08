import test from 'node:test'
import assert from 'node:assert/strict'
import { coveragePixel } from '../src/three/coverageRamp.js'
import { KEY_GROUPS } from '../src/panels/keys.js'

test('coverage: strong teal, weak amber, dead red, translucent', () => {
  assert.deepEqual(coveragePixel(-55).slice(0, 3), [45, 212, 191])
  assert.deepEqual(coveragePixel(-74).slice(0, 3), [245, 158, 11])
  assert.deepEqual(coveragePixel(-100).slice(0, 3), [239, 68, 68])
  for (const d of [-40, -74, -95]) assert.ok(coveragePixel(d)[3] < 128)
  assert.deepEqual(coveragePixel(null), [0, 0, 0, 0])
  assert.ok(KEY_GROUPS.find((g) => g.title === 'Model & network').keys.some(([k]) => k === 'W'))
})
