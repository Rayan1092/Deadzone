import test from 'node:test'
import assert from 'node:assert/strict'
import { KEY_GROUPS, helpGroups } from '../src/panels/keys.js'

test('help: four groups of plain sentences, nothing internal', () => {
  assert.deepEqual(KEY_GROUPS.map((g) => g.title), ['Run', 'View', 'Scenario', 'Model & network'])
  const keys = KEY_GROUPS.flatMap((g) => g.keys)
  const names = keys.map(([k]) => k)
  for (const gone of ['?', 'S', 'T', 'E', '?replay']) assert.ok(!names.includes(gone), `${gone} is gone`)
  assert.equal(new Set(names).size, names.length)
  for (const [k, line] of keys) {
    assert.match(line, /^[A-Z0-9].*[.)]$/, `${k}: a sentence`)
    assert.doesNotMatch(line, /DZ_|server|flag|Q&A|judge|presenter|record|Yusuf|Rayan|Aziz|built by/i, `${k}: ${line}`)
  }
  assert.ok(keys.some(([k, l]) => k === 'N' && /main scenario/.test(l)))
  assert.ok(KEY_GROUPS.find((g) => g.title === 'View').keys.some(([k, l]) => k === 'K' && l === 'Lighting: night / day.'))
})

test('help: Y shows only when the run has a belief map', () => {
  const has = (groups, key) => groups.some((g) => g.keys.some(([k]) => k === key))
  assert.equal(has(helpGroups(), 'Y'), false)
  assert.equal(has(helpGroups({ belief: false }), 'Y'), false)
  assert.equal(has(helpGroups({ belief: true }), 'Y'), true)
  assert.equal(has(helpGroups(), 'W'), true)
  assert.equal(helpGroups().length, KEY_GROUPS.length)
})
