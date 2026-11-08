import { usePhone } from './store'
import { clearAll, flush, removeRegion, setBudget, updateZone } from './plan'
import { unitName } from '../format'

const NONE = []

function ZoneEditor({ zone, robots }) {
  return (
    <div className="editor">
      <div className="field">
        <span className="label">Robot</span>
        <div className="chips">
          {robots.map((r) => (
            <button key={r.id} className={`chip-btn${zone.robot === r.id ? ' on' : ''}`} style={{ '--c': r.color }}
                    onClick={() => updateZone(zone.id, { robot: r.id })}>
              <i className="swatch" />{r.id}
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <span className="label">Priority</span>
        <div className="stepper">
          <button aria-label="Higher priority" disabled={zone.priority <= 1}
                  onClick={() => updateZone(zone.id, { priority: zone.priority - 1 })}>−</button>
          <b>{zone.priority}</b>
          <button aria-label="Lower priority" disabled={zone.priority >= 10}
                  onClick={() => updateZone(zone.id, { priority: zone.priority + 1 })}>+</button>
        </div>
        <span className="muted small">1 is searched first</span>
      </div>
      <div className="field">
        <span className="label">Radio</span>
        <div className="segmented">
          <button className={zone.comms === 'relay' ? 'on' : ''} onClick={() => updateZone(zone.id, { comms: 'relay' })}>
            Keep a relay link
          </button>
          <button className={zone.comms === 'lost_link_ok' ? 'on' : ''} onClick={() => updateZone(zone.id, { comms: 'lost_link_ok' })}>
            Dark is OK
          </button>
        </div>
      </div>
      <button className="text-btn danger" onClick={() => removeRegion(zone.id)}>Delete {zone.id}</button>
    </div>
  )
}

export default function PlanEditor() {
  const draft = usePhone((s) => s.draft)
  const pending = usePhone((s) => s.pending)
  const checking = usePhone((s) => s.checking)
  const lastDispatch = usePhone((s) => s.lastDispatch)
  const connected = usePhone((s) => s.connected)
  const error = usePhone((s) => s.error)
  const mode = usePhone((s) => s.mode)
  const selected = usePhone((s) => s.selected)
  const robots = usePhone((s) => s.hello?.robots ?? NONE)
  const me = usePhone((s) => s.hello?.client)
  const set = usePhone((s) => s.set)
  const zones = draft?.zones ?? NONE
  const noGo = draft?.no_go ?? NONE
  const colors = Object.fromEntries(robots.map((r) => [r.id, r.color]))
  const zone = zones.find((z) => z.id === selected)
  const toggle = (m) => set({ mode: mode === m ? 'view' : m, selected: null })

  return (
    <section className="m3-card plan-card">
      <div className="card-head">
        <b>Search plan {draft?.plan_id ?? ''}</b>
        {draft?.author && draft.author !== me && <span className="muted small">edited by {unitName(draft.author)}</span>}
      </div>

      {draft && <p className="hint" role="status">{pending
        ? !connected ? 'Offline · changes waiting to sync' : error ? 'Changes are not saved. Retry to share them.' : 'Saving your changes…'
        : 'Shared with the main screen and other phones. Check and dispatch to send it to robots.'}</p>}
      {pending && connected && error && <button className="text-btn" onClick={flush}>Retry saving changes</button>}

      <div className="tools">
        <button className={`tool${mode === 'zone' ? ' on' : ''}`} onClick={() => toggle('zone')}>
          <i className="tool-zone" />Add zone
        </button>
        <button className={`tool${mode === 'nogo' ? ' on' : ''}`} onClick={() => toggle('nogo')}>
          <i className="tool-nogo" />Add no-go
        </button>
        <button className="tool danger" disabled={!connected || checking} onClick={clearAll}>Clear all</button>
      </div>
      {mode !== 'view' && (
        <p className="hint">Drag on the map to draw {mode === 'zone' ? 'a search zone' : 'a no-go area'}. Tap the button again to cancel.</p>
      )}
      {mode === 'view' && !zones.length && !noGo.length && (
        <p className="hint">{lastDispatch?.hasContent
          ? 'All regions removed. Use Clear plan to send this change to robots.'
          : 'Draw a search zone on the map and assign a robot to it.'}</p>
      )}

      {[...zones].sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id)).map((z) => (
        <button key={z.id} className={`region-row${z.id === selected ? ' on' : ''}`} style={{ '--c': colors[z.robot] }}
                onClick={() => set({ selected: z.id === selected ? null : z.id })}>
          <i className="swatch" />
          <b>{z.id}</b>
          <span>{z.robot}</span>
          <span className="muted">priority {z.priority}</span>
          <span className="muted">{z.comms === 'lost_link_ok' ? 'dark OK' : 'relay link'}</span>
        </button>
      ))}
      {zone && <ZoneEditor zone={zone} robots={robots} />}

      {noGo.map((g) => (
        <div key={g.id} className={`region-row nogo${g.id === selected ? ' on' : ''}`}>
          <i className="swatch" />
          <b>{g.id}</b>
          <span className="muted">no-go area</span>
          <button className="text-btn danger" onClick={() => removeRegion(g.id)}>Delete</button>
        </div>
      ))}

      {zones.some((z) => z.comms === 'lost_link_ok') && (
        <div className="field budget">
          <span className="label">Dark for up to</span>
          <input type="range" min="0" max="900" step="15" value={draft.lost_link_budget_s}
                 onChange={(e) => setBudget(Number(e.target.value))} />
          <b className="mono">{draft.lost_link_budget_s}s</b>
        </div>
      )}
    </section>
  )
}
