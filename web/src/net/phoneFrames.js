// JPEG relay from the already-rendered robot-eye canvas. No extra scene/canvas renders.
export function captureJpeg(source, target) {
  const ctx = target.getContext('2d')
  if (!ctx || !source.width || !source.height) return null
  target.width = 320; target.height = 180
  const scale = Math.min(320 / source.width, 180 / source.height)
  const w = source.width * scale, h = source.height * scale
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, 320, 180)
  ctx.drawImage(source, (320 - w) / 2, (180 - h) / 2, w, h)
  const url = target.toDataURL('image/jpeg', 0.7)
  return url.startsWith('data:image/jpeg;base64,') ? url.slice(23) : null
}

export function createFrameSender({ getState, capture, fetcher = fetch, clock = () => performance.now() }) {
  let last = -Infinity, pending = false, closed = false, controller = null
  return {
    async send(robot, source) {
      const s = getState(), caps = s.phoneFrames
      const report = s.tick?.command?.robots.find((r) => r.id === robot)
      if (closed || pending || !s.connected || !caps || !report || report.state === 'SHUTDOWN' ||
          s.time - report.last_seen > 3 || s.time < report.last_seen || clock() - last < 1000 / Math.min(3, caps.max_fps)) return
      last = clock(); pending = true
      controller = new AbortController()
      try {
        const jpeg = capture(source)
        if (!jpeg) return
        await fetcher(`/api/frames/${encodeURIComponent(robot)}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
          body: JSON.stringify({ epoch: caps.epoch, t: s.time, jpeg }),
        })
      } catch { /* next camera tick retries; never interrupt the renderer */ }
      finally { pending = false }
    },
    close() { closed = true; controller?.abort() },
  }
}
