import { useSim, handleMessage } from '../store'

// Backup for the demo: record the big screen's WebSocket stream (?record), then play
// it back through the same store with no server at all (?replay or ?replay=<url>).
const params = new URLSearchParams(location.search)
export const RECORDING = params.has('record')
export const REPLAY = params.has('replay')
export const REPLAY_URL = params.get('replay') || null

// ------------------------------------------------------------------ recording
let frames = []
let t0 = null
let bytes = 0

export function recordFrame(raw) {
  if (!RECORDING) return
  const now = performance.now()
  if (t0 === null) t0 = now
  frames.push([Math.round(now - t0), raw])
  bytes += raw.length
  if (frames.length === 1 || frames.length % 20 === 0) publish()
}

function publish() {
  useSim.getState().set({ recorder: { frames: frames.length, ms: frames.length ? frames[frames.length - 1][0] : 0, bytes } })
}

export async function saveRecording() {
  publish()
  let blob = new Blob([JSON.stringify({ version: 1, recorded_at: new Date().toISOString(), frames })],
                      { type: 'application/json' })
  let name = `deadzone-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.json`
  if ('CompressionStream' in window) { // map frames make raw recordings tens of MB
    blob = await new Response(blob.stream().pipeThrough(new CompressionStream('gzip'))).blob()
    name += '.gz'
  }
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: name })
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 10000)
}

// ------------------------------------------------------------------ replay
export async function loadRecording(source) {
  const res = typeof source === 'string' ? await fetch(source) : new Response(source)
  if (!res.ok) throw new Error(`Could not load ${source} (${res.status})`)
  // Sniff the gzip magic bytes: some servers send .gz with Content-Encoding: gzip, so
  // fetch may already have decompressed it and the file name can't be trusted.
  const buf = new Uint8Array(await res.arrayBuffer())
  let body = new Blob([buf])
  if (buf[0] === 0x1f && buf[1] === 0x8b) {
    body = await new Response(body.stream().pipeThrough(new DecompressionStream('gzip'))).blob()
  }
  const data = JSON.parse(await body.text())
  if (!Array.isArray(data.frames) || !data.frames.length) throw new Error('Not a Deadzone recording')
  return data.frames
}

const player = { frames: [], next: 0, clock: 0, rate: 1, playing: false, last: 0, raf: 0 }

function state() {
  const end = player.frames.length ? player.frames[player.frames.length - 1][0] : 0
  useSim.getState().set({ replay: { loaded: player.frames.length > 0, playing: player.playing,
                                    rate: player.rate, pos: player.clock, dur: end,
                                    ended: player.next >= player.frames.length && player.frames.length > 0 } })
}

function step(now) {
  if (!player.playing) return
  player.clock += (now - player.last) * player.rate
  player.last = now
  while (player.next < player.frames.length && player.frames[player.next][0] <= player.clock) {
    handleMessage(JSON.parse(player.frames[player.next][1]))
    player.next++
  }
  if (player.next >= player.frames.length) player.playing = false
  state()
  if (player.playing) player.raf = requestAnimationFrame(step)
}

export function startReplay(loaded) {
  cancelAnimationFrame(player.raf)
  Object.assign(player, { frames: loaded, next: 0, clock: 0, playing: true, last: performance.now() })
  useSim.getState().set({ connected: true })
  state()
  player.raf = requestAnimationFrame(step)
}

// The big screen's controls drive the player instead of the server in replay mode.
export function replayControl(action, value) {
  if (!player.frames.length) return
  if (action === 'reset') return startReplay(player.frames)
  // +/- send the recorded sim speed doubled or halved; treat that as faster/slower playback
  if (action === 'speed') player.rate = Math.max(0.25, Math.min(8, player.rate * (Number(value) > useSim.getState().speed ? 2 : 0.5)))
  if (action === 'toggle' || action === 'start' || action === 'pause') {
    const play = action === 'toggle' ? !player.playing : action === 'start'
    if (play && player.next >= player.frames.length) return startReplay(player.frames)
    player.playing = play
    if (play) { player.last = performance.now(); player.raf = requestAnimationFrame(step) }
  }
  state()
}
