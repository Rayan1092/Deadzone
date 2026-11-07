import { useEffect, useState } from 'react'
import { useSim } from '../store'

const CARD_MS = 9000

// The thermal crop the onboard model judged, with its verdict. Reality shows the
// robot's own decisions (people and rejected hot spots); Command shows a person only
// once the report has been delivered.
function Crop({ crop }) {
  const [failed, setFailed] = useState(false)
  if (!crop || failed) return <div className="det-crop empty">thermal</div>
  return <img className="det-crop" src={`/crops/${crop}`} alt="Thermal crop the detector judged" onError={() => setFailed(true)} />
}

function pct(conf) {
  if (conf == null) return ''
  const v = conf * 100
  return v >= 99.5 || v <= 0.5 ? `${Math.round(v)}%` : `${v.toFixed(1)}%`
}

export default function DetectionCards({ side }) {
  const all = useSim((s) => s.detections)
  const cards = all.filter((c) => c.side === side).slice(-3)
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
      {cards.map((c) => (
        <div key={c.eid} className={`det-card ${c.verdict}`}>
          <Crop crop={c.crop} />
          <div className="det-body">
            <span className="det-kicker">{side === 'command' ? 'Reported to command' : 'Onboard AI detector'}</span>
            <b>{c.verdict === 'person' ? `Person · ${pct(c.conf)}` : `Not a person · ${pct(c.conf)}`}</b>
            <span className="muted small">
              {c.verdict === 'person' ? `${c.subject} · seen by ${c.robot}` : `hot spot ${c.subject} · ${c.robot} · rejected`}
            </span>
            {side === 'reality' && c.verdict === 'person' && c.linked === false && (
              <span className="det-warn small">No link, holding the report</span>
            )}
            {side === 'command' && c.delay != null && <span className="muted small">arrived {c.delay}s after detection</span>}
          </div>
        </div>
      ))}
    </div>
  )
}
