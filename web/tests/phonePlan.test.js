import test from 'node:test'
import assert from 'node:assert/strict'
import { pickRobot } from '../src/phone/zones.js'

const robots = [{ id: 'R1' }, { id: 'R2' }, { id: 'R3' }]
const room = [[0, 0], [4, 0], [4, 4], [0, 4]]   // centre (2, 2)

test('a new zone goes to the robot with the fewest zones', () => {
  const zones = [{ robot: 'R1' }, { robot: 'R1' }, { robot: 'R2' }]
  assert.equal(pickRobot(zones, robots, [], room), 'R3')
})

test('on a tie, the robot whose last delivered position is nearest wins', () => {
  const zones = [{ robot: 'R1' }, { robot: 'R2' }, { robot: 'R3' }]
  const reported = [{ id: 'R1', pose: [30, 20, 0] }, { id: 'R2', pose: [3, 3, 0] }, { id: 'R3', pose: [12, 2, 0] }]
  assert.equal(pickRobot(zones, robots, reported, room), 'R2')
})

test('robots with no report yet rank after reporting ones on a tie; empty fleet falls back to R1', () => {
  const reported = [{ id: 'R3', pose: [9, 9, 0] }]
  assert.equal(pickRobot([], robots, reported, room), 'R3')
  assert.equal(pickRobot([], [], [], room), 'R1')
})

import { hasPlanContent, refusalText } from '../src/phone/zones.js'
import { NO_GO_HOLD, robotStateLabel } from '../src/format.js'

test('a plan with only no-go areas can be checked and dispatched; an empty one cannot', () => {
  assert.equal(hasPlanContent({ zones: [], no_go: [{ id: 'NG1' }] }), true)
  assert.equal(hasPlanContent({ zones: [{ id: 'Z1' }], no_go: [] }), true)
  assert.equal(hasPlanContent({ zones: [], no_go: [] }), false)
  assert.equal(hasPlanContent(null), false)
})

test('a refusal banner says who refused and why, in the server\'s words', () => {
  assert.equal(refusalText('/api/plan/check', { message: 'Add a search zone before checking or dispatching' }),
    'Check refused: Add a search zone before checking or dispatching')
  assert.equal(refusalText('/api/dispatch', { violations: [{ msg: 'Z1 is in a predicted dead zone' }, { msg: 'R2 battery too low' }] }),
    'Dispatch refused: Z1 is in a predicted dead zone; R2 battery too low')
})

test('a robot holding because a no-go left it nothing reachable reads as obeying, not frozen', () => {
  assert.equal(robotStateLabel({ state: 'WAITING' }), NO_GO_HOLD)
  assert.equal(robotStateLabel({ state: 'EXPLORING', plan_state: 'no reachable area, holding' }), NO_GO_HOLD)
  assert.equal(robotStateLabel({ state: 'WAITING_FOR_LINK' }), 'No link, waiting')   // baseline mode stays itself
  assert.equal(robotStateLabel({ state: 'EXPLORING' }), 'Exploring')
})
