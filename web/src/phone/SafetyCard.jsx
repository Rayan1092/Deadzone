import { usePhone } from './store'
import { RULE_LABEL, checkPlan, commit, dispatchPlan, updateZone } from './plan'
import { hasPlanContent } from './zones'
import { canSendPlan } from './sync'

// Check → (fix) → dispatch. A pass is never stored as approval: dispatch rechecks
// against the latest delivered Command knowledge and can still be rejected.
export default function SafetyCard() {
  const draft = usePhone((s) => s.draft)
  const safety = usePhone((s) => s.safety)
  const checking = usePhone((s) => s.checking)
  const connected = usePhone((s) => s.connected)
  const dispatched = usePhone((s) => s.dispatched)
  const lastDispatch = usePhone((s) => s.lastDispatch)
  // An acknowledged clear stays visible even though the draft has no regions.
  if (draft && !hasPlanContent(draft) && lastDispatch?.plan_id === draft.plan_id && !lastDispatch.hasContent) {
    return (
      <section className="m3-card safety sent" role="status">
        <b>Cleared, sent to {lastDispatch.robots} robots</b>
        <span className="muted small">Sent through the network. Each robot applies it when it arrives.</span>
      </section>
    )
  }
  if (!canSendPlan({ draft, lastDispatch })) return null
  if (!hasPlanContent(draft)) {
    return (
      <section className="m3-card safety">
        <b>Ready to clear the plan</b>
        <span className="muted small">Send the empty plan so robots learn the no-go areas are gone.</span>
        <button className="filled" disabled={!connected || checking} onClick={dispatchPlan}>
          {checking ? 'Clearing...' : 'Clear plan'}
        </button>
      </section>
    )
  }

  const result = safety?.plan_id === draft.plan_id ? safety : null
  const robots = [...new Set(draft.zones.map((z) => z.robot))].sort().join(', ') || 'every robot'

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
          <button className="filled" disabled={!connected || checking} onClick={dispatchPlan}>
            {checking ? 'Dispatching…' : `Dispatch ${draft.plan_id}`}
          </button>
          <button className="text-btn" disabled={!connected || checking} onClick={checkPlan}>Check again</button>
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
              <>
                <div className="small muted">Let {v.robot} go dark there: it keeps searching and reports when it is back in range.</div>
                {/* one tap: change the zone and run the check again, so the fix is visible */}
                <button className="filled tonal" disabled={!connected || checking}
                        onClick={() => { updateZone(v.zone, { comms: 'lost_link_ok' }); checkPlan() }}>
                  Allow {v.zone} to go dark and check again
                </button>
              </>
            )}
          </div>
        ))}
        <div className="actions">
          <button className="filled" disabled={!connected || checking} onClick={checkPlan}>{checking ? 'Checking…' : 'Check again'}</button>
        </div>
      </section>
    )
  }

  return (
    <section className="m3-card safety">
      <b>Ready to check {draft.plan_id}</b>
      <span className="muted small">The command post checks battery, reach, no-go areas and radio coverage from what it knows.</span>
      <div className="actions">
        <button className="filled" disabled={!connected || checking} onClick={checkPlan}>{checking ? 'Checking…' : 'Run safety check'}</button>
      </div>
    </section>
  )
}
