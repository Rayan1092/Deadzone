import { useEffect } from 'react'
import { useSim } from '../store'
import { describeEvent } from '../format'

const TOAST_MS = 5000
const TONE = {
  survivor_found: 'alert', survivor_reported: 'alert', fault: 'alert', safety_reject: 'alert',
  link_lost: 'warn', rubble_fall: 'warn',
  link_restored: 'ok', relay_dropped: 'info',
}

// Stack over the split view. Each toast removes itself after TOAST_MS.
export default function Toasts() {
  const toasts = useSim((s) => s.toasts)
  useEffect(() => {
    if (!toasts.length) return
    const oldest = toasts[0]
    const id = setTimeout(() => {
      const s = useSim.getState()
      s.set({ toasts: s.toasts.filter((t) => t.eid !== oldest.eid) })
    }, Math.max(0, oldest.at + TOAST_MS - Date.now()))
    return () => clearTimeout(id)
  }, [toasts])
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.eid} className={`toast ${TONE[t.kind] ?? 'info'}`}>
          <i />
          <span>{describeEvent(t)}</span>
        </div>
      ))}
    </div>
  )
}
