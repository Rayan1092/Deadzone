import test from 'node:test'
import assert from 'node:assert/strict'
import { KEY_GROUPS } from '../src/panels/keys.js'

test('help: four groups of plain sentences, nothing internal', () => {
  assert.deepEqual(KEY_GROUPS.map((g) => g.title), ['Run', 'View', 'Scenario', 'Model & network'])
  const keys = KEY_GROUPS.flatMap((g) => g.keys)
  const names = keys.map(([k]) => k)
  for (const gone of ['?', 'S', 'T', 'K', 'E', '?replay']) assert.ok(!names.includes(gone), `${gone} is gone`)
  assert.equal(new Set(names).size, names.length)
  for (const [k, line] of keys) {
    assert.match(line, /^[A-Z0-9].*[.)]$/, `${k}: a sentence`)
    assert.doesNotMatch(line, /DZ_|server|flag|Q&A|judge|presenter|record|Yusuf|Rayan|Aziz|built by/i, `${k}: ${line}`)
  }
  assert.ok(keys.some(([k, l]) => k === 'N' && /main scenario/.test(l)))
})
