import { useEffect, useRef, useState } from 'react'
import { fmtClock } from '../format'
import { usePhone } from './store'
import { publicText } from './labels'

// "Ask Gemini" (POST /api/ask). The server answers from Command data only (what reached
// the antenna) and never moves robots. When Gemini is unavailable it says so and gives a
// local summary instead, and the label shows which one answered.
const SUGGESTIONS = ['Where should team 2 go?', 'Which survivor do we reach first?', 'What is still unexplored?']
const MAX_LEN = 1000
const TIMEOUT_MS = 15000
const UNAVAILABLE = {
  disabled: 'Answers are unavailable right now. Here is the latest local summary.',
  missing_key: 'Answers are unavailable right now. Here is the latest local summary.',
  invalid_model: 'Answers are unavailable right now. Here is the latest local summary.',
  timeout: 'The answer took too long. Try again.',
  provider_error: 'An answer is unavailable right now. Try again later.',
  invalid_response: 'A complete answer is unavailable. Try again.',
}

export default function AskCard() {
  const [question, setQuestion] = useState('')
  const [pending, setPending] = useState(null)
  const [answers, setAnswers] = useState([])
  const [error, setError] = useState(null)
  const hello = usePhone((s) => s.hello)
  const draft = usePhone((s) => s.draft)
  const epoch = usePhone((s) => s.hello?.plan_epoch)
  const connected = usePhone((s) => s.connected)
  const active = useRef(null)
  useEffect(() => {
    setAnswers([])
    setError(null)
    setPending(null)
    return () => { active.current?.abort(); active.current = null }
  }, [epoch])

  const ask = async (q) => {
    const text = q.trim().slice(0, MAX_LEN)
    if (!text || pending || active.current || !connected) return
    setPending(text)
    setError(null)
    const ctrl = new AbortController()
    active.current = ctrl
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
        signal: ctrl.signal,
      })
      const body = await res.json().catch(() => ({}))
      if (active.current !== ctrl) return
      if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : body.detail?.msg ?? `Ask failed (${res.status})`)
      setAnswers((a) => [{ q: text, ...body }, ...a].slice(0, 3))
      setQuestion('')
    } catch (err) {
      if (active.current === ctrl) setError(err.name === 'AbortError' ? 'No answer in time. Try again.' : err.message)
    } finally {
      clearTimeout(timer)
      if (active.current === ctrl) { active.current = null; setPending(null) }
    }
  }

  return (
    <section className="m3-card ask-card">
      <div className="card-head">
        <b>Ask about the search</b>
        <span className="muted small">Based on reports received at the command post</span>
      </div>
      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); ask(question) }}>
        <input value={question} maxLength={MAX_LEN} placeholder="Ask about the search…" enterKeyHint="send"
               onChange={(e) => setQuestion(e.target.value)} disabled={!!pending} aria-label="Question about the search" />
        <button type="submit" className="filled" disabled={!connected || !question.trim() || !!pending}>Ask</button>
      </form>
      {!answers.length && !pending && (
        <div className="ask-chips">
          {SUGGESTIONS.map((s) => <button key={s} className="chip-btn" disabled={!connected} onClick={() => ask(s)}>{s}</button>)}
        </div>
      )}
      {pending && (
        <div className="ask-answer pending">
          <div className="ask-q">{pending}</div>
          <div className="muted small">Thinking…</div>
        </div>
      )}
      {error && <div className="ask-error small">{publicText(error, hello, draft)}</div>}
      {!connected && <div className="muted small">Reconnect to ask about this search.</div>}
      {answers.map((a, i) => (
        <div key={i} className="ask-answer">
          <div className="ask-q">{a.q}</div>
          <p>{publicText(a.text, hello, draft)}</p>
          {a.source !== 'gemini' && UNAVAILABLE[a.unavailable_reason] && <p className="ask-error small">{UNAVAILABLE[a.unavailable_reason]}</p>}
          <div className={`ask-source small ${a.source === 'gemini' ? 'gemini' : ''}`}>
            {a.source === 'gemini' ? 'Gemini' : 'Local summary · Gemini unavailable'}
            {a.generated_at != null ? ` · T+${fmtClock(a.generated_at)}` : ''}
          </div>
        </div>
      ))}
    </section>
  )
}
