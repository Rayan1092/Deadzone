import test from 'node:test'
import assert from 'node:assert/strict'
import { RM_BOUND, TASK_INFO, TASK_ORDER, deadlineTicks, declaredUtilization, frameLoad } from '../src/panels/scheduler.js'

test('plain task names over the server task set, Liu & Layland bound and utilization as in FACTS.md', () => {
  assert.deepEqual(TASK_ORDER.map((n) => TASK_INFO[n].label), ['Lidar scan', 'Plan', 'Radio', 'Map update', 'Thermal', 'Battery'])
  assert.equal(RM_BOUND.toFixed(3), '0.735')
  assert.equal(declaredUtilization().toFixed(3), '0.377')
  // rate monotonic: shorter period, higher priority (lane order)
  const periods = TASK_ORDER.map((n) => TASK_INFO[n].period)
  assert.deepEqual(periods, [...periods].sort((a, b) => a - b))
})

test('deadline ticks fall where jobs are released in the frame that just ended', () => {
  assert.deepEqual(deadlineTicks(10.1, 50), [0, 50, 100])   // frame 10000-10100 ms
  assert.deepEqual(deadlineTicks(10.1, 100), [0, 100])
  assert.deepEqual(deadlineTicks(10.2, 200), [100])          // frame 10100-10200: the 200 ms job is due at its end
  assert.deepEqual(deadlineTicks(10.3, 200), [0])            // frame 10200-10300
  assert.equal(frameLoad([{ dur: 30 }, { dur: 12.5 }]), 0.425)
})
