// Verify captured compact frames with the actual browser decoder against legacy output.
// Usage: node scripts/check_map_stream.mjs legacy.jsonl compact.jsonl
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { MapStreamDecoder, recordableFrame } from '../web/src/net/mapStream.js'

const read = (path) => readFileSync(path, 'utf8').trim().split('\n').map(JSON.parse)
const legacy = read(process.argv[2])
const compact = read(process.argv[3])
const decoder = new MapStreamDecoder()
const states = []
const ticks = new Map()
for (const frame of compact) {
  const decoded = await decoder.decode(frame)
  if (decoded.t === 'maps') {
    states.push({ at: Math.round(frame.time * 10), grids: decoded.data })
    const replay = recordableFrame(decoded)
    for (const key of ['reality', 'command']) {
      assert.deepEqual(Buffer.from(replay.data[key], 'base64'), Buffer.from(decoded.data[key]))
    }
  }
  if (frame.t === 'tick') ticks.set(Math.round(frame.time * 10), frame.data.reality.robots)
}
let current = null, next = 0, mapChecks = 0, lidarChecks = 0
const geometry = (robots) => robots.map(({ id, pose, lidar }) => ({ id, pose, lidar }))
for (const frame of legacy) {
  const at = Math.round(frame.time * 10)
  if (frame.t === 'maps') {
    while (next < states.length && states[next].at <= at) current = states[next++].grids
    assert.ok(current, 'a keyframe must precede deltas')
    for (const key of ['reality', 'command']) {
      assert.deepEqual(Buffer.from(current[key]), Buffer.from(frame.data[key], 'base64'), `${key} at ${frame.time}`)
      mapChecks++
    }
  }
  if (frame.t === 'tick' && ticks.has(at)) {
    assert.deepEqual(geometry(ticks.get(at)), geometry(frame.data.reality.robots), `lidar fan at ${frame.time}`)
    lidarChecks++
  }
}
assert.ok(mapChecks >= 400 && lidarChecks >= 1000, 'compare a full 60-second capture')
console.log(JSON.stringify({ map_grid_checks: mapChecks, identical_lidar_pose_ticks: lidarChecks,
  compact_map_frames: states.length, replay_round_trips: states.length * 2 }, null, 2))
