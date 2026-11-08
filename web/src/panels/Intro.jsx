import { useEffect, useState } from 'react'
import { useSim } from '../store'

// The first thing a newcomer reads, in three lines: what this is, what they are looking at, and
// how to start. Opens once per browser session unless "Don't show again" was chosen (or the page
// was opened with ?nointro); the help popup's "What am I looking at?" always opens it. Closes on
// Space (which also starts the mission), a click, Esc, or when the mission starts.
const NO_INTRO = (() => { try { return new URLSearchParams(location.search).has('nointro') } catch { return false } })()

function seen() {
  try { return sessionStorage.getItem('dz-intro') === '1' || localStorage.getItem('dz-intro-off') === '1' } catch { return false }
}

export default function Intro() {
  const open = useSim((s) => s.introOpen)
  const running = useSim((s) => s.running)
  const set = useSim((s) => s.set)
  const view = useSim((s) => s.view)
  const [never, setNever] = useState(() => { try { return localStorage.getItem('dz-intro-off') === '1' } catch { return false } })
  useEffect(() => { if (!seen() && !NO_INTRO) set({ introOpen: true }) }, [set])
  useEffect(() => {
    if (!open) return undefined
    try { sessionStorage.setItem('dz-intro', '1') } catch { /* private mode */ }
    const onKey = (e) => { if (e.code === 'Space') set({ introOpen: false }) } // the key handler starts the mission
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, set])
  useEffect(() => { if (running && useSim.getState().introOpen) set({ introOpen: false }) }, [running, set])
  if (!open) return null
  const close = () => set({ introOpen: false })
  const toggleNever = (e) => {
    const on = e.target.checked
    setNever(on)
    try { localStorage.setItem('dz-intro-off', on ? '1' : '0') } catch { /* private mode */ }
  }
  return (
    <div className="intro" role="dialog" aria-label="What this is" onClick={close}>
      <div className="intro-card" onClick={(e) => e.stopPropagation()}>
        <div className="intro-kicker">Deadzone</div>
        <p className="intro-line lead">Rescue robots that keep searching a collapsed building where radio can't reach, and carry what they find back to the command post.</p>
        <p className="intro-line">
          {view === 'gap'
            ? 'The big view is the building as it really is. The map at the bottom right is only what the command post has heard so far.'
            : 'On the left is the building as it really is. On the right is only what the command post has heard so far.'}
        </p>
        <p className="intro-line go">Press <kbd>Space</kbd> to start the mission.</p>
        <div className="intro-foot">
          <label className="intro-never"><input type="checkbox" checked={never} onChange={toggleNever} />Don't show again</label>
          <span className="intro-hint">Press H for the keys</span>
          <button className="intro-go" onClick={close}>Got it</button>
        </div>
      </div>
    </div>
  )
}
