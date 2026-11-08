import { useEffect, useState } from 'react'
import { useSim } from '../store'

// Big one-line announcements over the main view: AFTERSHOCK when part of the building comes
// down, NEW SCENARIO when the building or the survivors change. Judge language, a few seconds,
// then gone; the feed keeps the detail.
const SHOW_MS = 5500

export default function Banner() {
  const banner = useSim((s) => s.banner)
  const [, tick] = useState(0)
  useEffect(() => {
    if (!banner) return
    const id = setTimeout(() => tick((n) => n + 1), Math.max(0, banner.at + SHOW_MS - Date.now()) + 20)
    return () => clearTimeout(id)
  }, [banner])
  if (!banner || Date.now() - banner.at > SHOW_MS) return null
  return (
    <div key={banner.at} className={`banner ${banner.tone ?? 'info'}`} role="status">
      <b>{banner.title}</b>
      {banner.sub && <span>{banner.sub}</span>}
    </div>
  )
}
