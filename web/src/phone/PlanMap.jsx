import { useEffect, useRef } from 'react'
import { usePhone } from './store'
import { MIN_SIDE, addRegion, pointInPoly, rectPoly, snap } from './plan'
import { sendPhone } from './socket'

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
  const drawing = usePhone((s) => s.mode !== 'view')

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

      // search plan: responder no-go areas, then zones in their robot's color
      const { draft, selected, safety } = usePhone.getState()
      const flagged = new Set(safety && !safety.ok && safety.plan_id === draft?.plan_id
        ? safety.violations.map((v) => v.zone) : [])
      const pulse = 0.5 + 0.5 * Math.sin(t * 6)
      for (const ng of draft?.no_go ?? []) {
        poly(ng.poly)
        ctx.fillStyle = hatch
        ctx.fill()
        ctx.setLineDash([4, 3])
        ctx.strokeStyle = ng.id === selected ? '#fecaca' : 'rgba(239,68,68,.9)'
        ctx.lineWidth = ng.id === selected ? 2.5 : 1.5
        ctx.stroke()
        ctx.setLineDash([])
      }
      for (const z of draft?.zones ?? []) {
        const color = colors[z.robot] ?? C.teal
        poly(z.poly)
        ctx.globalAlpha = 0.2
        ctx.fillStyle = color
        ctx.fill()
        ctx.globalAlpha = 1
        ctx.strokeStyle = flagged.has(z.id) ? `rgba(239,68,68,${0.5 + 0.5 * pulse})` : z.id === selected ? '#ffffff' : color
        ctx.lineWidth = flagged.has(z.id) ? 3 : z.id === selected ? 2.5 : 1.5
        ctx.stroke()
      }
      if (drag) {
        const [a, b] = [drag.a, drag.b]
        poly([[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]]])
        ctx.setLineDash([5, 4])
        ctx.strokeStyle = drag.kind === 'nogo' ? C.red : '#ffffff'
        ctx.lineWidth = 2
        ctx.stroke()
        ctx.setLineDash([])
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

      for (const r of [...(draft?.zones ?? []), ...(draft?.no_go ?? [])]) {
        const xs = r.poly.map((p) => p[0])
        const ys = r.poly.map((p) => p[1])
        const text = r.robot ? `${r.id} · ${r.robot}` : r.id
        label(text, X((Math.min(...xs) + Math.max(...xs)) / 2), Y(Math.max(...ys)) + 9,
              r.robot ? '#ffffff' : '#fecaca', 10, 700)
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

      // rescue routes Command has received (entrance → survivor), with the beacon relay if any
      for (const route of view?.routes ?? []) {
        ctx.beginPath()
        route.path.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))))
        ctx.setLineDash([6, 4])
        ctx.strokeStyle = '#facc15'
        ctx.lineWidth = 3
        ctx.stroke()
        ctx.setLineDash([])
        const [ex2, ey2] = route.path[route.path.length - 1]
        label(`Route to ${route.survivor} · ${route.length_m.toFixed(1)} m`, X(ex2), Y(ey2) + r0 + 18, '#fef08a', 10, 700)
        const beacon = route.beacon && (view?.relays ?? []).find((r) => r.id === route.beacon)
        if (beacon) {
          ctx.strokeStyle = '#facc15'
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.arc(X(beacon.pos[0]), Y(beacon.pos[1]), r0 * 1.6, 0, Math.PI * 2)
          ctx.stroke()
        }
      }

      // this phone's own relay (relay role): its own state, not Command knowledge
      const mine = usePhone.getState().relay
      if (mine) {
        const [x, y] = mine.pos
        const k = (t * 0.8) % 1
        if (mine.on) {
          ctx.strokeStyle = `rgba(45,212,191,${0.8 * (1 - k)})`
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.arc(X(x), Y(y), r0 * (1.2 + k * 2.2), 0, Math.PI * 2)
          ctx.stroke()
        }
        ctx.fillStyle = mine.on ? C.teal : C.ghost
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.arc(X(x), Y(y), r0 * 0.9, 0, Math.PI * 2)
        ctx.fill()
        ctx.stroke()
        label(`You · ${mine.id}${mine.on ? '' : ' off'}`, X(x), Y(y) + r0 + 9, mine.on ? C.teal : C.ghost, 10, 700)
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

    // ---------------------------------------------------------------- touch
    // Drawing mode: drag a snapped rectangle. View mode: tap a zone to edit it.
    const toWorld = (e) => {
      const r = el.getBoundingClientRect()
      return [(e.clientX - r.left) / s - PAD.left, H + PAD.top - (e.clientY - r.top) / s]
    }
    const clampSnap = ([x, y]) => [snap(Math.min(W, Math.max(0, x))), snap(Math.min(H, Math.max(0, y)))]
    let drag = null
    let down = null
    const onDown = (e) => {
      const { mode } = usePhone.getState()
      down = toWorld(e)
      if (mode === 'view' || mode === 'place') return
      el.setPointerCapture(e.pointerId)
      drag = { kind: mode, a: clampSnap(down), b: clampSnap(down) }
      dirty = true
    }
    const onMove = (e) => {
      if (!drag) return
      drag.b = clampSnap(toWorld(e))
      dirty = true
    }
    const onUp = (e) => {
      const st = usePhone.getState()
      if (drag) {
        const { kind, a, b } = drag
        drag = null
        dirty = true
        if (Math.abs(b[0] - a[0]) >= MIN_SIDE && Math.abs(b[1] - a[1]) >= MIN_SIDE) {
          addRegion(kind === 'nogo' ? 'nogo' : 'zone', rectPoly(a, b))
        }
        return
      }
      const p = toWorld(e)
      if (!down || Math.hypot(p[0] - down[0], p[1] - down[1]) > 0.5) return // a scroll, not a tap
      if (st.mode === 'place') {
        // the server rejects walls, hazards and outside positions with invalid_relay_position
        sendPhone('relay_place', { pos: [Math.min(W - 0.1, Math.max(0.1, p[0])), Math.min(H - 0.1, Math.max(0.1, p[1]))] })
        st.set({ mode: 'view' })
        return
      }
      const regions = [...(st.draft?.zones ?? []), ...(st.draft?.no_go ?? [])].reverse()
      st.set({ selected: regions.find((r) => pointInPoly(p, r.poly))?.id ?? null })
    }
    el.addEventListener('pointerdown', onDown)
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerup', onUp)
    el.addEventListener('pointercancel', () => { drag = null; dirty = true })

    const frame = (ms) => {
      const st = usePhone.getState()
      // Survivor pulses and flagged zones animate; otherwise redraw when new data arrives.
      const flaggedZones = st.safety && !st.safety.ok
      const animating = (st.view?.survivors?.length ?? 0) > 0 || flaggedZones || st.relay?.on
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
    <div ref={wrap} className={`plan-map${drawing ? ' drawing' : ''}`}>
      <canvas ref={canvas} />
      {!fp && <div className="map-empty">Connecting to the command post…</div>}
    </div>
  )
}
