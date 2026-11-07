import { useEffect, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { useSim } from '../store'

// The server picks the LAN address phones can reach (or DZ_PUBLIC_URL).
// Retry until it answers, the server may start after the page.
function useJoinLoader() {
  const [error, setError] = useState(null)
  useEffect(() => {
    let stop = false
    let timer
    const load = async () => {
      try {
        const res = await fetch('/api/join')
        const body = await res.json()
        if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Join link unavailable')
        if (!stop) { useSim.getState().set({ joinUrl: body.url }); setError(null) }
      } catch (err) {
        if (stop) return
        setError(err.message || 'Server offline')
        timer = setTimeout(load, 3000)
      }
    }
    load()
    return () => { stop = true; clearTimeout(timer) }
  }, [])
  return error
}

const link = (url, role) => `${url}?role=${role}`

function QR({ value, size }) {
  return <QRCodeSVG value={value} size={size} level="M" marginSize={2} bgColor="#ffffff" fgColor="#14171a" />
}

export function JoinCard() {
  const error = useJoinLoader()
  const url = useSim((s) => s.joinUrl)
  const set = useSim((s) => s.set)
  return (
    <div className="join-card" onClick={() => url && set({ joinOpen: true })}>
      {url ? <QR value={link(url, 'planner')} size={92} /> : <div className="join-qr-empty" />}
      <div className="join-text">
        <b>Plan on your phone</b>
        <span className="muted small">{url ? 'Scan, then draw search zones' : error || 'Loading link'}</span>
        {url && <span className="muted small">Press Q for relay QR</span>}
      </div>
    </div>
  )
}

export function JoinOverlay() {
  const url = useSim((s) => s.joinUrl)
  const open = useSim((s) => s.joinOpen)
  const set = useSim((s) => s.set)
  if (!open || !url) return null
  return (
    <div className="join-overlay" onClick={() => set({ joinOpen: false })}>
      <div className="join-grid">
        <div className="join-big">
          <QR value={link(url, 'planner')} size={280} />
          <b>Plan the search</b>
          <span className="muted">Draw zones, assign robots, run the safety check</span>
        </div>
        <div className="join-big">
          <QR value={link(url, 'relay')} size={280} />
          <b>Be a relay</b>
          <span className="muted">Your phone carries robot data</span>
        </div>
      </div>
      <div className="mono join-url">{url}</div>
      <div className="muted small">Same Wi-Fi as this laptop · Q or Esc to close</div>
    </div>
  )
}
