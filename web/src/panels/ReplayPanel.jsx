import { useEffect, useState } from 'react'
import { useSim } from '../store'
import { fmtClock } from '../format'
import { RECORDING, REPLAY, REPLAY_URL, loadRecording, saveRecording, startReplay } from '../net/replay'

const mb = (n) => `${(n / 1e6).toFixed(1)} MB`

// Top-bar status for ?record and ?replay. Nothing renders in a normal live session.
export function ReplayChip() {
  const recorder = useSim((s) => s.recorder)
  const replay = useSim((s) => s.replay)
  if (RECORDING) {
    return (
      <button className="rec-chip" title="Save the recording (S)" onClick={saveRecording}>
        <i />REC {fmtClock((recorder?.ms ?? 0) / 1000)} · {mb(recorder?.bytes ?? 0)}
      </button>
    )
  }
  if (REPLAY && replay?.loaded) {
    return (
      <span className="replay-chip">
        REPLAY {fmtClock(replay.pos / 1000)}/{fmtClock(replay.dur / 1000)} {replay.rate}x
        {replay.ended ? ' · ended' : replay.playing ? '' : ' · paused'}
      </span>
    )
  }
  return null
}

// Full-screen loader until a recording is playing.
export function ReplayLoader() {
  const loaded = useSim((s) => s.replay?.loaded)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const load = async (source) => {
    setBusy(true)
    setError(null)
    try { startReplay(await loadRecording(source)) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  useEffect(() => { if (REPLAY_URL) load(REPLAY_URL) }, [])
  if (!REPLAY || loaded) return null
  return (
    <div className="replay-loader" onDragOver={(e) => e.preventDefault()}
         onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files[0]) load(e.dataTransfer.files[0]) }}>
      <div className="replay-box">
        <b>Replay mode</b>
        <span className="muted">Plays a recorded run with no server. Drop a <span className="mono">.json.gz</span> recording here.</span>
        <label className="replay-pick">
          {busy ? 'Loading…' : 'Choose recording'}
          <input type="file" accept=".json,.gz,application/json,application/gzip" hidden
                 onChange={(e) => e.target.files[0] && load(e.target.files[0])} />
        </label>
        {error && <span className="replay-error">{error}</span>}
        <span className="muted small">Space pause · Backspace restart · + / − playback speed</span>
      </div>
    </div>
  )
}
