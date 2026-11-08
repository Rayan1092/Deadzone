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
