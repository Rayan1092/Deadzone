import test, { before, after, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { connectionLabel, probeServer, publicText, regionName } from './labels.js'

let vite, phone, transport, seed, sockets, previousLocation, previousSocket
before(async () => {
  previousLocation = globalThis.location
  previousSocket = globalThis.WebSocket
  globalThis.location = { href: 'http://localhost:8000/phone', search: '', protocol: 'http:', host: 'localhost:8000' }
  globalThis.WebSocket = class {
    readyState = 1
    constructor(url) { this.url = url; sockets.push(this) }
    close() { this.readyState = 3; this.onclose?.() }
    send() {}
  }
  vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  phone = await vite.ssrLoadModule('/src/phone/store.js')
  transport = await vite.ssrLoadModule('/src/phone/socket.js')
  seed = { ...phone.usePhone.getState() }
})
beforeEach(() => { sockets = []; phone.usePhone.setState({ ...seed, pending: false }) })
after(async () => {
  globalThis.location = previousLocation
  globalThis.WebSocket = previousSocket
  await vite?.close()
})
const hello = () => sockets.at(-1).onmessage({ data: JSON.stringify({ t: 'hello', time: 0, data: {
  client: 'phone-1', role: 'planner', plan_epoch: 'a', plan: null, robots: [],
} }) })

test('connection states distinguish initial join, reconnection and an unreachable server', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const stop = transport.connectPhone('planner')
  try {
    assert.equal(phone.usePhone.getState().connection, 'connecting')
    hello()
    assert.equal(phone.usePhone.getState().connection, 'live')
    sockets.at(-1).close()
    assert.equal(phone.usePhone.getState().connection, 'reconnecting')
    for (let i = 0; i < 2; i++) { t.mock.timers.tick(1000); sockets.at(-1).close() }
    assert.equal(phone.usePhone.getState().connection, 'unreachable')
    t.mock.timers.tick(1000)
    hello()
    assert.equal(phone.usePhone.getState().connected, true)
    assert.equal(connectionLabel(phone.usePhone.getState().connection), 'Connected')
  } finally { stop() }
})

test('a socket that never supplies hello times out; a stopped session cannot reconnect itself', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const stop = transport.connectPhone('planner')
  const first = sockets[0]
  t.mock.timers.tick(8000)
  assert.equal(phone.usePhone.getState().connection, 'unreachable')
  stop()
  first.onmessage({ data: JSON.stringify({ t: 'hello', data: {} }) })
  t.mock.timers.tick(10000)
  assert.equal(sockets.length, 1)
  assert.equal(phone.usePhone.getState().connected, false)
})

test('relay confirmations wait for matching server state, never a local toggle alone', () => {
  phone.usePhone.setState({ relayAction: { kind: 'power', on: false }, relayPending: false })
  phone.handlePhoneMessage({ t: 'relay_state', data: { on: true, pos: [1, 2] } })
  assert.equal(phone.usePhone.getState().notice, null)
  phone.handlePhoneMessage({ t: 'relay_state', data: { on: false, pos: [1, 2] } })
  assert.equal(phone.usePhone.getState().notice.msg, 'Relay turned off.')
  phone.usePhone.setState({ notice: null, relayAction: { kind: 'place', pos: [3, 4] } })
  phone.handlePhoneMessage({ t: 'relay_state', data: { on: false, pos: [1, 2] } })
  assert.equal(phone.usePhone.getState().notice, null)
  phone.handlePhoneMessage({ t: 'relay_state', data: { on: false, pos: [3, 4] } })
  assert.equal(phone.usePhone.getState().notice.msg, 'Relay moved.')
})

test('display copy uses complete names without replacing identifier prefixes', () => {
  const data = { robots: [{ id: 'R1', name: 'Scout 1' }, { id: 'R10', name: 'Scout 10' }] }
  const draft = { zones: [{ id: 'ZNE' }], no_go: [{ id: 'NG1' }] }
  assert.equal(regionName('NG1', draft), 'No-go area 1')
  assert.equal(publicText('R10 cannot reach ZNE. R1 is waiting.', data, draft), 'Scout 10 cannot reach Search area 1. Scout 1 is waiting.')
  assert.doesNotMatch(publicText('Enable DZ_VOICE=1'), /DZ_|VOICE/)
  assert.doesNotMatch(publicText('phone-abc controls R1'), /phone-|R1/)
})

test('Join checks real health and handles unavailable or malformed responses', async () => {
  assert.equal(await probeServer(null, async (path, options) => {
    assert.equal(path, '/api/health'); assert.equal(options.cache, 'no-store')
    return { ok: true, json: async () => ({ ok: true }) }
  }), true)
  assert.equal(await probeServer(null, async () => ({ ok: false })), false)
  assert.equal(await probeServer(null, async () => { throw new Error('offline') }), false)
  assert.equal(await probeServer(null, async () => ({ ok: true, json: async () => ({}) })), false)
})
