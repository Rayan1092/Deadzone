import { useEffect, useState } from 'react'
import { useSim } from '../store'
import { fmtClock } from '../format'

// Situation briefing from GET /api/report (G key). Built from Command data only.
// Only a briefing the server marks as Gemini is labelled as one.
export async function requestReport() {
  const s = useSim.getState()
  s.set({ report: { loading: true } })
  try {
    const res = await fetch('/api/report')
    if (!res.ok) throw new Error(`report failed (${res.status})`)
    useSim.getState().set({ report: await res.json() }) // also arrives as a `report` message
  } catch (err) {
    useSim.getState().set({ report: { error: err.message } })
  }
}

// Read the briefing aloud on the big screen (G is a key press, so the browser allows it).
// Remembered per browser; markdown symbols are dropped so the voice doesn't read them.
function readSpeak() {
  try { return localStorage.getItem('dz-speak') !== '0' } catch { return true }
}
function speak(text) {
  const synth = window.speechSynthesis
  if (!synth) return
  synth.cancel()
  const u = new SpeechSynthesisUtterance(text.replace(/[*#_`>]/g, '').replace(/\s*\n+\s*/g, '. '))
  u.rate = 1.05
  const voice = synth.getVoices().find((v) => /en[-_](US|GB)/i.test(v.lang) && /natural|premium|enhanced|google/i.test(v.name))
  if (voice) u.voice = voice
  synth.speak(u)
}

export default function ReportPanel() {
  const report = useSim((s) => s.report)
  const set = useSim((s) => s.set)
  const [shown, setShown] = useState(0)
  const [voiceOn, setVoiceOn] = useState(readSpeak)
  const text = report?.text ?? ''
  // Spoken version: the server's short form when it sends one (`short` or `spoken`), else the
  // first three sentences, so the voice never talks over the demo's close (Rayan's ask).
  const spoken = report?.short ?? report?.spoken ?? text.split(/(?<=[.!?])\s+/).slice(0, 3).join(' ')
  useEffect(() => {
    if (spoken && voiceOn) speak(spoken)
    return () => window.speechSynthesis?.cancel()
  }, [spoken, voiceOn])
  const toggleVoice = () => {
    const next = !voiceOn
    setVoiceOn(next)
    try { localStorage.setItem('dz-speak', next ? '1' : '0') } catch { /* private mode */ }
  }
  useEffect(() => {
    setShown(0)
    if (!text) return
    const id = setInterval(() => setShown((n) => (n >= text.length ? n : n + 3)), 16) // typewriter
    return () => clearInterval(id)
  }, [text])
  if (!report) return null
  const gemini = report.source === 'gemini'
  return (
    <div className="report">
      <div className="report-head">
        <b>{gemini ? 'Gemini briefing' : 'Command briefing'}</b>
        <span className="muted small">
          {report.loading ? 'Generating…' : report.error ? 'Unavailable'
            : `${gemini ? 'Gemini' : 'Local summary'} · Command data only · T+${fmtClock(report.generated_at ?? 0)}`}
        </span>
        <button className={`report-voice${voiceOn ? ' on' : ''}`} aria-pressed={voiceOn} onClick={toggleVoice}
                title="Read the briefing aloud">{voiceOn ? 'Voice on' : 'Voice off'}</button>
        <button className="report-close" aria-label="Close briefing" onClick={() => set({ report: null })}>×</button>
      </div>
      {report.error && <p className="muted">{report.error}</p>}
      {text && <pre className="report-text">{text.slice(0, shown)}</pre>}
    </div>
  )
}
