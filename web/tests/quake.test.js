import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { pickAftershock } from '../src/quake.js'

const plan = (name) => JSON.parse(readFileSync(new URL(`../../data/floorplans/${name}.json`, import.meta.url), 'utf8'))
const state = (fp, relays = [], robots = []) => ({ floorplan: fp, tick: { reality: { relays, robots } } })
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1])

test('each press lands somewhere new, inside the building', () => {
  const fp = plan('collapse_01')
  const spots = Array.from({ length: 12 }, () => pickAftershock(state(fp)).at)
  assert.ok(spots.every(Boolean))
  assert.ok(new Set(spots.map(String)).size >= 10)
  for (const [x, y] of spots) assert.ok(x > 1 && y > 1 && x < fp.size[0] - 1 && y < fp.size[1] - 1)
})

test('keeps clear of survivors, the entrance and robots', () => {
  const fp = plan('collapse_01')
  const robot = [20, 15, 0]
  for (let i = 0; i < 20; i++) {
    const { at } = pickAftershock(state(fp, [], [{ pose: robot }]))
    assert.ok(fp.survivors.every((s) => dist(at, s.pos) >= 2.5))
    assert.ok(dist(at, fp.entry) >= 3)
    assert.ok(dist(at, robot) >= 1.8)
  }
})

test('crushes a working relay next to the collapse, never a beacon or a phone', () => {
  const fp = plan('collapse_01')
  const relays = [
    { id: 'R1', pos: [12, 15], on: true, phone: false },
    { id: 'R2', pos: [30, 15], on: true, phone: false },
    { id: 'B1', pos: [26, 15], on: true, phone: false, beacon_for: 'S2' },
    { id: 'P1', pos: [8, 15], on: true, phone: true },
    { id: 'R9', pos: [18, 15], on: false, phone: false, destroyed: true },
  ]
  const used = new Set()
  for (let i = 0; i < 20; i++) {
    const { at, relay } = pickAftershock(state(fp, relays))
    assert.ok(['R1', 'R2'].includes(relay))
    assert.ok(dist(at, relays.find((r) => r.id === relay).pos) <= 1.7)
    used.add(relay)
  }
  assert.equal(used.size, 2)
})

test('works on generated buildings and sends nothing without a floor plan', () => {
  for (const name of ['generated/gen_1', 'generated/gen_2', 'generated/gen_3']) assert.ok(pickAftershock(state(plan(name))).at)
  assert.deepEqual(pickAftershock({ floorplan: null }), {})
})
