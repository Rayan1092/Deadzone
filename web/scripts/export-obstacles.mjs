// Export the furniture footprints into each floor plan's `obstacles` list (Aziz's
// DZ_OBSTACLES=1 treats them as solid: occupancy and radio loss). The footprints come from
// web/src/three/furniture.js, the same layout the big screen draws, so the picture and the
// physics agree. Run from web/:  node scripts/export-obstacles.mjs [floorplan.json ...]
//
// The list is inserted as text (one obstacle per line) so hand-formatted floor plans keep
// their formatting; every file is re-parsed and checked to differ only by `obstacles` (and a
// `wood` material where wooden pieces need one). Re-running replaces the block.
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { WOOD_LOSS_DB, obstaclesFor } from '../src/three/furniture.js'
import { fillPoly, flood, nearest, rasterSegment, traversable, truthGrid } from '../src/quake.js'

const ROOT = fileURLToPath(new URL('../../data/floorplans/', import.meta.url))

function floorplans() {
  const out = []
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      if (e.name.startsWith('.')) continue
      if (e.isDirectory()) walk(join(dir, e.name))
      else if (e.name.endsWith('.json')) out.push(join(dir, e.name))
    }
  }
  walk(ROOT)
  return out.sort()
}

function withWood(text) {
  return text.replace(/("materials":\s*\{)([^}]*?)(\s*)\}/, (m, open, body, ws) =>
    body.includes('\n')
      ? `${open}${body},${body.match(/\n[ \t]*/)[0]}"wood": ${WOOD_LOSS_DB}${ws}}`
      : `${open}${body}, "wood": ${WOOD_LOSS_DB}${ws}}`)
}

function withObstacles(text, obstacles) {
  const indent = text.match(/\n([ \t]+)"/)?.[1] ?? '  '
  const block = `"obstacles": [\n${obstacles.map((o) => `${indent}${indent}${JSON.stringify(o)}`).join(',\n')}\n${indent}]`
  const at = text.indexOf('"obstacles": [')
  if (at >= 0) {
    const end = text.indexOf(`\n${indent}]`, at)
    return text.slice(0, at) + block + text.slice(end + indent.length + 2)
  }
  const close = text.lastIndexOf('}')
  return `${text.slice(0, close).trimEnd()},\n${indent}${block}\n${text.slice(close)}`
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

// Add the pieces one by one on the planner's grid (walls and rubble grown one cell, no-go zones
// blocked; a footprint fills its cells and its outline, like Aziz's rasterizer) and leave out
// any piece after which a survivor or decoy the entrance could reach is cut off.
function keepReachable(fp, obstacles) {
  const g = truthGrid(fp)
  const people = [...(fp.survivors ?? []), ...(fp.decoys ?? [])]
  const reached = (occ) => {
    const trav = traversable(g, occ)
    const seen = flood(g, trav, nearest(g, trav, fp.entry))
    return people.filter((p) => { const i = nearest(g, trav, p.pos); return i >= 0 && seen[i] }).map((p) => p.id)
  }
  const want = reached(g.occ)
  const kept = []
  const dropped = []
  for (const o of obstacles) {
    const occ = g.occ.slice()
    fillPoly(g, occ, o.poly)
    o.poly.forEach((a, i) => rasterSegment({ ...g, occ }, a, o.poly[(i + 1) % o.poly.length]))
    if (reached(occ).length === want.length) { g.occ = occ; kept.push(o) } else dropped.push(o)
  }
  return { kept, dropped }
}
const args = process.argv.slice(2)
for (const path of args.length ? args : floorplans()) {
  const text = readFileSync(path, 'utf8')
  const before = JSON.parse(text)
  if (!before.rooms || !before.size) continue
  const { kept: obstacles, dropped } = keepReachable(before, obstaclesFor(before))
  let next = withObstacles(text, obstacles)
  const wood = obstacles.some((o) => o.material === 'wood') && !('wood' in before.materials)
  if (wood) next = withWood(next)
  const after = JSON.parse(next)
  const { obstacles: got, materials: m2, ...rest2 } = after
  const { obstacles: _old, materials: m1, ...rest1 } = before
  const okMaterials = same(m2, wood ? { ...m1, wood: WOOD_LOSS_DB } : m1)
  if (!same(rest1, rest2) || !okMaterials || !same(got, obstacles)) throw new Error(`${path}: export would change more than obstacles`)
  writeFileSync(path, next)
  const kinds = Object.entries(obstacles.reduce((t, o) => ({ ...t, [o.kind]: (t[o.kind] ?? 0) + 1 }), {})).map(([k, n]) => `${k} ${n}`).join(', ')
  console.log(`${relative(ROOT, path).padEnd(30)} ${String(obstacles.length).padStart(3)} obstacles${wood ? ' (+wood material)' : ''}: ${kinds}${dropped.length ? ` | left out (would cut someone off): ${dropped.map((o) => `${o.id} ${o.kind}`).join(', ')}` : ''}`)
}
