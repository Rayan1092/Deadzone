import { useEffect, useRef, useState } from 'react'
import { fmtClock } from '../format'
import { usePhone } from './store'

// "Ask Gemini" (POST /api/ask). The server answers from Command data only (what reached
// the antenna) and never moves robots. When Gemini is unavailable it says so and gives a
// local summary instead, and the label shows which one answered.
const SUGGESTIONS = ['Where should team 2 go?', 'Which survivor do we reach first?', 'What is still unexplored?']
const MAX_LEN = 1000
const TIMEOUT_MS = 15000
const UNAVAILABLE = {
  disabled: 'Gemini is turned off on the server.',
  missing_key: 'Gemini needs an API key configured on the server. Ask the operator to finish setup.',
  invalid_model: 'The server’s Gemini model setting needs fixing.',
  timeout: 'Gemini took too long. Try again.',
  provider_error: 'Gemini could not answer. The operator should check the server’s API access and quota.',
  invalid_response: 'Gemini did not return a complete answer grounded in Command data. Try again.',
}

export default function AskCard() {
  const [question, setQuestion] = useState('')
  const [pending, setPending] = useState(null)
  const [answers, setAnswers] = useState([])
  const [error, setError] = useState(null)
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
        <b>Ask Gemini</b>
        <span className="muted small">Answers from Command data only</span>
      </div>
      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); ask(question) }}>
        <input value={question} maxLength={MAX_LEN} placeholder="Ask about the search…" enterKeyHint="send"
               onChange={(e) => setQuestion(e.target.value)} disabled={!!pending} aria-label="Question for Gemini" />
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
      {error && <div className="ask-error small">{error}</div>}
      {!connected && <div className="muted small">Reconnect to ask about this search.</div>}
      {answers.map((a, i) => (
        <div key={i} className="ask-answer">
          <div className="ask-q">{a.q}</div>
          <p>{a.text}</p>
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
