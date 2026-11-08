import { useEffect, useState } from 'react'
import { useSim } from '../store'
import DataPanel from './DataPanel'
import { modelProbability, nextJudgeExample, POOL_ROOT, readJudgePool } from './judgePool'

export default function JudgeTest() {
  const open = useSim((state) => state.judgeOpen)
  const set = useSim((state) => state.set)
  const [pool, setPool] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [reload, setReload] = useState(0)
  const [current, setCurrent] = useState(null)
  const [used, setUsed] = useState([])
  const [guess, setGuess] = useState(null)
  const [imageReady, setImageReady] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [tally, setTally] = useState({ rounds: 0, judge: 0, model: 0 })
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setLoading(true); setError(''); setPool(null); setCurrent(null)
    setTally({ rounds: 0, judge: 0, model: 0 }); setUsed([]); setGuess(null)
    fetch(POOL_ROOT + 'manifest.json', { signal: controller.signal, cache: 'no-cache' })
      .then((response) => {
        if (!response.ok) throw new Error(response.status === 404
          ? 'Judge pool is not available yet. Enable AI Lab and wait for the held-out export.'
          : `Judge pool could not load (${response.status}).`)
        return response.json()
      })
      .then((raw) => {
        if (controller.signal.aborted) return
        const loaded = readJudgePool(raw)
        setPool(loaded); setCurrent(nextJudgeExample(loaded.items, []))
        setImageReady(false); setImageError(false)
      })
      .catch((failure) => { if (!controller.signal.aborted) setError(failure.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [open, reload])
  if (!open) return null
  const answer = (choice) => {
    if (guess !== null || !imageReady || imageError || !current) return
    setGuess(choice)
    setUsed((previous) => [...previous, current.id])
    setTally((previous) => ({ rounds: previous.rounds + 1,
      judge: previous.judge + Number(choice === current.label),
      model: previous.model + Number(current.predicted === current.label) }))
  }
  const next = () => {
    setCurrent(nextJudgeExample(pool.items, used)); setGuess(null)
    setImageReady(false); setImageError(false)
  }
  return (
    <DataPanel title="Judge test" onClose={() => set({ judgeOpen: false })} className="judge-test">
      <p>Can you spot a person in a real thermal image? Make your guess before the model result and label are revealed.</p>
      <div className="judge-tally" aria-live="polite">
        <span>Model <b>{tally.model} of {tally.rounds}</b></span><span>You <b>{tally.judge} of {tally.rounds}</b></span>
      </div>
      {loading && <p role="status">Loading the held-out judge pool…</p>}
      {error && <p role="alert" className="data-panel-note">{error}</p>}
      {!loading && error && <button onClick={() => setReload((n) => n + 1)}>Retry pool</button>}
      {pool && current && <>
        <figure><img key={current.id} src={current.url} alt="Thermal crop to classify"
                     onLoad={() => setImageReady(true)} onError={() => setImageError(true)} />
          <figcaption>Real thermal camera image, Teledyne FLIR dataset: the same input a thermal camera on a rescue robot produces.</figcaption>
        </figure>
        {imageError && <p role="alert">This crop could not load. No guess or score has been recorded.</p>}
        {guess === null ? <div className="judge-actions">
          <button disabled={!imageReady || imageError} onClick={() => answer('person')}>Person</button>
          <button disabled={!imageReady || imageError} onClick={() => answer('not person')}>Not a person</button>
        </div> : <div className="judge-result" aria-live="polite">
          <p><b>Truth:</b> {current.label === 'person' ? 'Person' : 'Not a person'}</p>
          <p><b>Model:</b> {current.predicted === 'person' ? 'Person' : 'Not a person'} · P(person) {modelProbability(current.score)}</p>
          <p><b>Your guess:</b> {guess === 'person' ? 'Person' : 'Not a person'} · {guess === current.label ? 'Correct' : 'Missed this one'}</p>
          <button onClick={next}>Next random crop</button>
        </div>}
        <p className="data-panel-note">{pool.model} · {pool.split} split · recorded model results from the export. This panel does not run new inference.</p>
      </>}
      {pool && !current && <p>All {pool.items.length} crops were tested. Reopen J to start a fresh tally.</p>}
    </DataPanel>
  )
}
