import test from 'node:test'
import assert from 'node:assert/strict'
import { createFrameSender, captureJpeg } from '../src/net/phoneFrames.js'
import { retainPhoneFrames, lastFrame, isDark } from '../src/phone/control.js'

test('JPEG uploads require advertised capability and fresh delivered Command contact; cap real time and overlap', async () => {
  let now = 0, done, captures = 0
  const calls = []
  const s = { connected: true, phoneFrames: { epoch: 'incident', max_fps: 3 }, time: 10,
    tick: { command: { robots: [{ id: 'R1', last_seen: 10, state: 'EXPLORING' }] } } }
  const sender = createFrameSender({ getState: () => s, clock: () => now,
    capture: () => { captures++; return 'jpeg' },
    fetcher: (path, init) => { calls.push({ path, init }); return new Promise((resolve) => { done = resolve }) } })
  const first = sender.send('R1', {})
  await sender.send('R1', {})
  assert.equal(calls.length, 1)
  assert.deepEqual(JSON.parse(calls[0].init.body), { epoch: 'incident', t: 10, jpeg: 'jpeg' })
  done({ ok: true }); await first
  now = 330; await sender.send('R1', {}); assert.equal(calls.length, 1)
  now = 334; const next = sender.send('R1', {}); done({ ok: true }); await next
  assert.equal(calls.length, 2)
  now = 1000; s.time = 14; await sender.send('R1', {})
  assert.equal(calls.length, 2); assert.equal(captures, 2)
  s.time = 10; s.phoneFrames = null; await sender.send('R1', {}); assert.equal(captures, 2)
  s.phoneFrames = { epoch: 'new', max_fps: 3 }; s.connected = false
  await sender.send('R1', {}); assert.equal(captures, 2)
  sender.close(); assert.equal(calls[1].init.signal.aborted, true)
})

test('a dark phone retains exactly the JPEG already received and ages it; new incident has none', () => {
  const frame = { jpeg: 'old', t: 10, last_seen_s: 0 }
  const prev = { robots: [{ id: 'R1', phone_frame: frame }] }
  const dark = { robots: [{ id: 'R1', stale_s: 8 }] }
  const view = retainPhoneFrames(prev, dark, true, 18)
  assert.equal(lastFrame(view.robots[0], [], 'R1').kind, 'jpeg')
  assert.equal(view.robots[0].phone_frame.last_seen_s, 8)
  assert.equal(isDark(view.robots[0]), true)
  assert.equal(frame.last_seen_s, 0)
  assert.equal(retainPhoneFrames(null, dark, true, 18).robots[0].phone_frame, undefined)
  assert.equal(retainPhoneFrames(prev, dark, false, 18), dark)
  const fresh = { robots: [{ id: 'R1', stale_s: 0, phone_frame: { jpeg: 'new', t: 19 } }] }
  assert.equal(retainPhoneFrames(prev, fresh, true, 19).robots[0].phone_frame.jpeg, 'new')
})

test('canvas capture fits without stretching and emits bounded JPEG base64 only', () => {
  const draws = []
  const ctx = { fillRect() {}, drawImage: (...args) => draws.push(args) }
  const target = { getContext: () => ctx, toDataURL: (format, quality) => {
    assert.equal(format, 'image/jpeg'); assert.equal(quality, .7); return 'data:image/jpeg;base64,aGVsbG8='
  } }
  const source = { width: 800, height: 600 }
  assert.equal(captureJpeg(source, target), 'aGVsbG8=')
  assert.deepEqual([target.width, target.height], [320, 180])
  assert.deepEqual(draws[0].slice(1), [40, 0, 240, 180])
  assert.equal(captureJpeg({ width: 0, height: 0 }, target), null)
})
