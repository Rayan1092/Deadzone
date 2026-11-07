import { create } from 'zustand'

// One store for everything streamed from the sim. Components select what they need.
export const useSim = create((set) => ({
  connected: false,
  running: false,
  speed: 2,
  floorplan: null,
  grid: null,
  robotsMeta: [],
  time: 0,
  tick: null,          // { reality, command, stats }
  maps: { reality: null, command: null, version: 0 },
  events: [],          // newest first, capped
  joinOpen: false,     // full screen QR overlay (Q key)
  joinUrl: null,       // phone join URL from /api/join
  set,
}))

export function decodeMap(b64) {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

export function handleMessage(msg) {
  const { t, data, time } = msg
  const s = useSim.getState()
  switch (t) {
    case 'hello':
      s.set({ floorplan: data.floorplan, grid: data.grid, robotsMeta: data.robots,
              running: data.running, speed: data.speed, events: [] })
      break
    case 'tick':
      s.set({ tick: data, time })
      break
    case 'maps':
      s.set({ maps: { reality: decodeMap(data.reality), command: decodeMap(data.command),
                      version: s.maps.version + 1 } })
      break
    case 'event':
      s.set({ events: [{ ...data, time }, ...s.events].slice(0, 40) })
      break
    case 'control':
      s.set({ running: data.running, speed: data.speed })
      break
    default:
      break
  }
}
