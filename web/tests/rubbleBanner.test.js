import test from 'node:test'
import assert from 'node:assert/strict'
import { describeEvent, polyCenter, rubbleBanner } from '../src/format.js'

const poly = [[10, 10], [11.4, 10], [11.4, 11.4], [10, 11.4]]

test('the scripted secondary collapse gets the big banner naming the blocked robot', () => {
  const b = rubbleBanner({ kind: 'rubble_fall', poly, cause: 'collapse', robot: 'R1' })
  assert.deepEqual(b, { title: 'SECONDARY COLLAPSE', sub: 'R1 blocked', tone: 'alert', size: 'major' })
  assert.equal(describeEvent({ kind: 'rubble_fall', cause: 'collapse', robot: 'R1' }), "Secondary collapse: rubble across R1's path")
})

test("an R press gets the smaller banner with the server's robot, else the one the screen aimed at", () => {
  assert.equal(rubbleBanner({ kind: 'rubble_fall', poly, cause: 'key', robot: 'R2' }, 'R1').sub, 'Dropped ahead of R2')
  assert.equal(rubbleBanner({ kind: 'rubble_fall', poly, cause: 'key' }, 'R3').sub, 'Dropped ahead of R3')
  const b = rubbleBanner({ kind: 'rubble_fall', poly, cause: 'key', robot: 'R2' })
  assert.equal(b.size, 'minor')
  assert.ok(b.ms < 5500)
})

test('rubble without a cause (an aftershock, an old server) gets no rubble banner', () => {
  assert.equal(rubbleBanner({ kind: 'rubble_fall', poly }), null)
  assert.equal(rubbleBanner({ kind: 'aftershock', cause: 'collapse' }), null)
  assert.equal(describeEvent({ kind: 'rubble_fall' }), 'Rubble fell')
})

test('the collapse shake centers on the rubble footprint', () => {
  assert.deepEqual(polyCenter(poly).map((v) => Math.round(v * 10) / 10), [10.7, 10.7])
  assert.equal(polyCenter([]), null)
})
