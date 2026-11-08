import test from 'node:test'
import assert from 'node:assert/strict'
import { deflateSync } from 'node:zlib'
import { MapStreamDecoder, recordableFrame } from '../src/net/mapStream.js'

const compressed = (raw) => deflateSync(raw).toString('base64')
const raw = Uint8Array.from([0, 1, 2, 3, 0, 1])
const keyframe = (epoch = 'one') => ({ t: 'maps', time: 1, data: { w: 3, h: 2, cell: .25,
  epoch, version: 0, encoding: 'zlib-base64', reality: compressed(raw), command: compressed(raw) } })
const change = (entries) => {
  const packed = Buffer.alloc(entries.length * 5)
  entries.forEach(([index, value], i) => { packed.writeUInt32LE(index, i * 5); packed[i * 5 + 4] = value })
  return compressed(packed)
}
const patch = (grids = { command: change([[0, 3], [5, 2]]) }) => ({ t: 'map_patch', time: 2, data: {
  w: 3, h: 2, cell: .25, epoch: 'one', base: 0, version: 1, encoding: 'zlib-base64-u32le-u8', grids } })

test('compressed snapshot and sparse deltas reconstruct the exact grids consumed by the renderer', async () => {
  const decoder = new MapStreamDecoder()
  const first = await decoder.decode(keyframe())
  const next = await decoder.decode(patch())
  assert.equal(next.t, 'maps')
  assert.deepEqual([...next.data.reality], [...raw])
  assert.deepEqual([...next.data.command], [3, 1, 2, 3, 0, 2])
  assert.deepEqual([...first.data.command], [...raw], 'applying a patch must not mutate the displayed previous frame')
  assert.equal(next.data.reality, first.data.reality, 'unchanged grids reuse their buffer')
})

test('gaps, stale epochs, geometry changes, unknown grids and malformed indices reject atomically', async () => {
  const decoder = new MapStreamDecoder()
  await decoder.decode(keyframe())
  for (const data of [
    { ...patch().data, base: 4 }, { ...patch().data, epoch: 'old' },
    { ...patch().data, w: 9 }, { ...patch().data, grids: { truth: change([[0, 1]]) } },
    { ...patch().data, grids: { command: change([[6, 1]]) } },
    { ...patch().data, grids: { command: compressed(Buffer.alloc(4)) } },
  ]) await assert.rejects(decoder.decode({ t: 'map_patch', data }))
  assert.equal(decoder.version, 0)
  assert.deepEqual([...decoder.grids.command], [...raw])
  assert.deepEqual([...(await decoder.decode(patch())).data.command], [3, 1, 2, 3, 0, 2])
})

test('reconnect/reset needs a fresh keyframe, while geometry hello preserves the current baseline', async () => {
  const decoder = new MapStreamDecoder()
  await decoder.decode(keyframe())
  await decoder.decode({ t: 'hello', data: { compact_stream: { epoch: 'one' } } })
  await decoder.decode(patch())
  await decoder.decode({ t: 'hello', data: { compact_stream: { epoch: 'two' } } })
  await assert.rejects(decoder.decode(patch()))
  const fresh = await decoder.decode(keyframe('two'))
  assert.deepEqual([...fresh.data.command], [...raw])
  await assert.rejects(new MapStreamDecoder().decode(patch()))
})

test('ordinary frames remain untouched and compact recordings replay as legacy full maps', async () => {
  const decoder = new MapStreamDecoder()
  const legacy = { t: 'maps', data: { command: Buffer.from(raw).toString('base64') } }
  assert.equal(await decoder.decode(legacy), legacy)
  const first = await decoder.decode(keyframe())
  const wire = recordableFrame(await decoder.decode(patch()))
  const replay = JSON.parse(JSON.stringify(wire))
  assert.deepEqual([...Buffer.from(replay.data.command, 'base64')], [3, 1, 2, 3, 0, 2])
  assert.deepEqual([...first.data.command], [...raw])
})

test('optional belief grids and metadata update losslessly without fabricating missing layers', async () => {
  const decoder = new MapStreamDecoder()
  const full = keyframe()
  full.data.belief = full.data.reality
  full.data.missing = { reality: 2, command: 3 }
  await decoder.decode(full)
  const update = patch({ belief: change([[1, 255]]) })
  update.data.missing = { reality: 1, command: 3 }
  const result = await decoder.decode(update)
  assert.equal(result.data.belief[1], 255)
  assert.equal(result.data.missing.reality, 1)
  assert.ok(!('belief_command' in result.data))
})
