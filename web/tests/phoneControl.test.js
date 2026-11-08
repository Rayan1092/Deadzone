import test from 'node:test'
import assert from 'node:assert/strict'
import { ackFor, claim, command, holder, isDark, lastFrame } from '../src/phone/control.js'

const leases = { enabled: true, robots: [
  { robot: 'R1', controller: { client: 'phone-a', name: 'phone-a' } },
  { robot: 'R2', controller: { client: 'phone-b', name: 'Sam' } },
  { robot: 'R3', controller: null },
] }

test('one controller per robot: mine, locked by someone else, free, or control off', () => {
  assert.equal(holder(leases, 'R1', 'phone-a'), 'me')
  assert.equal(holder(leases, 'R2', 'phone-a'), 'other')
  assert.equal(holder(leases, 'R3', 'phone-a'), 'free')
  assert.equal(holder({ ...leases, enabled: false }, 'R1', 'phone-a'), 'off')
  assert.equal(holder(null, 'R1', 'phone-a'), 'off')
})

test('lease and command calls carry the controller token and the server error', async () => {
  const calls = []
  const ok = async (path, init) => { calls.push({ path, init }); return { ok: true, json: async () => ({ queued: true, cmd_id: 'V-1' }) } }
  await claim('R3', 'phone-a', 'tok', ok)
  const res = await command('R3', { action: 'hold' }, 'tok', ok)
  assert.equal(calls[0].path, '/api/leases/claim')
  assert.equal(calls[0].init.headers['X-Controller-Token'], 'tok')
  assert.deepEqual(JSON.parse(calls[0].init.body), { robot: 'R3', name: 'phone-a' })
  const body = JSON.parse(calls[1].init.body)
  assert.equal(body.action, 'hold')
  assert.ok(body.request_id)
  assert.equal(res.cmd_id, 'V-1')
  const locked = async () => ({ ok: false, status: 409, json: async () => ({ detail: { code: 'robot_controlled', msg: 'R2 is controlled by Sam' } }) })
  await assert.rejects(claim('R2', 'phone-a', 'tok', locked), (e) => e.code === 'robot_controlled' && /Sam/.test(e.message))
})

test('the camera only shows delivered images: a frame, else the newest delivered crop, else nothing', () => {
  const survivors = [
    { id: 'S1', by: 'R1', crop: 'pos_0001.png', t: 40, reported_t: 60 },
    { id: 'S2', by: 'R1', crop: 'pos_0002.png', t: 90, reported_t: 95 },
    { id: 'S3', by: 'R2', crop: 'pos_0003.png', t: 99, reported_t: 99 },
  ]
  assert.equal(lastFrame({ camera: { t: 120, hits: [{ id: 'S2', pos: [3, 4], verdict: 'unsure', conf: 0.58 }] } }, survivors, 'R1').kind, 'frame')
  const f = lastFrame({ stale_s: 0 }, survivors, 'R1')
  assert.equal(f.kind, 'crop')
  assert.equal(f.crop.id, 'S2')
  assert.equal(f.t, 90)
  assert.equal(lastFrame({ stale_s: 0 }, survivors, 'R3'), null)
})

test('out of contact once the last report is older than 3 s; acks only once delivered', () => {
  assert.equal(isDark({ stale_s: 1 }), false)
  assert.equal(isDark({ stale_s: 12 }), true)
  assert.equal(isDark(null), true)
  const view = { command_acks: [{ cmd_id: 'V-1', status: 'accepted', say: 'Holding' }] }
  assert.equal(ackFor(view, 'V-1').status, 'accepted')
  assert.equal(ackFor(view, 'V-2'), null)
  assert.equal(ackFor({}, 'V-1'), null)
})
