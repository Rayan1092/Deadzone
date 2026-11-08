import { useEffect } from 'react'
import { useSim } from '../store'
import { describeEvent } from '../format'

// One headline at a time: the most important live event wins (newest on a tie), so a
// survivor reaching Command is never bumped by link chatter. Everything is in the feed.
const RANK = {
  survivor_reported: 6, aftershock: 6, relay_destroyed: 5, control_error: 4, survivor_found: 5, rescue_route_reported: 5, safety_reject: 5,
  fault: 4, mode_changed: 4, plan_dispatched: 3, plan_applied: 3, resumed: 3, relay_power: 3,
  rescue_route: 2, rubble_fall: 2, link_lost: 2, link_restored: 2, relay_dropped: 1,
}
const TONE = {
  survivor_found: 'alert', survivor_reported: 'alert', aftershock: 'alert', relay_destroyed: 'alert', control_error: 'warn', fault: 'alert', safety_reject: 'alert',
  link_lost: 'warn', rubble_fall: 'warn', rescue_route: 'route', rescue_route_reported: 'route',
  link_restored: 'ok', mode_changed: 'warn', plan_dispatched: 'ok', plan_applied: 'ok', resumed: 'ok',
}
const rank = (t) => RANK[t.kind] ?? 1
const lifetime = (t) => (rank(t) >= 5 ? 6000 : 4000)

export default function Toasts() {
  const toasts = useSim((s) => s.toasts)
  useEffect(() => {
    if (!toasts.length) return
    const next = Math.min(...toasts.map((t) => t.at + lifetime(t)))
    const id = setTimeout(() => {
      const s = useSim.getState()
      const now = Date.now()
      s.set({ toasts: s.toasts.filter((t) => t.at + lifetime(t) > now) })
    }, Math.max(0, next - Date.now()))
    return () => clearTimeout(id)
  }, [toasts])
  const head = toasts.reduce((best, t) => (!best || rank(t) >= rank(best) ? t : best), null)
  if (!head) return null
  const tone = head.kind === 'relay_power' ? (head.on ? 'ok' : 'warn') : TONE[head.kind] ?? 'info'
  return (
    <div className="toasts">
      <div key={head.eid} className={`toast headline ${tone}`}>
        <i />
        <span>{describeEvent(head)}</span>
      </div>
    </div>
  )
}
