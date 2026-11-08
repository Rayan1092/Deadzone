import test from 'node:test'
import assert from 'node:assert/strict'
import { drainHops, linkKey, linkRate, pushTraffic, resetTraffic, trafficSeen } from '../src/net/traffic.js'

test('no traffic events yet: link rates are unknown, so lines keep their plain look', () => {
  assert.equal(trafficSeen(), false)
  assert.equal(linkRate('R1', 'RL1', 0), null)
})

test('a completed hop becomes one packet and counts toward that link, in both directions', () => {
  pushTraffic({ kind: 'bundle_hop', a: 'R1', b: 'RL1', bundle_kind: 'telemetry', bytes: 200, wire_bytes: 240 }, 1000)
  pushTraffic({ kind: 'bundle_hop', a: 'RL1', b: 'R1', bundle_kind: 'survivor', bytes: 400, wire_bytes: 420 }, 1500)
  pushTraffic({ kind: 'bundle_held', node: 'RL1', reason: 'link_busy' }, 1600)      // a hold is not a hop
  assert.equal(trafficSeen(), true)
  assert.equal(linkKey('RL1', 'R1'), linkKey('R1', 'RL1'))
  assert.equal(linkRate('RL1', 'R1', 2000), (240 + 420) / 3)                         // bytes/s over 3 s
  assert.equal(linkRate('R2', 'CMD', 2000), 0)                                       // idle link: dimmed
  const hops = drainHops()
  assert.deepEqual(hops.map((h) => [h.a, h.b, h.kind]), [['R1', 'RL1', 'telemetry'], ['RL1', 'R1', 'survivor']])
  assert.equal(drainHops().length, 0)                                                // each hop flies once
})

test('old bytes leave the 3 s window, and a reset clears everything', () => {
  assert.equal(linkRate('R1', 'RL1', 4200), 420 / 3)
  assert.equal(linkRate('R1', 'RL1', 9000), 0)
  pushTraffic({ kind: 'bundle_hop', a: 'R1', b: 'CMD', wire_bytes: 90 }, 9100)
  resetTraffic()
  assert.equal(drainHops().length, 0)
  assert.equal(linkRate('R1', 'CMD', 9200), 0)
})
