import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describeEvent, fieldUnitName, isScenarioEvent, radioFailBanner, scheduledScenario, unitName } from '../src/format.js'
import { PRESENTER_NAME } from '../src/net/leaseState.js'

test('phones show as field units, numbered by the shared lease table', () => {
  assert.equal(unitName('phone-3'), 'Field unit 3')
  assert.equal(unitName('phone-k3f2'), 'Field unit K3F2')
  assert.equal(unitName('Console'), 'Console')
  assert.equal(describeEvent({ kind: 'relay_dropped', id: 'P2', owner: 'phone-2' }), 'Field unit 2 joined as relay P2')
  const leases = { robots: [
    { robot: 'R1', controller: { client: 'phone-aa', name: 'Field unit 1' } },
    { robot: 'R2', controller: null },
    { robot: 'R3', controller: { client: 'phone-bb', name: 'Field unit 2' } }] }
  assert.equal(fieldUnitName(leases, 'phone-cc'), 'Field unit 3')       // a third phone
  assert.equal(fieldUnitName(leases, 'phone-bb'), 'Field unit 2')       // keeps its number for a second robot
  assert.equal(fieldUnitName({ robots: [] }, 'phone-aa'), 'Field unit 1')
  assert.equal(PRESENTER_NAME, 'Console')                                // phones read "Console has control"
})

test("scenario events from the floor plan's events list are matched by type and time", () => {
  const events = [{ t: 162.5, type: 'collapse', near: 'R1' }, { t: 200, type: 'aftershock' }, { t: 240, type: 'radio_fail', label: 'Relay RL2 floods' }]
  assert.equal(scheduledScenario({ kind: 'aftershock' }, 200.1, events)?.type, 'aftershock')
  assert.equal(scheduledScenario({ kind: 'aftershock' }, 150, events), null)              // an A-key aftershock
  assert.equal(scheduledScenario({ kind: 'rubble_fall', cause: 'collapse' }, 162.6, events)?.near, 'R1')
  assert.equal(scheduledScenario({ kind: 'relay_destroyed', cause: 'radio_fail' }, 240, events)?.type, 'radio_fail')
  assert.ok(isScenarioEvent({ kind: 'aftershock' }, { scheduled: events[1] }))
  const b = radioFailBanner({ kind: 'radio_fail', relay: 'RL2', lost_bundles: 3 }, 'Relay RL2 floods')
  assert.deepEqual([b.title, b.sub], ['RADIO FAILURE', 'Scenario event · Relay RL2 floods · 3 bundles lost'])
  assert.equal(describeEvent({ kind: 'radio_fail', relay: 'RL1' }), "Relay RL1's radio failed")
})

test('scenario events: the scripted collapse always, timeline disasters unless this console asked', () => {
  assert.ok(isScenarioEvent({ kind: 'rubble_fall', cause: 'collapse' }))
  assert.ok(!isScenarioEvent({ kind: 'rubble_fall', cause: 'key' }, { timeline: true }))
  assert.ok(isScenarioEvent({ kind: 'aftershock' }, { timeline: true }))
  assert.ok(!isScenarioEvent({ kind: 'aftershock' }, { timeline: true, pressedRecently: true }))
  assert.ok(!isScenarioEvent({ kind: 'aftershock' }, { timeline: false }))
  assert.ok(isScenarioEvent({ kind: 'radio_fail', source: 'timeline' }))
})

// No "judge" or "presenter" in anything the web app shows: string literals and JSX text in
// web/src (comments, identifiers, CSS class names and the stored layout id are not shown).
test('no "judge" or "presenter" left in user-facing web text', () => {
  const files = []
  const walk = (d) => readdirSync(d).forEach((f) => { const p = join(d, f); statSync(p).isDirectory() ? walk(p) : /\.(jsx?|html)$/.test(f) && files.push(p) })
  walk(new URL('../src', import.meta.url).pathname)
  const bad = []
  for (const f of files) {
    readFileSync(f, 'utf8').split('\n').forEach((line, i) => {
      const code = line.replace(/\/\/.*$/, '').replace(/^\s*\*.*$/, '').replace(/\{\/\*.*?\*\/\}/g, '')
      // quoted strings and JSX text between tags
      const texts = [...code.matchAll(/'([^']*)'|"([^"]*)"|`([^`]*)`|>([^<>{}]+)</g)].map((m) => m[1] ?? m[2] ?? m[3] ?? m[4])
      for (const s of texts) {
        if (!/judge|presenter/i.test(s)) continue
        if (/^(judge|full)$|judge-|judge_pool|^\.\/|^\.\.\//.test(s)) continue   // the stored layout id, class names, paths
        bad.push(`${f.split('/src/')[1]}:${i + 1}: ${s.trim()}`)
      }
    })
  }
  assert.deepEqual(bad, [])
})

test('plan captions: zone assignment, plan pending while dark, holding first', async () => {
  const { planCaption, zoneLabel, NO_GO_HOLD } = await import('../src/format.js')
  assert.equal(zoneLabel('Z3'), 'Zone 3')
  assert.equal(zoneLabel('ZNE'), 'Zone ZNE')
  const plan = { plan_id: 'P-2', zones: [{ id: 'Z3', robot: 'R2' }] }
  const r2 = { id: 'R2', name: 'Scout 2', plan_id: 'P-1', zone: 'ZNE', link: { up: false } }
  assert.deepEqual(planCaption(r2, { dispatched: ['P-1', 'P-2'], plan }), { kind: 'pending', text: 'plan pending · robot dark' })
  assert.equal(planCaption({ ...r2, link: { up: true } }, { dispatched: ['P-1', 'P-2'], plan }).text, 'plan pending')
  assert.equal(planCaption({ ...r2, plan_id: 'P-2', zone: 'Z3', link: { up: true } }, { dispatched: ['P-1', 'P-2'], plan }).text, 'Scout 2 → Zone 3')
  assert.equal(planCaption({ ...r2, state: 'WAITING' }, { dispatched: ['P-2'], plan }).text, NO_GO_HOLD)
  assert.equal(NO_GO_HOLD, 'Holding · no-go blocks all routes')
  // a no-go-only plan names no robot: nothing is pending, robots keep their zones
  assert.equal(planCaption({ ...r2, link: { up: true } }, { dispatched: ['P-1', 'P-3'], plan: { plan_id: 'P-3', zones: [] } }).text, 'Scout 2 → Zone ZNE')
  assert.equal(planCaption({ id: 'R1', link: { up: true } }), null)
})

test('robot identity label: link in dBm, then NO LINK with seconds since Command heard it', async () => {
  const { robotTag } = await import('../src/format.js')
  assert.deepEqual(robotTag({ id: 'R1', link: { up: true, rssi: -75.6 } }, null, 10), { text: 'R1 · LINK −76 dBm', dark: false })
  assert.deepEqual(robotTag({ id: 'R2', link: { up: false } }, { last_seen: 88 }, 100.4), { text: 'R2 · NO LINK · 12 s', dark: true })
  assert.equal(robotTag({ id: 'R3', state: 'SHUTDOWN', link: { up: true, rssi: -50 } }, null, 0).text, 'R3 · POWERED DOWN')
})
