import { usePhone } from './store'
import { RULE_LABEL, checkPlan, commit, dispatchPlan, updateZone } from './plan'

// Check → (fix) → dispatch. A pass is never stored as approval: dispatch rechecks
// against the latest delivered Command knowledge and can still be rejected.
export default function SafetyCard() {
  const draft = usePhone((s) => s.draft)
  const safety = usePhone((s) => s.safety)
  const checking = usePhone((s) => s.checking)
  const dispatched = usePhone((s) => s.dispatched)
  if (!draft?.zones.length) return null

  const result = safety?.plan_id === draft.plan_id ? safety : null
  const robots = [...new Set(draft.zones.map((z) => z.robot))].sort().join(', ')

  if (dispatched.includes(draft.plan_id)) {
    return (
      <section className="m3-card safety sent">
        <b>{draft.plan_id} dispatched to {robots}</b>
        <span className="muted small">Sent through the network. Each robot starts once the plan reaches it.</span>
        <button className="text-btn" onClick={() => commit(() => {})}>Edit as a new plan</button>
      </section>
    )
  }

  if (result?.ok) {
    return (
      <section className="m3-card safety pass">
        <b>Safety check passed</b>
        <span className="muted small">Battery, reach, no-go and radio all check out for {robots}.</span>
        <div className="actions">
          <button className="filled" disabled={checking} onClick={dispatchPlan}>
            {checking ? 'Dispatching…' : `Dispatch ${draft.plan_id}`}
          </button>
          <button className="text-btn" disabled={checking} onClick={checkPlan}>Check again</button>
        </div>
      </section>
    )
  }

  if (result) {
    return (
      <section className="m3-card safety fail">
        <b>Safety check failed</b>
        {result.violations.map((v, i) => (
          <div key={i} className="violation">
            <div><b>{RULE_LABEL[v.rule] ?? v.rule}</b> <span className="muted">{v.robot} · {v.zone}</span></div>
            <div className="small">{v.msg}</div>
            {v.rule === 'comms_plan' && (
              <button className="text-btn" onClick={() => updateZone(v.zone, { comms: 'lost_link_ok' })}>
                Allow {v.zone} to go dark
              </button>
            )}
          </div>
        ))}
        <div className="actions">
          <button className="filled" disabled={checking} onClick={checkPlan}>{checking ? 'Checking…' : 'Check again'}</button>
        </div>
      </section>
    )
  }

  return (
    <section className="m3-card safety">
      <b>Ready to check {draft.plan_id}</b>
      <span className="muted small">The command post checks battery, reach, no-go areas and radio coverage from what it knows.</span>
      <div className="actions">
        <button className="filled" disabled={checking} onClick={checkPlan}>{checking ? 'Checking…' : 'Run safety check'}</button>
      </div>
    </section>
  )
}
