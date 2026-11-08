import { useEffect, useState } from 'react'
import { useSim } from '../store'

// First glance for someone who has never seen the project: what the screen shows, in three
// lines, over the 3D view. Opens once per browser session (and with the ? key's "How to read
// this" button); closes on click, Esc, or by itself once the robots get going.
const AUTO_CLOSE_MS = 14000

// ?nointro (the demo URL) never opens it by itself; the ? overlay's button still does
const NO_INTRO = (() => { try { return new URLSearchParams(location.search).has('nointro') } catch { return false } })()

function seen() {
  try { return sessionStorage.getItem('dz-intro') === '1' } catch { return false }
}

export default function Intro() {
  const open = useSim((s) => s.introOpen)
  const set = useSim((s) => s.set)
  const view = useSim((s) => s.view)
  useEffect(() => { if (!seen() && !NO_INTRO) set({ introOpen: true }) }, [set])
  const [shownAt, setShownAt] = useState(0)
  useEffect(() => {
    if (!open) return
    setShownAt(Date.now())
    try { sessionStorage.setItem('dz-intro', '1') } catch { /* private mode */ }
    const id = setTimeout(() => useSim.getState().set({ introOpen: false }), AUTO_CLOSE_MS)
    return () => clearTimeout(id)
  }, [open])
  if (!open) return null
  const close = () => set({ introOpen: false })
  return (
    <div className="intro" role="dialog" aria-label="How to read this screen" onClick={close} key={shownAt}>
      <div className="intro-card" onClick={(e) => e.stopPropagation()}>
        <div className="intro-kicker">DEADZONE · how to read this screen</div>
        <h2>Rescue robots that keep working where radio can't reach</h2>
        <ol>
          <li>
            <i className="n">1</i>
            <span><b>Three robots search a collapsed building.</b> Thick walls block radio, so most of the time they can't talk to the command post outside.</span>
          </li>
          <li>
            <i className="n">2</i>
            <span>
              {view === 'gap'
                ? <><b>Amber means "the command post hasn't heard this yet".</b> Robots keep searching anyway and carry their findings until a radio path opens.</>
                : <><b>Left is what's really happening. Right is what the command post knows.</b> The difference is the information still stuck inside the building.</>}
            </span>
          </li>
          <li>
            <i className="n">3</i>
            <span><b>When a robot sees something warm, an onboard AI checks its thermal image</b> (person or not), then the report hops relay to relay to the command post.</span>
          </li>
        </ol>
        <button className="intro-go" onClick={close}>Got it</button>
        <span className="intro-hint">Press ? anytime for the keys</span>
      </div>
    </div>
  )
}
