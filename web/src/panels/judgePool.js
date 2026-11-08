// Judge evidence comes only from the exported pool, never a made-up prediction.
export const POOL_ROOT = '/ai-lab/results/judge_pool/'

function label(value) {
  if (value === 1 || value === 'person') return 'person'
  if (value === 0 || ['not person', 'not_person', 'not-person'].includes(value)) return 'not person'
  throw new Error('Each example needs a recorded person/not person label.')
}

export function poolImageUrl(file) {
  if (typeof file !== 'string') throw new Error('Missing crop file.')
  const relative = file.startsWith(POOL_ROOT) ? file.slice(POOL_ROOT.length) : file
  if (!relative || /[:\\?#]/.test(relative) || relative.startsWith('/') ||
      relative.split('/').some((part) => !part || part.startsWith('.')) ||
      !/\.(png|jpe?g|webp)$/i.test(relative)) throw new Error('Crop must be an image inside the held-out test set.')
  return POOL_ROOT + relative.split('/').map(encodeURIComponent).join('/')
}

export function readJudgePool(raw) {
  const examples = raw?.examples ?? raw?.samples ?? raw?.items
  if (!Array.isArray(examples) || !examples.length || examples.length > 2000)
    throw new Error('The held-out test set needs 1–2000 exported examples.')
  const split = raw.split ?? raw.dataset?.split
  const heldOut = raw.held_out === true || /^(val|validation|test|held[_ -]out)$/i.test(split ?? '')
  if (!heldOut) throw new Error('The manifest must identify a held-out validation/test split.')
  const threshold = raw.model?.threshold ?? raw.threshold
  const seen = new Set()
  const items = examples.map((row) => {
    const url = poolImageUrl(row.file ?? row.path)
    if (seen.has(url)) throw new Error('The held-out test set contains duplicate crop files.')
    seen.add(url)
    // `conf` is P(person), matching Rayan's existing lab.json convention.
    const score = row.p_person ?? row.score ?? row.conf
    if (typeof score !== 'number' || !Number.isFinite(score) || score < 0 || score > 1)
      throw new Error('Each crop needs its exported model P(person), from 0 to 1.')
    let predicted
    if (row.predicted != null) predicted = label(row.predicted)
    else {
      if (typeof threshold !== 'number' || !Number.isFinite(threshold) || threshold < 0 || threshold > 1)
        throw new Error('Record the model threshold or its predicted label in the export.')
      predicted = score >= threshold ? 'person' : 'not person'
    }
    return { id: url, url, label: label(row.label), predicted, score }
  })
  return { items, model: raw.model?.name ?? 'Exported onboard model', split: split ?? 'held-out' }
}

export function nextJudgeExample(items, used, random = Math.random) {
  const remaining = items.filter((item) => !used.includes(item.id))
  if (!remaining.length) return null
  return remaining[Math.min(remaining.length - 1, Math.floor(random() * remaining.length))]
}

// Floor rather than round up a near-100% prediction into a guarantee.
export const modelProbability = (score) => `${Math.floor(score * 10000) / 100}%`
