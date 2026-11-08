import { useEffect, useState } from 'react'
import { useSim } from '../store'

// Big one-line announcements over the main view: AFTERSHOCK when part of the building comes
// down, SECONDARY COLLAPSE (Rayan's scripted beat, bigger) and RUBBLE (an R press, smaller, which
// robot), NEW SCENARIO when the building or the survivors change. Judge language, a few seconds,
// then gone; the feed keeps the detail.
const SHOW_MS = 5500

export default function Banner() {
  const banner = useSim((s) => s.banner)
  const [, tick] = useState(0)
  useEffect(() => {
    if (!banner) return
    const id = setTimeout(() => tick((n) => n + 1), Math.max(0, banner.at + (banner.ms ?? SHOW_MS) - Date.now()) + 20)
    return () => clearTimeout(id)
  }, [banner])
  const ms = banner?.ms ?? SHOW_MS
  if (!banner || Date.now() - banner.at > ms) return null
  return (
    <div key={banner.at} className={`banner ${banner.tone ?? 'info'}${banner.size ? ` ${banner.size}` : ''}`} role="status">
      <b>{banner.title}</b>
      {banner.sub && <span>{banner.sub}</span>}
    </div>
  )
}
