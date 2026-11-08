import { useEffect, useState } from 'react'
import { useSim } from '../store'
import { AI_CAPTION, fmtClock } from '../format'
import { cropCaption, cropEntry, sentence } from '../crops'

// AI Lab (key L): how the onboard person detector was trained and how it scores, plus the
// crop a robot just judged with its Grad-CAM. Static ML evidence comes from Rayan's exports,
// served read-only by the backend at /ai-lab (DZ_AI_LAB=1): results/metrics.json now,
// results/lab.json (curve, examples) when exported. Nothing here is invented: a panel whose
// data isn't served stays hidden or says where it comes from.
const NONE = []
const TRAIN = '#0d9488' // validated pair on the dark surface (dataviz validate_palette)
const VAL = '#d97706'

async function getJson(url) {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

function useLabData(open) {
  const [data, setData] = useState({ loaded: false })
  useEffect(() => {
    if (!open || data.loaded) return
    Promise.all([getJson('/ai-lab/results/metrics.json'), getJson('/ai-lab/results/lab.json'), getJson('/crops/manifest.json')])
      .then(([metrics, lab, crops]) => setData({ loaded: true, metrics: lab?.metrics ? { ...metrics, ...lab.metrics } : metrics, lab, crops }))
  }, [open, data.loaded])
  return data
}

const pct = (v, digits = 1) => `${(v * 100).toFixed(digits)}%`

function Stats({ m }) {
  const tiles = [['Accuracy', m.accuracy], ['Precision', m.precision], ['Recall', m.recall], ['F1', m.f1]].filter(([, v]) => v != null)
  return (
    <div className="lab-stats">
      {tiles.map(([k, v]) => (
        <div key={k} className="lab-stat"><b>{pct(v)}</b><span>{k}</span></div>
      ))}
    </div>
  )
}

// Second test set (Rayan's lab.json `metrics_indoor`): real indoor thermal frames of people
// lying, sitting and standing, the poses a survivor is found in. Shown only when exported.
function Indoor({ mi }) {
  return (
    <div className="lab-indoor">
      <b>{pct(mi.accuracy)}</b>
      <span>
        on real indoor thermal people lying, sitting or standing
        <small>{mi.n_test?.toLocaleString()} held-out frames{mi.recall != null ? ` · recall ${pct(mi.recall)}` : ''}{mi.precision != null ? ` · precision ${pct(mi.precision)}` : ''}</small>
      </span>
    </div>
  )
}

// 2x2 confusion matrix: cells shaded by count (one hue), counts in text ink.
function Confusion({ c }) {
  const cells = [
    ['person', 'person', c.tp, 'correct'], ['person', 'not person', c.fn, 'missed'],
    ['not person', 'person', c.fp, 'false alarm'], ['not person', 'not person', c.tn, 'correct'],
  ]
  const max = Math.max(c.tp, c.fn, c.fp, c.tn)
  return (
    <div className="lab-confusion" role="table" aria-label="Confusion matrix">
      <span className="lab-axis y">True label</span>
      <span className="lab-axis x">Predicted</span>
      <span className="cm-h c1">person</span><span className="cm-h c2">not person</span>
      <span className="cm-h r1">person</span><span className="cm-h r2">not person</span>
      {cells.map(([t, p, n, what], i) => (
        <div key={i} className={`cm-cell p${i}`} role="cell" title={`True ${t}, predicted ${p}: ${n} (${what})`}
             style={{ '--a': 0.12 + 0.6 * (n / max) }}>
          <b>{n}</b><span>{what}</span>
        </div>
      ))}
    </div>
  )
}

// One measure per chart (loss and accuracy have different scales: never two y-axes).
function Curve({ curve, keys, title, fmt }) {
  const [hover, setHover] = useState(null)
  const W = 260
  const H = 120
  const pad = { l: 34, r: 34, t: 10, b: 20 }
  const vals = curve.flatMap((d) => keys.map(([k]) => d[k])).filter((v) => v != null)
  if (!vals.length) return null
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const x = (i) => pad.l + (i / Math.max(1, curve.length - 1)) * (W - pad.l - pad.r)
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo || 1)) * (H - pad.t - pad.b)
  const line = (k) => curve.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d[k]).toFixed(1)}`).join('')
  const last = curve[curve.length - 1]
  return (
    <figure className="lab-curve">
      <figcaption>{title}<span className="lab-legend">{keys.map(([k, color, label]) => <span key={k}><i style={{ background: color }} />{label}</span>)}</span></figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}
           onMouseMove={(e) => {
             const r = e.currentTarget.getBoundingClientRect()
             const px = ((e.clientX - r.left) / r.width) * W
             setHover(Math.max(0, Math.min(curve.length - 1, Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (curve.length - 1)))))
           }}>
        <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} className="lab-axisline" />
        <text x={pad.l - 4} y={y(hi) + 3} textAnchor="end" className="lab-tick">{fmt(hi)}</text>
        <text x={pad.l - 4} y={y(lo) + 3} textAnchor="end" className="lab-tick">{fmt(lo)}</text>
        <text x={pad.l} y={H - 6} className="lab-tick">epoch {curve[0].epoch}</text>
        <text x={W - pad.r} y={H - 6} textAnchor="end" className="lab-tick">{last.epoch}</text>
        {keys.map(([k, color]) => <path key={k} d={line(k)} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />)}
        {keys.map(([k, color, label]) => (
          <text key={`l${k}`} x={x(curve.length - 1) + 4} y={y(last[k]) + 3} className="lab-direct">{label}</text>
        ))}
        {hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} className="lab-cross" />
            {keys.map(([k, color]) => <circle key={k} cx={x(hover)} cy={y(curve[hover][k])} r="4" fill={color} stroke="#14181c" strokeWidth="2" />)}
          </g>
        )}
      </svg>
      {hover != null && (
        <div className="lab-tip">
          Epoch {curve[hover].epoch}: {keys.map(([k, color, label]) => (
            <span key={k}><i style={{ background: color }} />{label} {fmt(curve[hover][k])}</span>
          ))}
        </div>
      )}
    </figure>
  )
}

function Live({ crops }) {
  const events = useSim((s) => s.events)
  const last = events.find((e) => e.kind === 'survivor_found' || e.kind === 'hotspot_rejected' || e.kind === 'hotspot_unsure')
  const [heat, setHeat] = useState(true)
  if (!last) return <div className="lab-live empty muted">Waiting for a robot to classify a hot spot…</div>
  const person = last.kind === 'survivor_found'
  const unsure = last.kind === 'hotspot_unsure'
  const entry = cropEntry(crops, last.crop)
  // transparent overlay first, so the toggle shows the crop with and without it
  const heatmap = entry?.heatmap_alpha ?? last.heatmap
  return (
    <div className="lab-live">
      <div className="lab-crop">
        {last.crop ? <img src={`/crops/${last.crop}`} alt="Thermal image the robot classified" /> : <div className="crop-ph">thermal</div>}
        {heat && heatmap && <img className="lab-heat" src={`/crops/${heatmap}`} alt="Grad-CAM: where the model looked" />}
      </div>
      <div className="lab-live-text">
        <span className="muted small">Just classified onboard · {last.robot} · T+{fmtClock(last.time ?? 0)}</span>
        {entry?.shows && <span className="det-shows">{entry.shows}</span>}
        <span className="det-caption">{cropCaption(crops, entry)}</span>
        <b className={person ? 'yes' : unsure ? 'unsure' : 'no'}>
          {unsure ? 'Unsure' : person ? 'Person' : 'Not a person'} · {pct(last.conf ?? (person ? 1 : 0), last.conf > 0 && last.conf < 0.01 ? 1 : 0)}
        </b>
        <span className="muted small">
          {unsure ? `Hot spot ${last.id}: moving closer for a second look`
            : person ? `Survivor ${last.survivor}` : `Hot spot ${last.id}${entry?.object ? ` (${entry.object})` : ''}, rejected`}
          {last.looked_closer && last.conf_far != null ? ` · unsure ${pct(last.conf_far, 0)} from afar, classified again up close` : ''}
        </span>
        {heatmap && (
          <label className="lab-toggle">
            <input type="checkbox" checked={heat} onChange={(e) => setHeat(e.target.checked)} />
            Grad-CAM: where the model looked
          </label>
        )}
      </div>
    </div>
  )
}

function Examples({ lab, crops }) {
  if (lab?.examples?.length) {
    return (
      <section className="lab-examples">
        <h4>Training examples</h4>
        <p className="det-caption">{sentence(lab.examples[0].caption ?? AI_CAPTION)} Held-out: the model never trained on these; misses are kept on purpose.</p>
        <div className="lab-grid">
          {lab.examples.slice(0, 24).map((ex) => (
            <figure key={ex.file} className={ex.label === ex.predicted ? '' : 'wrong'}>
              <img src={`/ai-lab/results/${ex.file}`} alt={`${ex.label} example`} loading="lazy" />
              <figcaption>{ex.label}{ex.pose ? ` · ${ex.pose}` : ''}{ex.conf != null ? ` · ${pct(ex.conf, 0)}` : ''}</figcaption>
            </figure>
          ))}
        </div>
      </section>
    )
  }
  const list = crops?.crops ?? NONE
  if (!list.length) return null
  return (
    <section className="lab-examples">
      <h4>Thermal images in this building</h4>
      <div className="lab-grid">
        {list.map((c) => (
          <figure key={c.file}>
            <img src={`/crops/${c.file}`} alt={`${c.label} thermal image`} loading="lazy" />
            <figcaption><b>{c.id} · {c.object ?? c.label}</b>Model: {c.predicted ?? c.label} {pct(c.conf, c.conf > 0 && c.conf < 0.01 ? 1 : 0)}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  )
}

export default function AILab() {
  const open = useSim((s) => s.labOpen)
  const set = useSim((s) => s.set)
  const { loaded, metrics, lab, crops } = useLabData(open)
  if (!open) return null
  const m = metrics
  const model = lab?.model?.name ?? m?.arch?.replace(/_/g, ' ')
  const curve = lab?.curve?.length > 1 ? lab.curve : null
  return (
    <div className="lab-backdrop" onClick={() => set({ labOpen: false })}>
      <div className="lab" role="dialog" aria-label="Model Lab" onClick={(e) => e.stopPropagation()}>
        <header className="lab-head">
          <div>
            <b>Model Lab</b>
            <span className="muted">
              Onboard person detector{model ? ` · ${model}` : ''} · classifies thermal images on the robot, no signal needed
            </span>
          </div>
          <button className="report-close" aria-label="Close Model Lab" onClick={() => set({ labOpen: false })}>×</button>
        </header>
        <div className="lab-body">
          <section className="lab-col">
            <h4>Live</h4>
            <Live crops={crops} />
            <Examples lab={lab} crops={crops} />
          </section>
          <section className="lab-col">
            <h4>Held-out test{m?.n ? ` · ${m.n.toLocaleString()} FLIR images` : ''}{m?.threshold != null ? ` · threshold ${m.threshold}` : ''}</h4>
            {m ? (
              <>
                <Stats m={m} />
                {lab?.metrics_indoor?.accuracy != null && <Indoor mi={lab.metrics_indoor} />}
                {m.confusion && <Confusion c={m.confusion} />}
              </>
            ) : (
              <p className="muted small">{loaded ? 'Test results not served: start the server with DZ_AI_LAB=1.' : 'Loading…'}</p>
            )}
            {!curve && lab && (
              <p className="muted small lab-note">Training curve pending{lab.curve_note ? `: ${lab.curve_note}` : ''}</p>
            )}
            {curve && (
              <div className="lab-curves">
                <Curve curve={curve} title="Loss" fmt={(v) => v.toFixed(2)}
                       keys={[['train_loss', TRAIN, 'train'], ['val_loss', VAL, 'val']]} />
                <Curve curve={curve} title="Accuracy" fmt={(v) => pct(v, 0)}
                       keys={[['train_acc', TRAIN, 'train'], ['val_acc', VAL, 'val']]} />
              </div>
            )}
            {/* where the curve comes from (e.g. a logged retrain with the same recipe) */}
            {curve && lab.curve_note && <p className="muted small lab-note">{lab.curve_note}</p>}
          </section>
        </div>
      </div>
    </div>
  )
}
