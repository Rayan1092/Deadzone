import { useEffect, useState } from 'react'
import { useSim } from '../store'
import { cropCaption, cropEntry, useCropManifest } from '../crops'

const CARD_MS = 9000

// The thermal crop the onboard model judged, with its verdict. Reality shows the
// robot's own decisions (people, rejected hot spots, and doubtful ones it drives closer to);
// Command shows a person only once the report has been delivered. The model's Grad-CAM
// (Rayan's export) fades in over the crop a moment later: where the model looked to decide.
function Crop({ crop, entry }) {
  const [failed, setFailed] = useState(false)
  const [heatFailed, setHeatFailed] = useState(false)
  if (!crop || failed) return <div className="det-crop empty">thermal</div>
  const heat = !heatFailed && (entry?.heatmap_alpha ?? entry?.heatmap)
  return (
    <div className="det-crop">
      <img src={`/crops/${crop}`} alt="Thermal crop the detector classified" onError={() => setFailed(true)} />
      {heat && <img className="det-heat" src={`/crops/${heat}`} alt="Grad-CAM: where the model looked" onError={() => setHeatFailed(true)} />}
      {heat && <span className="det-heat-tag">where the AI looked</span>}
    </div>
  )
}

function pct(conf) {
  if (conf == null) return ''
  const v = conf * 100
  return v >= 99.5 || v <= 0.5 ? `${Math.round(v)}%` : `${v.toFixed(1)}%`
}

function headline(c) {
  if (c.verdict === 'unsure') return c.say ?? `AI unsure · ${pct(c.conf)}, moving closer`
  return c.verdict === 'person' ? `Person · ${pct(c.conf)}` : `Not a person · ${pct(c.conf)}`
}

function subline(c, entry) {
  const what = `hot spot ${c.subject}${entry?.object ? ` (${entry.object})` : ''}`
  if (c.verdict === 'unsure') return `${what} · ${c.robot} · driving in for a close-up`
  return c.verdict === 'person' ? `${c.subject} · seen by ${c.robot}` : `${what} · ${c.robot} · rejected`
}

// sides: which cards this pane shows, latest of each (the one-view pane shows both).
export default function DetectionCards({ side, sides = [side] }) {
  const all = useSim((s) => s.detections)
  const manifest = useCropManifest()
  const cards = sides.map((sd) => all.filter((c) => c.side === sd).slice(-1)[0]).filter(Boolean)
  useEffect(() => {
    if (!all.length) return
    const end = (c) => c.at + (c.ttl ?? CARD_MS)
    const id = setTimeout(() => {
      const s = useSim.getState()
      const now = Date.now()
      s.set({ detections: s.detections.filter((c) => end(c) > now) })
    }, Math.max(0, Math.min(...all.map(end)) - Date.now()))
    return () => clearTimeout(id)
  }, [all])
  if (!cards.length) return null
  return (
    <div className="det-cards">
      {cards.map((c) => {
        const entry = cropEntry(manifest, c.crop)
        const person = c.verdict === 'person'
        return (
          <div key={c.eid} className={`det-card ${c.verdict}`}>
            <Crop crop={c.crop} entry={entry} />
            <div className="det-body">
              <span className="det-kicker">{c.side === 'command' ? 'Reported to command' : 'Onboard AI detector'}</span>
              <b>{headline(c)}</b>
              <span className="muted small">{subline(c, entry)}</span>
              {c.side === 'reality' && c.confFar != null && (
                <span className="det-closer small">
                  {c.closer
                    ? `unsure ${pct(c.confFar)} from afar → ${person ? 'person' : 'not a person'} ${pct(c.conf)} up close`
                    : `unsure ${pct(c.confFar)} · could not get close, decided from afar`}
                </span>
              )}
              {c.side === 'reality' && person && c.linked === false && (
                <span className="det-warn small">No link, holding the report</span>
              )}
              {c.side === 'command' && c.delay != null && <span className="muted small">arrived {c.delay}s after detection</span>}
              {/* what the real image shows (a decoy's is a stand-in: a hot panel for "radiator"), then what it is */}
              {entry?.shows && <span className="det-shows">{entry.shows}</span>}
              <span className="det-caption">{cropCaption(manifest, entry)}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
