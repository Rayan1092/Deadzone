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

export default function ReportPanel() {
  const report = useSim((s) => s.report)
  const set = useSim((s) => s.set)
  const [shown, setShown] = useState(0)
  const text = report?.text ?? ''
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
        <button className="report-close" aria-label="Close briefing" onClick={() => set({ report: null })}>×</button>
      </div>
      {report.error && <p className="muted">{report.error}</p>}
      {text && <pre className="report-text">{text.slice(0, shown)}</pre>}
    </div>
  )
}
