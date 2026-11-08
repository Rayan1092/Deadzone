import * as THREE from 'three'

// Procedural concrete, drawn once on a canvas: no image downloads, so nothing depends
// on venue Wi-Fi. Deterministic noise so every client and reload looks the same.
function rng(seed) {
  let s = seed % 2147483647
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}

function concrete({ size = 256, base = [38, 43, 48], spread = 14, joints = 0, seed = 11 }) {
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')
  const img = ctx.createImageData(size, size)
  const r = rng(seed)
  // two octaves of value noise: coarse blotches plus fine grain
  const coarse = Array.from({ length: 17 * 17 }, () => r())
  const at = (x, y) => {
    const gx = (x / size) * 16
    const gy = (y / size) * 16
    const x0 = Math.floor(gx)
    const y0 = Math.floor(gy)
    const fx = gx - x0
    const fy = gy - y0
    const v = (i, j) => coarse[((y0 + j) % 17) * 17 + ((x0 + i) % 17)]
    return (v(0, 0) * (1 - fx) + v(1, 0) * fx) * (1 - fy) + (v(0, 1) * (1 - fx) + v(1, 1) * fx) * fy
  }
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const n = (at(x, y) - 0.5) * spread + (r() - 0.5) * spread * 0.6
      const o = (y * size + x) * 4
      img.data[o] = base[0] + n
      img.data[o + 1] = base[1] + n
      img.data[o + 2] = base[2] + n
      img.data[o + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
  if (joints) { // saw-cut expansion joints
    ctx.strokeStyle = 'rgba(0,0,0,0.35)'
    ctx.lineWidth = 2
    for (let k = 0; k <= size; k += size / joints) {
      ctx.beginPath(); ctx.moveTo(k, 0); ctx.lineTo(k, size); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(0, k); ctx.lineTo(size, k); ctx.stroke()
    }
  }
  const tex = new THREE.CanvasTexture(c)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  return tex
}

let cache = null
export function concreteTextures() {
  if (!cache) {
    cache = {
      floor: concrete({ base: [34, 39, 44], spread: 12, joints: 1, seed: 11 }),
      wall: concrete({ base: [70, 78, 86], spread: 18, seed: 29 }),
    }
  }
  return cache
}
