import test from 'node:test'
import assert from 'node:assert/strict'

// The crop manifest the AI cards read. The fetch runs when the module loads, so stub it first.
const manifest = { caption: 'Real FLIR thermal frame, same input as the AI', crops: [{ file: 'pos_0003.png', shows: 'person slumped in a chair', heatmap_alpha: 'heatmaps/pos_0003_alpha.png' }] }
globalThis.fetch = async () => ({ ok: true, json: async () => manifest })
const { cropCaption, cropEntry, manifestReady, onManifest, sentence } = await import('../src/crops.js')

test('a card that subscribes after the manifest already loaded still gets it (the #121 fast-load bug)', async () => {
  await manifestReady                              // the fetch finished before the card's effect ran
  const got = await new Promise((resolve) => {
    onManifest(resolve)
    setTimeout(() => resolve('never called'), 200)
  })
  assert.equal(got, manifest)
  const entry = cropEntry(got, 'pos_0003.png')
  assert.equal(entry.shows, 'person slumped in a chair')
  assert.equal(cropCaption(got, entry), manifest.caption)
})

test('an unsubscribed card is not called back; a card with no manifest falls back honestly', async () => {
  let calls = 0
  const off = onManifest(() => calls++)
  off()
  await manifestReady
  await new Promise((r) => setTimeout(r, 20))
  assert.equal(calls, 0)
  assert.equal(cropEntry(null, 'pos_0003.png'), null)
  assert.match(cropCaption(null, null), /thermal/i)
  assert.equal(sentence('Real FLIR thermal frame'), 'Real FLIR thermal frame.')
})

test('the cards\' hook subscribes through onManifest with no "already loaded" shortcut', async () => {
  const { readFileSync } = await import('node:fs')
  const src = readFileSync(new URL('../src/crops.js', import.meta.url), 'utf8')
  const hook = src.slice(src.indexOf('export function useCropManifest'))
  assert.match(hook, /useEffect\(\(\) => onManifest\(setM\), \[\]\)/)
  assert.doesNotMatch(hook, /if \(!manifest\)/, 'skipping the subscription when the manifest is already loaded is the #121 bug')
  const cards = readFileSync(new URL('../src/panels/DetectionCards.jsx', import.meta.url), 'utf8')
  assert.match(cards, /useCropManifest\(\)/)
})
