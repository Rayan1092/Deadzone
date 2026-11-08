// Normalize negotiated, lossless map frames before the existing store/renderer.
const GRID_KEYS = ['reality', 'command', 'belief', 'belief_command']

function bytes(b64) {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
}

async function inflate(b64) {
  const stream = new Blob([bytes(b64)]).stream().pipeThrough(new DecompressionStream('deflate'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

function shape(data) {
  if (!Number.isInteger(data.w) || !Number.isInteger(data.h) || data.w <= 0 || data.h <= 0) {
    throw new Error('Invalid map dimensions')
  }
  return data.w * data.h
}

export class MapStreamDecoder {
  constructor() { this.reset() }

  reset(epoch = null) {
    this.epoch = epoch
    this.version = null
    this.grids = null
    this.metadata = null
  }

  async decode(message) {
    const { t, data } = message
    if (t === 'hello') {
      const epoch = data.compact_stream?.epoch
      if (epoch && epoch !== this.epoch) this.reset(epoch)
      return message
    }
    if (t === 'maps' && data.encoding === 'zlib-base64') {
      const size = shape(data)
      const entries = await Promise.all(GRID_KEYS.filter((k) => typeof data[k] === 'string')
        .map(async (key) => [key, await inflate(data[key])]))
      if (!entries.length || entries.some(([, grid]) => grid.length !== size)) throw new Error('Invalid map keyframe')
      const { encoding, ...metadata } = data
      for (const key of GRID_KEYS) delete metadata[key]
      this.epoch = data.epoch
      this.version = data.version
      this.grids = Object.fromEntries(entries)
      this.metadata = metadata
    } else if (t === 'map_patch') {
      if (data.encoding !== 'zlib-base64-u32le-u8' || !this.grids || data.epoch !== this.epoch ||
          data.base !== this.version || data.version !== this.version + 1) throw new Error('Map patch gap')
      const size = shape(data)
      if (data.w !== this.metadata.w || data.h !== this.metadata.h || data.cell !== this.metadata.cell) {
        throw new Error('Map patch geometry changed')
      }
      const grids = { ...this.grids }
      for (const [key, encoded] of Object.entries(data.grids)) {
        if (!GRID_KEYS.includes(key) || !grids[key]) throw new Error('Unknown patch grid')
        const raw = await inflate(encoded)
        if (raw.length % 5) throw new Error('Truncated map patch')
        const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength)
        const grid = grids[key].slice() // never mutate a grid currently displayed by React
        for (let offset = 0; offset < raw.length; offset += 5) {
          const index = view.getUint32(offset, true)
          if (index >= size) throw new Error('Map patch index outside grid')
          grid[index] = raw[offset + 4]
        }
        grids[key] = grid
      }
      const { encoding, grids: patches, base, ...metadata } = data
      this.grids = grids
      this.metadata = { ...this.metadata, ...metadata }
      this.version = data.version
    } else {
      return message
    }
    return { ...message, t: 'maps', data: { ...this.metadata, ...this.grids } }
  }
}

// Record normalized legacy maps, so existing recordings/replay stay synchronous.
export function recordableFrame(message) {
  if (message.t !== 'maps') return message
  const data = { ...message.data }
  for (const key of GRID_KEYS) {
    if (!(data[key] instanceof Uint8Array)) continue
    let binary = ''
    for (let i = 0; i < data[key].length; i += 8192) {
      binary += String.fromCharCode(...data[key].subarray(i, i + 8192))
    }
    data[key] = btoa(binary)
  }
  return { ...message, data }
}
