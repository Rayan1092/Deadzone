import { useEffect, useRef, useState } from 'react'
import { useSim } from '../store'
import { REPLAY } from '../net/replay'

// What the screen is waiting for, and what to do about it: first load ("Connecting…"), a dropped
// link ("Reconnecting…"), and after a few seconds of either, the one thing to check. The socket
// retries by itself (net/socket.js); this only says so.
const HINT_AFTER_MS = 6000

export default function Connection() {
  const connected = useSim((s) => s.connected)
  const ever = useRef(false)
  const [since, setSince] = useState(() => Date.now())
  const [, tick] = useState(0)
  if (connected) ever.current = true
  useEffect(() => {
    if (connected) return undefined
    setSince(Date.now())
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [connected])
  if (REPLAY || connected) return null
  const long = Date.now() - since > HINT_AFTER_MS
  return (
    <div className="conn-card" role="status" aria-live="polite">
      <i />
      <b>{ever.current ? 'Connection lost. Reconnecting…' : 'Connecting to the simulation…'}</b>
      {long && (
        <span>{ever.current
          ? 'Still trying. Check that the simulation is running and that this laptop is on the network.'
          : 'This is taking a while. Make sure the simulation is running on this laptop, then reload this page.'}</span>
      )}
    </div>
  )
}
