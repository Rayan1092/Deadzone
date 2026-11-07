import { useEffect, useRef } from 'react'
import { usePhone } from './store'

// 2D plan of the building: the pre-collapse prior plus delivered Command knowledge.
// Margins in meters; the CMD antenna sits outside the west wall at x = -2.
const PAD = { left: 3.5, right: 0.6, top: 0.6, bottom: 0.6 }
const WALL_W = { concrete: 0.3, brick: 0.2, metal: 0.14, drywall: 0.1 }
const C = {
  floor: '#1b2024', wall: '#6b7580', metal: '#8b96a3', room: 'rgba(139,152,165,.8)',
  teal: '#2dd4bf', amber: '#f59e0b', red: '#ef4444', green: '#22c55e', ghost: '#94a3b8',
  halo: 'rgba(20,23,26,.9)',
}
const GHOST_AFTER_S = 3 // same rule as the big screen's ghost robots

// Command occupancy grid as a small offscreen image (row 0 is the south edge).
function gridImage(map, grid) {
  const c = document.createElement('canvas')
  c.width = grid.w
  c.height = grid.h
  const ctx = c.getContext('2d')
  const img = ctx.createImageData(grid.w, grid.h)
  for (let iy = 0; iy < grid.h; iy++) {
    for (let ix = 0; ix < grid.w; ix++) {
      const v = map[iy * grid.w + ix]
      const o = ((grid.h - 1 - iy) * grid.w + ix) * 4
      if (v === 1) img.data.set([45, 212, 191, 64], o)
      else if (v === 2) img.data.set([180, 255, 245, 230], o)
    }
  }
  ctx.putImageData(img, 0, 0)
  return c
}

function hatchPattern(ctx) {
  const c = document.createElement('canvas')
  c.width = c.height = 8
  const p = c.getContext('2d')
  p.strokeStyle = 'rgba(239,68,68,.55)'
  p.lineWidth = 1.5
  p.beginPath()
  p.moveTo(0, 8); p.lineTo(8, 0)
  p.moveTo(-2, 2); p.lineTo(2, -2)
  p.moveTo(6, 10); p.lineTo(10, 6)
  p.stroke()
  return ctx.createPattern(c, 'repeat')
}

export default function PlanMap() {
  const wrap = useRef()
  const canvas = useRef()
  const fp = usePhone((s) => s.hello?.floorplan)

  useEffect(() => {
    if (!fp) return
    const el = canvas.current
    const ctx = el.getContext('2d')
    const [W, H] = fp.size
    const spanX = W + PAD.left + PAD.right
    const spanY = H + PAD.top + PAD.bottom
    let s = 1
    let raf = 0
    let dirty = true
    let img = null
    let imgVersion = -1
    let hatch = null

    const X = (x) => (x + PAD.left) * s
    const Y = (y) => (H + PAD.top - y) * s

    const resize = () => {
      const cssW = wrap.current.clientWidth
      s = cssW / spanX
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      el.style.width = `${cssW}px`
      el.style.height = `${spanY * s}px`
      el.width = Math.round(cssW * dpr)
      el.height = Math.round(spanY * s * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      hatch = hatchPattern(ctx)
      dirty = true
    }

    const label = (text, x, y, color, size = 11, weight = 600) => {
      ctx.font = `${weight} ${size}px Inter, system-ui, sans-serif`
      ctx.lineJoin = 'round'
      ctx.lineWidth = 3
      ctx.strokeStyle = C.halo
      ctx.strokeText(text, x, y)
      ctx.fillStyle = color
      ctx.fillText(text, x, y)
    }

    const poly = (pts) => {
      ctx.beginPath()
      pts.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))))
      ctx.closePath()
    }

    const draw = (t) => {
      const { hello, view, map, mapVersion } = usePhone.getState()
      const grid = hello?.grid
      const colors = Object.fromEntries((hello?.robots ?? []).map((r) => [r.id, r.color]))
      ctx.clearRect(0, 0, spanX * s, spanY * s)
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'

      ctx.fillStyle = C.floor
      ctx.fillRect(X(0), Y(H), W * s, H * s)

      if (map && grid) {
        if (imgVersion !== mapVersion) { img = gridImage(map, grid); imgVersion = mapVersion }
        ctx.imageSmoothingEnabled = false
        ctx.drawImage(img, X(0), Y(grid.h * grid.cell), grid.w * grid.cell * s, grid.h * grid.cell * s)
      }

      for (const hz of fp.hazards ?? []) {
        poly(hz.poly)
        ctx.fillStyle = hatch
        ctx.fill()
        ctx.strokeStyle = 'rgba(239,68,68,.7)'
        ctx.lineWidth = 1
        ctx.stroke()
      }

      ctx.lineCap = 'square'
      for (const w of fp.walls) {
        ctx.strokeStyle = w.material === 'metal' ? C.metal : C.wall
        ctx.lineWidth = Math.max(1.5, (WALL_W[w.material] ?? 0.2) * s)
        ctx.beginPath()
        ctx.moveTo(X(w.a[0]), Y(w.a[1]))
        ctx.lineTo(X(w.b[0]), Y(w.b[1]))
        ctx.stroke()
      }

      const roomSize = Math.max(8, Math.min(12, s * 0.6))
      ctx.font = `500 ${roomSize}px Inter, system-ui, sans-serif`
      for (const room of fp.rooms ?? []) {
        const xs = room.poly.map((p) => p[0])
        const ys = room.poly.map((p) => p[1])
        const cx = (Math.min(...xs) + Math.max(...xs)) / 2
        const cy = (Math.min(...ys) + Math.max(...ys)) / 2
        const roomW = (Math.max(...xs) - Math.min(...xs)) * s - 6
        // wrap names that don't fit the room onto two lines
        const words = room.name.split(' ')
        const lines = ctx.measureText(room.name).width > roomW && words.length > 1
          ? [words.slice(0, Math.ceil(words.length / 2)).join(' '), words.slice(Math.ceil(words.length / 2)).join(' ')]
          : [room.name]
        lines.forEach((line, i) => {
          label(line, X(cx), Y(cy) + (i - (lines.length - 1) / 2) * roomSize * 1.2, C.room, roomSize, 500)
        })
      }

      const [ex, ey] = fp.entry
      const [cx, cy] = fp.command_post.pos
      label('Entry', X(ex) + 2, Y(ey) - 0.9 * s, C.green, 10)
      ctx.fillStyle = C.amber
      ctx.beginPath()
      ctx.arc(X(cx), Y(cy), Math.max(4, 0.35 * s), 0, Math.PI * 2)
      ctx.fill()
      label('CMD', X(cx), Y(cy) - Math.max(10, 0.9 * s), C.amber, 10)

      const r0 = Math.max(5, 0.42 * s)
      for (const relay of view?.relays ?? []) {
        const [x, y] = relay.pos
        ctx.save()
        ctx.translate(X(x), Y(y))
        ctx.rotate(Math.PI / 4)
        ctx.fillStyle = C.amber
        ctx.strokeStyle = C.halo
        ctx.lineWidth = 2
        ctx.fillRect(-r0 * 0.7, -r0 * 0.7, r0 * 1.4, r0 * 1.4)
        ctx.strokeRect(-r0 * 0.7, -r0 * 0.7, r0 * 1.4, r0 * 1.4)
        ctx.restore()
        label(relay.id, X(x), Y(y) + r0 + 7, C.amber, 9)
      }

      for (const sv of view?.survivors ?? []) {
        const [x, y] = sv.pos
        const k = (t * 0.9) % 1
        ctx.strokeStyle = `rgba(239,68,68,${0.8 * (1 - k)})`
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.arc(X(x), Y(y), r0 * (1 + k * 1.8), 0, Math.PI * 2)
        ctx.stroke()
        ctx.fillStyle = C.red
        ctx.beginPath()
        ctx.arc(X(x), Y(y), r0 * 0.75, 0, Math.PI * 2)
        ctx.fill()
        label(sv.id, X(x), Y(y) - r0 - 8, '#fecaca', 10)
      }

      for (const r of view?.robots ?? []) {
        const [x, y, th] = r.pose
        const ghost = r.stale_s > GHOST_AFTER_S
        const color = ghost ? C.ghost : colors[r.id] ?? C.teal
        const px = X(x)
        const py = Y(y)
        ctx.globalAlpha = ghost ? 0.6 : 1
        ctx.fillStyle = color
        ctx.beginPath()
        ctx.arc(px, py, r0, 0, Math.PI * 2)
        ctx.fill()
        ctx.setLineDash(ghost ? [3, 3] : [])
        ctx.strokeStyle = ghost ? '#e5e7eb' : C.halo
        ctx.lineWidth = 2
        ctx.stroke()
        ctx.setLineDash([])
        ctx.strokeStyle = C.halo
        ctx.beginPath()
        ctx.moveTo(px, py)
        ctx.lineTo(px + Math.cos(th) * r0 * 1.7, py - Math.sin(th) * r0 * 1.7)
        ctx.stroke()
        ctx.globalAlpha = 1
        label(ghost ? `${r.id} · ${Math.round(r.stale_s)}s ago` : r.id, px, py - r0 - 8,
              ghost ? C.ghost : '#e6edf3', 10)
      }
    }

    const frame = (ms) => {
      const st = usePhone.getState()
      // Only survivor pulses animate; otherwise redraw when new data arrives.
      const animating = (st.view?.survivors?.length ?? 0) > 0
      if (dirty || animating) {
        draw(ms / 1000)
        dirty = false
      }
      raf = requestAnimationFrame(frame)
    }
    const unsub = usePhone.subscribe(() => { dirty = true })
    const ro = new ResizeObserver(resize)
    ro.observe(wrap.current)
    resize()
    raf = requestAnimationFrame(frame)
    return () => { cancelAnimationFrame(raf); ro.disconnect(); unsub() }
  }, [fp])

  return (
    <div ref={wrap} className="plan-map">
      <canvas ref={canvas} />
      {!fp && <div className="map-empty">Connecting to the command post…</div>}
    </div>
  )
}
