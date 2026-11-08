import test from 'node:test'
import assert from 'node:assert/strict'
import { modelProbability, nextJudgeExample, poolImageUrl, readJudgePool } from '../src/panels/judgePool.js'

const manifest = () => ({ split: 'val', model: { name: 'Onboard model', threshold: .6 }, examples: [
  { file: 'crops/a.png', label: 'person', p_person: .91 },
  { file: 'crops/b.png', label: 'not person', conf: .13 },
] })

test('uses actual exported probabilities, threshold and labels', () => {
  const pool = readJudgePool(manifest())
  assert.equal(pool.model, 'Onboard model')
  assert.equal(pool.items[0].score, .91)
  assert.equal(pool.items[0].predicted, 'person')
  assert.equal(pool.items[1].predicted, 'not person')
})

test('does not invent missing model evidence or assume held-out status', () => {
  const data = manifest()
  delete data.examples[0].p_person
  assert.throws(() => readJudgePool(data), /exported model/)
  const unverified = manifest()
  delete unverified.split
  assert.throws(() => readJudgePool(unverified), /held-out/)
  const noThreshold = manifest()
  delete noThreshold.model.threshold
  assert.throws(() => readJudgePool(noThreshold), /threshold/)
})

test('refuses invalid probabilities and duplicate files instead of cherry-picking', () => {
  for (const value of [-1, 1.1, NaN, '0.9']) {
    const data = manifest()
    data.examples[0].p_person = value
    assert.throws(() => readJudgePool(data), /P\(person\)/)
  }
  const data = manifest()
  data.examples[1].file = data.examples[0].file
  assert.throws(() => readJudgePool(data), /duplicate/)
})

test('crop URLs stay in the same-origin pool', () => {
  assert.equal(poolImageUrl('crops/a b.png'), '/ai-lab/results/judge_pool/crops/a%20b.png')
  for (const file of ['../a.png', 'https://elsewhere/a.png', '/outside.png', 'crops\\a.png', '.hidden.png', 'a.svg'])
    assert.throws(() => poolImageUrl(file))
})

test('random rounds do not repeat previously judged images', () => {
  const { items } = readJudgePool(manifest())
  assert.equal(nextJudgeExample(items, [], () => 0).id, items[0].id)
  assert.equal(nextJudgeExample(items, [items[0].id], () => 0).id, items[1].id)
  assert.equal(nextJudgeExample(items, items.map((item) => item.id)), null)
})

test('near-certain probabilities are never rounded up to 100%', () => {
  assert.equal(modelProbability(.999999), '99.99%')
  assert.equal(modelProbability(1), '100%')
  assert.equal(modelProbability(.13), '13%')
})
