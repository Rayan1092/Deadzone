// Sound cues for the big screen. Browsers only play audio after a user gesture, so the
// context is created lazily on the first call; a cue that arrives before any gesture is
// skipped (no error, no retry). Everything is synthesized: no files to load.

// X turns every cue on or off; the choice is kept per browser.
let on = true
try { on = localStorage.getItem('dz-sound') !== '0' } catch { /* storage blocked: sound stays on */ }
export const soundOn = () => on
export function setSound(value) {
  on = value
  try { localStorage.setItem('dz-sound', value ? '1' : '0') } catch { /* not remembered */ }
}

let ctx = null
function context() {
  if (!soundOn()) return null
  try {
    ctx ??= new (window.AudioContext || window.webkitAudioContext)()
    if (ctx.state === 'suspended') ctx.resume().catch(() => {})
    return ctx.state === 'running' || ctx.state === 'suspended' ? ctx : null
  } catch { return null }
}

let brown = null
function brownNoise(ac) {
  if (brown) return brown
  const seconds = 6
  const buf = ac.createBuffer(1, ac.sampleRate * seconds, ac.sampleRate)
  const d = buf.getChannelData(0)
  let last = 0
  for (let i = 0; i < d.length; i++) {
    const white = Math.random() * 2 - 1
    last = (last + 0.02 * white) / 1.02
    d[i] = last * 3.5
  }
  brown = buf
  return buf
}

// Earthquake: a sub-bass thud, then a low rumble that swells and dies over `seconds`.
export function rumble(seconds = 5) {
  const ac = context()
  if (!ac) return
  const t0 = ac.currentTime
  const master = ac.createGain()
  master.gain.value = 0.9
  master.connect(ac.destination)

  const src = ac.createBufferSource()
  src.buffer = brownNoise(ac)
  const low = ac.createBiquadFilter()
  low.type = 'lowpass'
  low.frequency.setValueAtTime(140, t0)
  low.frequency.linearRampToValueAtTime(70, t0 + seconds)
  const env = ac.createGain()
  env.gain.setValueAtTime(0.0001, t0)
  env.gain.exponentialRampToValueAtTime(0.8, t0 + 0.35)
  env.gain.setValueAtTime(0.8, t0 + seconds * 0.45)
  env.gain.exponentialRampToValueAtTime(0.0001, t0 + seconds)
  src.connect(low).connect(env).connect(master)
  src.start(t0)
  src.stop(t0 + seconds + 0.1)

  const thud = ac.createOscillator()
  thud.type = 'sine'
  thud.frequency.setValueAtTime(48, t0)
  thud.frequency.exponentialRampToValueAtTime(28, t0 + 0.5)
  const tg = ac.createGain()
  tg.gain.setValueAtTime(0.0001, t0)
  tg.gain.exponentialRampToValueAtTime(0.9, t0 + 0.04)
  tg.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.7)
  thud.connect(tg).connect(master)
  thud.start(t0)
  thud.stop(t0 + 0.8)
}

// Short tonal cues, one per kind of news. Each note: [frequency Hz, start s, length s].
// A cue that fires again within its gap is dropped, so a burst of events plays once.
const lastPlayed = {}
function cue(name, gapMs, notes, { type = 'sine', gain = 0.2, lowpass = 0 } = {}) {
  const now = performance.now()
  if (now - (lastPlayed[name] ?? -Infinity) < gapMs) return
  const ac = context()
  if (!ac) return
  lastPlayed[name] = now
  const t0 = ac.currentTime + 0.01
  const out = ac.createGain()
  out.gain.value = gain
  let tail = out
  if (lowpass) {
    const f = ac.createBiquadFilter()
    f.type = 'lowpass'
    f.frequency.value = lowpass
    out.connect(f)
    tail = f
  }
  tail.connect(ac.destination)
  for (const [freq, start, len] of notes) {
    const osc = ac.createOscillator()
    osc.type = type
    osc.frequency.value = freq
    const env = ac.createGain()
    env.gain.setValueAtTime(0.0001, t0 + start)
    env.gain.exponentialRampToValueAtTime(1, t0 + start + 0.012)
    env.gain.exponentialRampToValueAtTime(0.0001, t0 + start + len)
    osc.connect(env).connect(out)
    osc.start(t0 + start)
    osc.stop(t0 + start + len + 0.05)
  }
}

// A robot found someone: two soft rising notes.
export const ping = () => cue('ping', 800, [[880, 0, 0.22], [1318.5, 0.11, 0.42]])
// The report reached the command post: a brighter three-note confirm.
export const confirm = () => cue('confirm', 800, [[784, 0, 0.18], [987.8, 0.1, 0.18], [1568, 0.2, 0.5]], { type: 'triangle', gain: 0.22 })
// A robot faulted: two low, muffled buzzes.
export const alarm = () => cue('alarm', 3000, [[392, 0, 0.16], [392, 0.24, 0.16]], { type: 'square', gain: 0.1, lowpass: 1400 })
// A robot's link came back: a quick rising arpeggio, quieter than the news cues.
export const chime = () => cue('chime', 5000, [[659.3, 0, 0.14], [880, 0.07, 0.14], [1174.7, 0.14, 0.3]], { type: 'triangle', gain: 0.12 })
