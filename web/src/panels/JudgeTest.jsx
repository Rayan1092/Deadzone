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
          ? 'The model test is not available on this run.'
          : `The held-out test set could not load (${response.status}).`)
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
    <DataPanel title="Model test · held-out sample" onClose={() => set({ judgeOpen: false })} className="judge-test">
      <p>Can you spot a person in a real thermal image? Make your guess before the model result and label are revealed.</p>
      <div className="judge-tally" aria-live="polite">
        {tally.rounds ? <><span>Model <b>{tally.model} of {tally.rounds}</b></span><span>You <b>{tally.judge} of {tally.rounds}</b></span></>
          : <span>Make your first guess to start the score</span>}
      </div>
      {loading && <p role="status">Loading a held-out sample…</p>}
      {error && <p role="alert" className="data-panel-note">{error}</p>}
      {!loading && error && <button onClick={() => setReload((n) => n + 1)}>Retry</button>}
      {pool && current && <>
        <figure><img key={current.id} src={current.url} alt="Thermal image to classify"
                     onLoad={() => setImageReady(true)} onError={() => setImageError(true)} />
          <figcaption>Real FLIR thermal frame, same input as the AI (images the model never saw in training)</figcaption>
        </figure>
        {imageError && <p role="alert">This image could not load. No guess or score has been recorded.</p>}
        {guess === null ? <div className="judge-actions">
          <button disabled={!imageReady || imageError} onClick={() => answer('person')}>Person</button>
          <button disabled={!imageReady || imageError} onClick={() => answer('not person')}>Not a person</button>
        </div> : <div className="judge-result" aria-live="polite">
          <p><b>Truth:</b> {current.label === 'person' ? 'Person' : 'Not a person'}</p>
          <p><b>Model:</b> {current.predicted === 'person' ? 'Person' : 'Not a person'} · P(person) {modelProbability(current.score)}</p>
          <p><b>Your guess:</b> {guess === 'person' ? 'Person' : 'Not a person'} · {guess === current.label ? 'Correct' : 'Missed this one'}</p>
          <button onClick={next}>Next image</button>
        </div>}
        <p className="data-panel-note">{pool.model} · the model's answers were recorded when it was tested; this panel shows them, it does not rerun the model.</p>
      </>}
      {pool && !current && <p>All {pool.items.length} images were tested. Reopen J to start a fresh tally.</p>}
    </DataPanel>
  )
}
