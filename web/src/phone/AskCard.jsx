import { useState } from 'react'
import { fmtClock } from '../format'

// "Ask Gemini" (POST /api/ask). The server answers from Command data only (what reached
// the antenna) and never moves robots. When Gemini is unavailable it says so and gives a
// local summary instead, and the label shows which one answered.
const SUGGESTIONS = ['Where should team 2 go?', 'Which survivor do we reach first?', 'What is still unexplored?']
const MAX_LEN = 1000
const TIMEOUT_MS = 15000

export default function AskCard() {
  const [question, setQuestion] = useState('')
  const [pending, setPending] = useState(null)
  const [answers, setAnswers] = useState([])
  const [error, setError] = useState(null)

  const ask = async (q) => {
    const text = q.trim().slice(0, MAX_LEN)
    if (!text || pending) return
    setPending(text)
    setError(null)
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
        signal: ctrl.signal,
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail?.msg ?? `Ask failed (${res.status})`)
      setAnswers((a) => [{ q: text, ...body }, ...a].slice(0, 3))
      setQuestion('')
    } catch (err) {
      setError(err.name === 'AbortError' ? 'No answer in time. Try again.' : err.message)
    } finally {
      clearTimeout(timer)
      setPending(null)
    }
  }

  return (
    <section className="m3-card ask-card">
      <div className="card-head">
        <b>Ask Gemini</b>
        <span className="muted small">Answers from Command data only</span>
      </div>
      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); ask(question) }}>
        <input value={question} maxLength={MAX_LEN} placeholder="Ask about the search…" enterKeyHint="send"
               onChange={(e) => setQuestion(e.target.value)} disabled={!!pending} aria-label="Question for Gemini" />
        <button type="submit" className="filled" disabled={!question.trim() || !!pending}>Ask</button>
      </form>
      {!answers.length && !pending && (
        <div className="ask-chips">
          {SUGGESTIONS.map((s) => <button key={s} className="chip-btn" onClick={() => ask(s)}>{s}</button>)}
        </div>
      )}
      {pending && (
        <div className="ask-answer pending">
          <div className="ask-q">{pending}</div>
          <div className="muted small">Thinking…</div>
        </div>
      )}
      {error && <div className="ask-error small">{error}</div>}
      {answers.map((a, i) => (
        <div key={i} className="ask-answer">
          <div className="ask-q">{a.q}</div>
          <p>{a.text}</p>
          <div className={`ask-source small ${a.source === 'gemini' ? 'gemini' : ''}`}>
            {a.source === 'gemini' ? 'Gemini' : 'Local summary · Gemini unavailable'}
            {a.generated_at != null ? ` · T+${fmtClock(a.generated_at)}` : ''}
          </div>
        </div>
      ))}
    </section>
  )
}
