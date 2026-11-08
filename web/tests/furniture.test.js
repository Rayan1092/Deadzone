import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { MAIN_RUN_BASELINE, footprint, furnitureLayout, obstaclesFor } from '../src/three/furniture.js'

const plan = (name) => JSON.parse(readFileSync(new URL(`../../data/floorplans/${name}.json`, import.meta.url), 'utf8'))
const r2 = (v) => Math.round(v * 100) / 100

test('a footprint follows the prop heading: local x along rot, the front (+z) away from its wall', () => {
  // a 1.4 x 0.7 desk against the north wall (rot 0) faces south: it spans x +-0.7, y +-0.35
  const f = footprint({ kind: 'desk', x: 5, y: 10, rot: 0 })
  assert.deepEqual(f.poly.map((p) => p.map(r2)), [[4.3, 10.35], [5.7, 10.35], [5.7, 9.65], [4.3, 9.65]])
  // against the west wall (rot W) the long side runs north-south
  const g = footprint({ kind: 'desk', x: 0.45, y: 7.1, rot: Math.PI / 2 })
  const xs = g.poly.map((p) => p[0]); const ys = g.poly.map((p) => p[1])
  assert.ok(Math.max(...ys) - Math.min(...ys) > Math.max(...xs) - Math.min(...xs))
  // flat and wall-mounted dressing is not solid; chairs and carton piles are
  assert.equal(footprint({ kind: 'papers', x: 0, y: 0, rot: 0 }), null)
  assert.equal(footprint({ kind: 'pipeRun', x: 0, y: 0, rot: 0, opts: { len: 4 } }), null)
  assert.ok(footprint({ kind: 'chair', x: 0, y: 0, rot: 0 }))
  assert.ok(footprint({ kind: 'chair', x: 0, y: 0, rot: 0, opts: { tipped: true } }))
  assert.ok(footprint({ kind: 'boxes', x: 0, y: 0, rot: 0, opts: { n: 5 } }))
  assert.equal(footprint({ kind: 'chair', x: 0, y: 0, rot: 0, opts: { visualOnly: true } }), null)
})

test('chairs are solid in generated buildings; the main run keeps its measured baseline', () => {
  assert.ok(plan('generated/gen_3').obstacles.some((o) => o.kind === 'chair'))
  assert.ok(MAIN_RUN_BASELINE)
  const demo = furnitureLayout(plan('collapse_01'))
  assert.ok(demo.some((i) => i.kind === 'chair' && !i.solid))   // still drawn, drive-through until DEMO.md is re-baselined
  assert.ok(!plan('collapse_01').obstacles.some((o) => o.kind === 'chair' || o.kind === 'boxes'))
})

for (const name of ['collapse_01', 'generated/gen_1', 'generated/gen_3', 'showcase_01', 'variants/collapse_01_v2']) {
  test(`${name}: what the screen draws is exactly the exported obstacle list`, () => {
    const fp = plan(name)
    const drawn = furnitureLayout(fp).filter((i) => i.solid).map((i) => [i.id, i.poly.map((p) => p.map(r2))])
    assert.deepEqual(drawn, fp.obstacles.map((o) => [o.id, o.poly]))
    for (const o of fp.obstacles) {
      assert.ok(o.material in fp.materials)
      assert.ok(o.poly.every(([x, y]) => x >= 0 && y >= 0 && x <= fp.size[0] && y <= fp.size[1]))
    }
  })
}

test('the demo building keeps every hand-placed solid piece, and none sits on a person', () => {
  const fp = plan('collapse_01')
  assert.equal(obstaclesFor(fp).length, 25)
  const inside = ([x, y], poly) => poly.reduce((hit, [xi, yi], i) => {
    const [xj, yj] = poly[(i + poly.length - 1) % poly.length]
    return (yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi ? !hit : hit
  }, false)
  for (const p of [...fp.survivors, ...fp.decoys]) assert.ok(!fp.obstacles.some((o) => inside(p.pos, o.poly)), p.id)
})
