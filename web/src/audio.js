// Sound cues for the big screen. Browsers only play audio after a user gesture, so the
// context is created lazily on the first call; a cue that arrives before any gesture is
// skipped (no error, no retry). Everything is synthesized: no files to load.
let ctx = null
function context() {
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
