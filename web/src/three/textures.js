import * as THREE from 'three'

// Procedural PBR textures, drawn once on canvases: no image downloads, so nothing
// depends on venue Wi-Fi. Each surface gets a color map plus a normal map derived from
// the same height field, so lights pick out real bumps, joints and mortar lines.
// Deterministic noise: every client and reload looks the same.

function rng(seed) {
  let s = seed % 2147483647
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}

// Smooth value noise in [0, 1), tileable on a `cells` grid.
function valueNoise(seed, cells) {
  const r = rng(seed)
  const grid = Array.from({ length: cells * cells }, () => r())
  const at = (i, j) => grid[(((j % cells) + cells) % cells) * cells + (((i % cells) + cells) % cells)]
  return (u, v) => {
    const x = u * cells
    const y = v * cells
    const i = Math.floor(x)
    const j = Math.floor(y)
    const fx = x - i
    const fy = y - j
    const sx = fx * fx * (3 - 2 * fx)
    const sy = fy * fy * (3 - 2 * fy)
    const a = at(i, j) * (1 - sx) + at(i + 1, j) * sx
    const b = at(i, j + 1) * (1 - sx) + at(i + 1, j + 1) * sx
    return a * (1 - sy) + b * sy
  }
}

// Fractal noise from a few octaves.
function fbm(seed, base = 4, octaves = 4) {
  const layers = Array.from({ length: octaves }, (_, k) => valueNoise(seed + k * 101, base << k))
  return (u, v) => {
    let sum = 0
    let amp = 0.5
    let norm = 0
    for (const n of layers) { sum += n(u, v) * amp; norm += amp; amp *= 0.5 }
    return sum / norm
  }
}

// Build a color canvas and a normal-map canvas from per-pixel functions.
function surface(size, colorAt, heightAt, strength = 2) {
  const color = document.createElement('canvas')
  const normal = document.createElement('canvas')
  color.width = color.height = normal.width = normal.height = size
  const cctx = color.getContext('2d')
  const nctx = normal.getContext('2d')
  const cimg = cctx.createImageData(size, size)
  const nimg = nctx.createImageData(size, size)
  const h = new Float32Array(size * size)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = x / size
      const v = y / size
      const [r, g, b] = colorAt(u, v, x, y)
      const o = (y * size + x) * 4
      cimg.data[o] = r; cimg.data[o + 1] = g; cimg.data[o + 2] = b; cimg.data[o + 3] = 255
      h[y * size + x] = heightAt(u, v, x, y)
    }
  }
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const hx = h[y * size + ((x + 1) % size)] - h[y * size + ((x - 1 + size) % size)]
      const hy = h[((y + 1) % size) * size + x] - h[((y - 1 + size) % size) * size + x]
      const nx = -hx * strength
      const ny = -hy * strength
      const len = Math.hypot(nx, ny, 1)
      const o = (y * size + x) * 4
      nimg.data[o] = ((nx / len) * 0.5 + 0.5) * 255
      nimg.data[o + 1] = ((ny / len) * 0.5 + 0.5) * 255
      nimg.data[o + 2] = ((1 / len) * 0.5 + 0.5) * 255
      nimg.data[o + 3] = 255
    }
  }
  cctx.putImageData(cimg, 0, 0)
  nctx.putImageData(nimg, 0, 0)
  const map = new THREE.CanvasTexture(color)
  map.colorSpace = THREE.SRGBColorSpace
  const normalMap = new THREE.CanvasTexture(normal)
  for (const t of [map, normalMap]) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 8 }
  return { map, normalMap }
}

const clamp = (v) => Math.max(0, Math.min(255, v))

// Polished concrete slab: mottled grey, saw-cut joint around the tile edge, hairline
// cracks, dust. One texture tile = one 4 m slab.
function floorConcrete() {
  const n = fbm(11, 4, 5)
  const crack = fbm(17, 3, 3)
  const dust = fbm(23, 2, 3)
  const joint = (u, v) => Math.min(u, 1 - u, v, 1 - v) < 0.006
  const where = fbm(19, 2, 2)
  const isCrack = (u, v) => where(u, v) > 0.62 && Math.abs(crack(u, v) - 0.5) < 0.004
  return surface(512, (u, v) => {
    const m = n(u, v)
    let g = 74 + (m - 0.5) * 34 + (dust(u, v) - 0.5) * 18
    if (joint(u, v)) g -= 34
    if (isCrack(u, v)) g -= 22
    return [clamp(g + 2), clamp(g + 3), clamp(g + 5)]
  }, (u, v) => {
    let ht = n(u, v) * 0.6
    if (joint(u, v)) ht -= 1.2
    if (isCrack(u, v)) ht -= 0.6
    return ht
  }, 3)
}

// Interior plaster: warm off-white with water stains and a dark baseboard at the bottom
// (texture v runs bottom to top along the wall height).
function plaster() {
  const n = fbm(31, 6, 4)
  const stain = fbm(37, 2, 3)
  return surface(256, (u, v) => {
    if (v > 0.955) return [56, 58, 62] // baseboard (bottom of the wall, flipY)
    const s = Math.max(0, stain(u, v) - 0.55) * 120
    const g = 178 + (n(u, v) - 0.5) * 22 - s
    return [clamp(g + 6), clamp(g + 3), clamp(g - 4)]
  }, (u, v) => (v > 0.955 ? 0.8 : n(u, v) * 0.4), 2)
}

// Brick: running bond with recessed mortar, per-brick color variation.
function brick() {
  const n = fbm(41, 8, 3)
  const r = rng(43)
  const shades = Array.from({ length: 64 }, () => 0.8 + r() * 0.35)
  const ROWS = 8
  const COLS = 4
  const cellAt = (u, v) => {
    const row = Math.floor(v * ROWS)
    const shift = row % 2 ? 0.5 / COLS : 0
    const uu = (u + shift) % 1
    const col = Math.floor(uu * COLS)
    const fu = uu * COLS - col
    const fv = v * ROWS - row
    const mortar = fu < 0.05 || fv < 0.1
    return { mortar, shade: shades[(row * COLS + col) % 64] }
  }
  return surface(256, (u, v) => {
    const { mortar, shade } = cellAt(u, v)
    if (mortar) return [118, 112, 104]
    const k = shade * (0.9 + n(u, v) * 0.2)
    return [clamp(132 * k), clamp(66 * k), clamp(52 * k)]
  }, (u, v) => (cellAt(u, v).mortar ? -1 : n(u, v) * 0.3), 3)
}

// Metal cladding: vertical ribs with streaks of grime.
function ribbedMetal() {
  const n = fbm(51, 2, 4)
  return surface(256, (u, v) => {
    const rib = Math.cos(u * Math.PI * 2 * 10)
    const g = 120 + rib * 14 + (n(u, v) - 0.5) * 30
    return [clamp(g - 4), clamp(g), clamp(g + 6)]
  }, (u) => Math.cos(u * Math.PI * 2 * 10), 1.5)
}

// Asphalt lot outside the building.
function asphalt() {
  const n = fbm(61, 8, 4)
  const r = rng(67)
  return surface(256, (u, v) => {
    const g = 34 + (n(u, v) - 0.5) * 16 + (r() - 0.5) * 10
    return [clamp(g), clamp(g + 1), clamp(g + 3)]
  }, (u, v) => n(u, v) * 0.5 + r() * 0.15, 1.5)
}

// Yellow/black hazard tape, stripes running along u.
function hazardTape() {
  return surface(128, (u, v) => (Math.floor((u * 8 + v) * 2) % 2 ? [20, 20, 20] : [234, 179, 8]), () => 0, 0)
}

// Soft dust stain under rubble and props (alpha in the color map's luminance).
function dustDecal() {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const ctx = c.getContext('2d')
  const g = ctx.createRadialGradient(64, 64, 4, 64, 64, 64)
  g.addColorStop(0, 'rgba(120,110,96,0.85)')
  g.addColorStop(0.6, 'rgba(110,100,88,0.35)')
  g.addColorStop(1, 'rgba(110,100,88,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

// Cast-in-place concrete wall: formwork panel seams, tie holes, mottling, grime at the base.
function concreteWall() {
  const n = fbm(71, 4, 5)
  const grime = fbm(73, 2, 3)
  const seam = (u, v) => (u * 2) % 1 < 0.008 || (v * 2) % 1 < 0.01
  const tie = (u, v) => {
    const du = ((u * 4 + 0.5) % 1) - 0.5
    const dv = ((v * 4 + 0.5) % 1) - 0.5
    return du * du + dv * dv < 0.0035
  }
  return surface(256, (u, v) => {
    let g = 128 + (n(u, v) - 0.5) * 36 - Math.max(0, v - 0.7) * 70 * grime(u, v)
    if (seam(u, v)) g -= 22
    if (tie(u, v)) g -= 40
    return [clamp(g + 2), clamp(g + 1), clamp(g - 2)]
  }, (u, v) => (tie(u, v) ? -1 : seam(u, v) ? -0.5 : n(u, v) * 0.5), 2.5)
}

// Office carpet tiles: fine fibre noise, 50 cm tiles laid in alternating grain.
function carpet() {
  const r = rng(81)
  const n = fbm(83, 16, 2)
  return surface(256, (u, v) => {
    const alt = (Math.floor(u * 4) + Math.floor(v * 4)) % 2
    const g = 62 + (r() - 0.5) * 18 + (n(u, v) - 0.5) * 14 + (alt ? 4 : -4)
    return [clamp(g - 8), clamp(g - 2), clamp(g + 10)]
  }, () => r() * 0.5, 1)
}

// Vinyl floor tiles (break room / corridor): 30 cm squares, light and dark, scuffed.
function vinyl() {
  const n = fbm(91, 8, 3)
  return surface(256, (u, v) => {
    const k = (Math.floor(u * 4) + Math.floor(v * 4)) % 2
    const edge = (u * 4) % 1 < 0.012 || (v * 4) % 1 < 0.012
    const g = (k ? 170 : 132) + (n(u, v) - 0.5) * 20 - (edge ? 30 : 0)
    return [clamp(g + 2), clamp(g), clamp(g - 6)]
  }, (u, v) => ((u * 4) % 1 < 0.012 || (v * 4) % 1 < 0.012 ? -0.6 : 0), 2)
}

// Diamond chain-link fence: color map carries the wire, alpha map cuts the gaps.
function chainLink() {
  const S = 256
  const c = document.createElement('canvas')
  c.width = c.height = S
  const ctx = c.getContext('2d')
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, S, S)
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = 7
  const N = 4
  for (let i = -N; i <= N * 2; i++) {
    ctx.beginPath(); ctx.moveTo((i * S) / N, 0); ctx.lineTo(((i + N) * S) / N, S); ctx.stroke()
    ctx.beginPath(); ctx.moveTo((i * S) / N, S); ctx.lineTo(((i + N) * S) / N, 0); ctx.stroke()
  }
  const alphaMap = new THREE.CanvasTexture(c)
  alphaMap.wrapS = alphaMap.wrapT = THREE.RepeatWrapping
  return { alphaMap }
}

// Soft round puff for gas haze sprites.
function puff() {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const ctx = c.getContext('2d')
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(0.5, 'rgba(255,255,255,0.45)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  return new THREE.CanvasTexture(c)
}

// Rubber track tread: ridges across the belt.
function tread() {
  return surface(64, (u) => {
    const g = (u * 8) % 1 < 0.5 ? 34 : 22
    return [g, g, g + 2]
  }, (u) => ((u * 8) % 1 < 0.5 ? 1 : 0), 3)
}

// Text on a canvas, for signs and the truck livery.
export function signTexture(lines, { w = 256, h = 128, bg = '#facc15', fg = '#111', font = 'bold 44px Inter, sans-serif' } = {}) {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const ctx = c.getContext('2d')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, w, h)
  ctx.fillStyle = fg
  ctx.font = font
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  lines.forEach((t, i) => ctx.fillText(t, w / 2, (h * (i + 1)) / (lines.length + 1)))
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 8
  return t
}

let cache = null
export function materials() {
  if (!cache) {
    cache = {
      floor: floorConcrete(),
      plaster: plaster(),
      brick: brick(),
      metal: ribbedMetal(),
      asphalt: asphalt(),
      tape: hazardTape(),
      dust: dustDecal(),
      concrete: concreteWall(),
      carpet: carpet(),
      vinyl: vinyl(),
      fence: chainLink(),
      puff: puff(),
      tread: tread(),
    }
  }
  return cache
}

// Kept for older callers: plain concrete color maps.
export function concreteTextures() {
  const m = materials()
  return { floor: m.floor.map, wall: m.plaster.map }
}

// A clone with its own repeat, so one surface can tile differently on each mesh.
export function tiled(tex, rx, ry) {
  const t = tex.clone()
  t.repeat.set(rx, ry)
  t.needsUpdate = true
  return t
}

// tiled() for a {map, normalMap} pair.
export function tiledSet(set, rx, ry) {
  const out = {}
  for (const k of ['map', 'normalMap', 'alphaMap']) if (set[k]) out[k] = tiled(set[k], rx, ry)
  return out
}
