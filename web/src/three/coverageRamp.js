// Aziz's predicted Command radio coverage (DZ_COVERAGE_GRID, PLAN.md "Predicted Command RSSI
// grid"): signed int8 dBm per map cell. Strong (teal) down to the link limit (amber), then dead
// (red). The radio model runs full rate at -60 dBm and drops the link below -88. No imports.
export const STRONG_DBM = -60
export const DEAD_DBM = -88
const mix = (a, b, k) => a.map((v, i) => Math.round(v + (b[i] - v) * k))
const TEAL = [45, 212, 191]
const AMBER = [245, 158, 11]
const RED = [239, 68, 68]
export function coveragePixel(dbm) {
  if (dbm == null || !Number.isFinite(dbm)) return [0, 0, 0, 0]
  if (dbm < DEAD_DBM) return [...RED, 120]
  const k = Math.min(1, Math.max(0, (STRONG_DBM - dbm) / (STRONG_DBM - DEAD_DBM))) // 0 strong .. 1 at the limit
  const rgb = k < 0.5 ? mix(TEAL, AMBER, k * 2) : mix(AMBER, RED, (k - 0.5) * 2 * 0.5)
  return [...rgb, 95]
}
