import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { bodyFootprint, decoyFootprint, decoyLayout, furnitureLayout } from '../src/three/furniture.js'

// Nothing the screen draws in the main run may stand where a robot drives: a visual-only piece
// (chairs and carton piles that are not in the sim's obstacle list, and the decoy props) on a
// recorded path would show a robot driving through it. The paths are the demo guard's exact
// replay (seed 7, 3 robots, DZ_OBSTACLES=1, DZ_SMART_RUBBLE=1, F and O on time) to sim 300 s,
// recorded by web/scripts/record-seed7-paths.py; re-record when the guard is re-baselined.
const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'))
const fp = read('../../data/floorplans/collapse_01.json')
const rec = read('./fixtures/seed7-paths.json')
const MARGIN_M = 0.15   // daylight between the robot's body and the piece

// FLAGS from server/tests/test_demo_guard.py, so a changed main run makes this test ask for a re-record
function guardFlags() {
  const src = readFileSync(new URL('../../server/tests/test_demo_guard.py', import.meta.url), 'utf8')
  const m = /^FLAGS = (\{[^}]*\})/m.exec(src)
  return JSON.parse(m[1].replace(/'/g, '"'))
}

const distToPoly = ([px, py], poly) => {
  let best = Infinity
  for (let i = 0; i < poly.length; i++) {
    const [ax, ay] = poly[i]
    const [bx, by] = poly[(i + 1) % poly.length]
    const dx = bx - ax
    const dy = by - ay
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy || 1)))
    best = Math.min(best, Math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
  }
  return best
}
const inside = ([px, py], poly) => poly.reduce((hit, [xi, yi], i) => {
  const [xj, yj] = poly[(i + poly.length - 1) % poly.length]
  return (yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi ? !hit : hit
}, false)

test('the recorded paths are the main run', () => {
  assert.equal(rec.floorplan, fp.id)
  assert.equal(rec.seed, 7)
  assert.deepEqual(Object.keys(rec.paths).sort(), ['R1', 'R2', 'R3'])
  // the guard's main-run flags when the paths were recorded (re-record when they change)
  assert.deepEqual(rec.flags, guardFlags())
  for (const p of Object.values(rec.paths)) assert.ok(p.length > 500 && p.at(-1)[2] > 250)
})

const pieces = [
  ...furnitureLayout(fp).filter((it) => !it.solid).map((it) => ({ id: `${it.id} ${it.kind}`, poly: bodyFootprint(it)?.poly })).filter((p) => p.poly),
  ...decoyLayout(fp).map((d) => ({ id: `${d.id} ${d.label}`, poly: decoyFootprint(d) })),
]

test('there are visual-only pieces to check (6 chairs, 2 carton piles, 3 decoys)', () => {
  assert.equal(pieces.length, 11)
})

for (const piece of pieces) {
  test(`no robot drives through ${piece.id}`, () => {
    for (const [rid, path] of Object.entries(rec.paths)) {
      for (const [x, y, t] of path) {
        const d = inside([x, y], piece.poly) ? 0 : distToPoly([x, y], piece.poly)
        assert.ok(d >= rec.robot_radius_m + MARGIN_M, `${rid} at sim ${t} s passes ${d.toFixed(2)} m from ${piece.id}`)
      }
    }
  })
}

// The survivor figures stand in Reality from sim 0 (posed like their crops): no robot may drive
// through one either. Reach of each pose from the survivor's spot (Human.jsx; lying includes the
// slab on the legs), poses from the crop manifest the screen reads.
const manifest = read('../../ml/crops/runtime/manifest.json')
const POSE_OF = { crouching: 0.55, crouched: 0.55, bent: 0.8, kneeling: 0.8, sitting: 0.6, slumped: 0.6 }
for (const s of fp.survivors) {
  const pose = s.pose ?? manifest.crops.find((c) => c.file === s.thermal)?.pose
  const reach = POSE_OF[pose] ?? 1.0
  test(`no robot drives through survivor ${s.id} (${pose ?? 'lying'}, ${reach} m)`, () => {
    for (const [rid, path] of Object.entries(rec.paths)) {
      for (const [x, y, t] of path) {
        const d = Math.hypot(x - s.pos[0], y - s.pos[1]) - reach
        assert.ok(d >= rec.robot_radius_m + MARGIN_M, `${rid} at sim ${t} s passes ${d.toFixed(2)} m from ${s.id}`)
      }
    }
  })
}
