// Sim coordinates (meters, x east, y north) to three.js (y up). Sim y maps to -z so
// north is "up" on screen when looking down from above.
export const w2t = (x, y, h = 0) => [x, h, -y]

export const COLORS = {
  bg: '#14171a',
  floor: '#1b2024',
  wall: '#3a424a',
  wallTop: '#55606b',
  teal: '#2dd4bf',
  amber: '#f59e0b',
  red: '#ef4444',
  green: '#22c55e',
  rubble: '#5b524a',
  hazard: '#ef4444',
}

export const WALL_H = 2.2   // full-height walls; the roof is cut away
export const FOG_H = 2.35   // fog of war sits just above the wall tops
export const MAST_H = 4.2   // command post antenna mast, where radio links end
