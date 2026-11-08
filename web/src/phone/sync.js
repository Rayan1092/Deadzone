import { hasPlanContent } from './zones.js'

// Whole-draft last-write-wins saves, ordered before checks and dispatches.
// HTTP acknowledges persistence; the socket broadcasts changes to all viewers.
export async function postJSON(path, data) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 15000)
  try {
    const res = await fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data), signal: ctrl.signal,
    })
    const body = await res.json()
    if (!res.ok) {
      const detail = body.detail
      const error = new Error(typeof detail === 'string' ? detail : detail?.msg ?? `Request failed (${res.status})`)
      error.code = detail?.code ?? 'request'
      throw error
    }
    return body
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('No answer in time. Try again.')
    throw error
  } finally { clearTimeout(timer) }
}

export function createDraftSync(getState, request = postJSON) {
  let flight = null
  async function save() {
    while (getState().pending) {
      const s = getState()
      if (!s.connected || !s.hello || !s.draft) return false
      const draft = s.draft
      const epoch = s.hello.plan_epoch
      const { plan_id, zones, no_go, lost_link_budget_s } = draft
      try {
        await request('/api/plan?check=false', {
          plan_id, zones, no_go, lost_link_budget_s, author: s.hello.client, plan_epoch: epoch,
        })
        const current = getState()
        if (current.hello?.plan_epoch !== epoch) return false
        // Edits made while saving must get their own acknowledged save.
        if (current.draft === draft) current.set({ pending: false, error: null })
      } catch (error) {
        if (getState().hello?.plan_epoch === epoch) {
          getState().set({ error: { code: error.code ?? 'save', msg: error.message, at: Date.now() } })
        }
        return false
      }
    }
    return true
  }
  return () => {
    if (!flight) flight = save().finally(() => { flight = null })
    return flight
  }
}

export function phoneHelloState(s, data, time) {
  const sameIncident = Boolean(data.plan_epoch && data.plan_epoch === s.hello?.plan_epoch)
  const preserve = sameIncident && s.pending
  return {
    hello: data, draft: preserve ? s.draft : data.plan,
    pending: preserve, selected: preserve ? s.selected : null, mode: 'view',
    safety: null, relay: null, relayPending: null, checking: false, error: null, time,
    view: sameIncident ? s.view : null, map: sameIncident ? s.map : null,
    dispatched: data.dispatched_plan_ids ?? (sameIncident ? s.dispatched : []),
    lastDispatch: data.plan && data.dispatched_plan_ids?.includes(data.plan.plan_id)
      ? dispatchInfo(data.plan, data.robots)
      : sameIncident ? s.lastDispatch : null,
  }
}

// Empty drafts are meaningful only as a clear of a previously sent plan.
// A blank new incident still has no implicit plan to send.
export const canSendPlan = (s) => Boolean(s.draft && (hasPlanContent(s.draft) || s.lastDispatch?.hasContent))

function dispatchInfo(draft, robots) {
  return { plan_id: draft.plan_id, hasContent: hasPlanContent(draft), robots: robots?.length ?? 0 }
}

export function dispatchedState(s, planId) {
  return {
    dispatched: [...new Set([...s.dispatched, planId])],
    ...(!s.pending && s.draft?.plan_id === planId ? { lastDispatch: dispatchInfo(s.draft, s.hello?.robots) } : {}),
  }
}
