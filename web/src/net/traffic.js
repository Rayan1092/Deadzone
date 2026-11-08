// Aziz's network traffic events (DZ_NETWORK_TRAFFIC=1, scripts/TRAFFIC.md): `bundle_hop` after a
// hop's custody acknowledgment, `bundle_held` when a bundle starts waiting. Several arrive every
// second, so they stay out of the store and the event feed: a small buffer the network layer
// drains each frame (packet dots), and per-link byte windows (line thickness). Only actual
// completed hops are kept; nothing here is invented. No imports, so Node can test it.

const MAX_HOPS = 256
const WINDOW_MS = 3000
let hops = []
let seen = false
const linkBytes = new Map()   // 'a|b' (sorted) -> [[at, wire_bytes], ...] within the window

export const linkKey = (a, b) => (a < b ? `${a}|${b}` : `${b}|${a}`)

export function pushTraffic(ev, now = performance.now()) {
  if (ev.kind !== 'bundle_hop' || !ev.a || !ev.b) return
  seen = true
  hops.push({ a: ev.a, b: ev.b, kind: ev.bundle_kind, bytes: ev.wire_bytes ?? ev.bytes ?? 0, at: now })
  if (hops.length > MAX_HOPS) hops = hops.slice(-MAX_HOPS)
  const key = linkKey(ev.a, ev.b)
  const list = linkBytes.get(key) ?? []
  list.push([now, ev.wire_bytes ?? ev.bytes ?? 0])
  linkBytes.set(key, list)
}

// The hops that completed since the last call (oldest first).
export function drainHops() {
  const out = hops
  hops = []
  return out
}

// Bytes per second over this link in the last 3 s; null until any traffic event has arrived (the
// flag is off), so callers can keep the plain look instead of showing every link as idle.
export function linkRate(a, b, now = performance.now()) {
  if (!seen) return null
  const list = linkBytes.get(linkKey(a, b))
  if (!list) return 0
  while (list.length && now - list[0][0] > WINDOW_MS) list.shift()
  return list.reduce((t, [, bytes]) => t + bytes, 0) / (WINDOW_MS / 1000)
}

export const trafficSeen = () => seen

export function resetTraffic() {
  hops = []
  linkBytes.clear()
}
