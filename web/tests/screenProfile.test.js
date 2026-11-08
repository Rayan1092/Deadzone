import test from 'node:test'
import assert from 'node:assert/strict'
import { screenPath } from '../src/net/screenProfile.js'

test('local screens retain full rate; public HTTPS viewers select lite', () => {
  for (const hostname of ['localhost', '127.0.0.1', '[::1]', '10.84.1.2', '192.168.0.2', '172.20.1.2']) {
    assert.equal(screenPath({ hostname, protocol: 'https:', search: '' }), '/ws/screen?map_deltas=1')
  }
  assert.equal(screenPath({ hostname: 'demo.trycloudflare.com', protocol: 'https:', search: '' }), '/ws/screen?map_deltas=1&lite=1')
  assert.equal(screenPath({ hostname: 'demo.example.com', protocol: 'https:', search: '?lite=0' }), '/ws/screen?map_deltas=1')
})

test('explicit lite and older decompression support work independently', () => {
  const local = { hostname: 'localhost', protocol: 'http:', search: '?lite' }
  assert.equal(screenPath(local, false), '/ws/screen?lite=1')
  assert.equal(screenPath({ ...local, search: '' }, false), '/ws/screen')
  assert.equal(screenPath({ ...local, search: '?lite=false' }), '/ws/screen?map_deltas=1')
})
