// Where the next aftershock lands (keys A and Shift+A). Without a point the server always
// drops the collapse on the first working relay, so every test hit the same spot. Each press
// here draws a fresh random spot: next to a random working relay (that relay is the one
// crushed), or anywhere on open floor before any relay is out. A spot is only sent if it
// keeps clear of survivors, robots and the entrance and cuts nobody off: a flood fill over
// the grid the robot planner drives on (walls and rubble grown by one cell, no-go zones
// blocked) must still reach every survivor and robot it reached before. Truth data on
// purpose: the director plays the disaster, robots still only learn of it through sensors.
// The draw happens here, not in the sim, so a given seed still replays the same way.

const RUBBLE_HALF = 1   // the server's collapse: a 2 x 2 m rubble block centred on the point...
const WALL_HALF = 1.5   // ...and a 3 m fallen wall along its north edge
const STRICT = { survivor: 2.5, entry: 3, robot: 1.8, previous: 3 }
const LOOSE = { survivor: 2.5, entry: 3, robot: 0, previous: 0 }
const RELAY_TRIES = 12
const FLOOR_TRIES = 48
const N8 = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]

function rasterSegment(g, a, b) {
  const n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / (g.cell / 4)) + 1
  for (let i = 0; i < n; i++) {
    const t = n > 1 ? i / (n - 1) : 0
    const ix = Math.min(g.w - 1, Math.max(0, Math.floor((a[0] + (b[0] - a[0]) * t) / g.cell)))
    const iy = Math.min(g.h - 1, Math.max(0, Math.floor((a[1] + (b[1] - a[1]) * t) / g.cell)))
    g.occ[iy * g.w + ix] = 1
  }
}

function inPoly(x, y, poly) {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i]
    const [xj, yj] = poly[j]
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

function fillPoly(g, mask, poly) {
  const xs = poly.map((p) => p[0])
  const ys = poly.map((p) => p[1])
  for (let iy = Math.max(0, Math.floor(Math.min(...ys) / g.cell)); iy <= Math.min(g.h - 1, Math.floor(Math.max(...ys) / g.cell)); iy++)
    for (let ix = Math.max(0, Math.floor(Math.min(...xs) / g.cell)); ix <= Math.min(g.w - 1, Math.floor(Math.max(...xs) / g.cell)); ix++)
      if (inPoly((ix + 0.5) * g.cell, (iy + 0.5) * g.cell, poly)) mask[iy * g.w + ix] = 1
}

// Truth occupancy and no-go cells, rasterized like the server's FloorPlan.
function truthGrid(fp) {
  const [W, H] = fp.size
  const cell = fp.cell ?? 0.25
  const g = { W, H, cell, w: Math.round(W / cell), h: Math.round(H / cell) }
  g.occ = new Uint8Array(g.w * g.h)
  g.nogo = new Uint8Array(g.w * g.h)
  for (const wl of [...fp.walls, ...(fp.dynamic_walls ?? [])]) rasterSegment(g, wl.a, wl.b)
  for (const rb of fp.rubble ?? []) fillPoly(g, g.occ, rb.poly)
  for (const hz of fp.hazards ?? []) fillPoly(g, g.nogo, hz.poly)
  return g
}

function traversable(g, occ) {
  const ok = new Uint8Array(g.w * g.h)
  for (let y = 0; y < g.h; y++)
    for (let x = 0; x < g.w; x++) {
      if (g.nogo[y * g.w + x]) continue
      let free = 1
      for (let dy = -1; dy <= 1 && free; dy++)
        for (let dx = -1; dx <= 1; dx++) {
          const xx = x + dx
          const yy = y + dy
          if (xx >= 0 && yy >= 0 && xx < g.w && yy < g.h && occ[yy * g.w + xx]) { free = 0; break }
        }
      ok[y * g.w + x] = free
    }
  return ok
}

function nearest(g, trav, [x, y], radius = 6) {
  const sx = Math.floor(x / g.cell)
  const sy = Math.floor(y / g.cell)
  let best = -1
  let bd = Infinity
  for (let dy = -radius; dy <= radius; dy++)
    for (let dx = -radius; dx <= radius; dx++) {
      const xx = sx + dx
      const yy = sy + dy
      if (xx >= 0 && yy >= 0 && xx < g.w && yy < g.h && trav[yy * g.w + xx] && dx * dx + dy * dy < bd) { best = yy * g.w + xx; bd = dx * dx + dy * dy }
    }
  return best
}

function flood(g, trav, start) {
  const seen = new Uint8Array(g.w * g.h)
  if (start < 0) return seen
  const queue = new Int32Array(g.w * g.h)
  let head = 0
  let tail = 0
  queue[tail++] = start
  seen[start] = 1
  while (head < tail) {
    const i = queue[head++]
    const x = i % g.w
    const y = (i - x) / g.w
    for (const [dx, dy] of N8) {
      const xx = x + dx
      const yy = y + dy
      if (xx < 0 || yy < 0 || xx >= g.w || yy >= g.h) continue
      const j = yy * g.w + xx
      if (!seen[j] && trav[j]) { seen[j] = 1; queue[tail++] = j }
    }
  }
  return seen
}

// Everyone the entrance can reach now must still be reachable with this collapse added.
function keepsEveryoneReachable(g, x, y, targets) {
  const occ = g.occ.slice()
  const y1 = Math.min(g.H, y + RUBBLE_HALF)
  fillPoly(g, occ, [[x - RUBBLE_HALF, y - RUBBLE_HALF], [x + RUBBLE_HALF, y - RUBBLE_HALF], [x + RUBBLE_HALF, y1], [x - RUBBLE_HALF, y1]])
  rasterSegment({ ...g, occ }, [Math.max(0, x - WALL_HALF), y1], [Math.min(g.W, x + WALL_HALF), y1])
  const trav = traversable(g, occ)
  const reach = flood(g, trav, nearest(g, trav, g.entry))
  return targets.every((p) => { const i = nearest(g, trav, p); return i >= 0 && reach[i] })
}

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1])
const round2 = (v) => Math.round(v * 100) / 100

export function pickAftershock(s) {
  const fp = s.floorplan
  if (!fp?.size || !fp.walls) return {}
  const g = truthGrid(fp)
  g.entry = fp.entry
  const relays = (s.tick?.reality.relays ?? []).filter((r) => r.on && !r.phone && !r.destroyed && !r.beacon_for)
  const robots = (s.tick?.reality.robots ?? []).map((r) => r.pose)
  const survivors = (fp.survivors ?? []).map((p) => p.pos)
  const previous = (fp.rubble ?? []).filter((rb) => rb.dynamic).map((rb) => [
    rb.poly.reduce((t, p) => t + p[0], 0) / rb.poly.length, rb.poly.reduce((t, p) => t + p[1], 0) / rb.poly.length])

  const trav = traversable(g, g.occ)
  const reach = flood(g, trav, nearest(g, trav, g.entry))
  const targets = [...survivors, ...robots].filter((p) => { const i = nearest(g, trav, p); return i >= 0 && reach[i] })

  const fits = (x, y, clear) => {
    const m = RUBBLE_HALF + 0.2
    if (x < m || y < m || x > g.W - m || y > g.H - m) return false
    const ix = Math.floor(x / g.cell)
    const iy = Math.floor(y / g.cell)
    if (g.occ[iy * g.w + ix]) return false
    const p = [x, y]
    if (dist(p, g.entry) < clear.entry) return false
    if (survivors.some((q) => dist(p, q) < clear.survivor)) return false
    if (robots.some((q) => dist(p, q) < clear.robot)) return false
    if (previous.some((q) => dist(p, q) < clear.previous)) return false
    return keepsEveryoneReachable(g, x, y, targets)
  }

  const order = relays.map((r) => [Math.random(), r]).sort((a, b) => a[0] - b[0]).map((e) => e[1])
  for (const clear of [STRICT, LOOSE]) {
    for (const relay of order)
      for (let k = 0; k < RELAY_TRIES; k++) {
        const ang = Math.random() * Math.PI * 2
        const r = 0.6 + Math.random()
        const x = relay.pos[0] + Math.cos(ang) * r
        const y = relay.pos[1] + Math.sin(ang) * r
        if (fits(x, y, clear)) return { at: [round2(x), round2(y)], relay: relay.id }
      }
    for (let k = 0; k < FLOOR_TRIES; k++) {
      const x = Math.random() * g.W
      const y = Math.random() * g.H
      if (!fits(x, y, clear)) continue
      // the server crushes a working relay with every collapse; make it the closest one
      const near = relays.reduce((best, r) => (!best || dist(r.pos, [x, y]) < dist(best.pos, [x, y]) ? r : best), null)
      return { at: [round2(x), round2(y)], ...(near ? { relay: near.id } : {}) }
    }
  }
  return {}
}
