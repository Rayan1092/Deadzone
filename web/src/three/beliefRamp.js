// Rayan's survivor belief map (maps.belief / maps.belief_command): per cell 0..254 is the missing
// survivor mass on a shared scale, 255 a confirmed survivor's cell. One colour ramp for the heat
// (transparent where nobody is likely, violet where someone may still be), a teal marker for the
// confirmed cells. No imports, so Node can test it.
export const CONFIRMED = 255
const LOW = [124, 58, 237]    // violet-600
const HIGH = [233, 213, 255]  // violet-200
const MARK = [45, 212, 191]   // teal: someone confirmed here

export function beliefPixel(v) {
  if (v === CONFIRMED) return [...MARK, 235]
  if (!v) return [0, 0, 0, 0]
  const k = Math.min(1, v / 254)
  const e = Math.sqrt(k) // lift faint mass so a whole unsearched room still reads
  return [0, 1, 2].map((i) => Math.round(LOW[i] + (HIGH[i] - LOW[i]) * k)).concat(Math.round(40 + 175 * e))
}

// Whole people for the Rescue Status strip ("≈2 still unaccounted for"); null without an estimate
export function missingPeople(n) {
  if (n == null || !Number.isFinite(n)) return null
  return Math.max(0, Math.round(n))
}

// "about 2 people still unaccounted for"; null when the server sends no estimate
export function missingText(n) {
  if (n == null || !Number.isFinite(n)) return null
  const people = Math.max(0, Math.round(n))
  return people === 1 ? 'about 1 person' : `about ${people} people`
}
