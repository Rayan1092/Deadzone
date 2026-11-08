import { useEffect, useState } from 'react'
import { useSim } from '../store'
import { cropCaption, cropEntry, sentence, useCropManifest } from '../crops'

const CARD_MS = 9000

// The thermal crop the onboard model judged, with its verdict. Reality shows the
// robot's own decisions (people and rejected hot spots); Command shows a person only
// once the report has been delivered. The model's Grad-CAM (Rayan's export) fades in over
// the crop a moment later: where the model looked to decide.
function Crop({ crop, entry }) {
  const [failed, setFailed] = useState(false)
  const [heatFailed, setHeatFailed] = useState(false)
  if (!crop || failed) return <div className="det-crop empty">thermal</div>
  const heat = !heatFailed && (entry?.heatmap_alpha ?? entry?.heatmap)
  return (
    <div className="det-crop">
      <img src={`/crops/${crop}`} alt="Thermal crop the detector judged" onError={() => setFailed(true)} />
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

// sides: which cards this pane shows, latest of each (the one-view pane shows both).
export default function DetectionCards({ side, sides = [side] }) {
  const all = useSim((s) => s.detections)
  const manifest = useCropManifest()
  const cards = sides.map((sd) => all.filter((c) => c.side === sd).slice(-1)[0]).filter(Boolean)
  useEffect(() => {
    if (!all.length) return
    const oldest = all[0]
    const id = setTimeout(() => {
      const s = useSim.getState()
      s.set({ detections: s.detections.filter((c) => c.eid !== oldest.eid) })
    }, Math.max(0, oldest.at + CARD_MS - Date.now()))
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
              <b>{person ? `Person · ${pct(c.conf)}` : `Not a person · ${pct(c.conf)}`}</b>
              <span className="muted small">
                {person
                  ? `${c.subject}${entry?.pose ? ` · ${entry.pose}` : ''} · seen by ${c.robot}`
                  : `hot spot ${c.subject}${entry?.object ? ` (${entry.object})` : ''} · ${c.robot} · rejected`}
              </span>
              {c.side === 'reality' && person && c.linked === false && (
                <span className="det-warn small">No link, holding the report</span>
              )}
              {c.side === 'command' && c.delay != null && <span className="muted small">arrived {c.delay}s after detection</span>}
              {/* a decoy's image is a stand-in (a hot panel for "radiator"): say what it really shows */}
              <span className="det-caption">{sentence(cropCaption(manifest, entry))}{!person && entry?.shows ? ` Image: ${entry.shows}.` : ''}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
