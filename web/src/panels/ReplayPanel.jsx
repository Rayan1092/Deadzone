import { useEffect, useState } from 'react'
import { useSim } from '../store'
import { fmtClock } from '../format'
import { RECORDING, REPLAY, REPLAY_URL, loadRecording, saveRecording, startReplay } from '../net/replay'

const mb = (n) => `${(n / 1e6).toFixed(1)} MB`

// Top-bar status for ?record and ?replay. Nothing renders in a normal live session.
export function ReplayChip() {
  const recorder = useSim((s) => s.recorder)
  const replay = useSim((s) => s.replay)
  // Only with ?record in the URL (never otherwise): the recording status and the one way to save it
  // (a .json.gz download, played back with ?replay)
  if (RECORDING) {
    return (
      <span className="rec-group">
        <span className="rec-chip" title="This page is recording the mission"><i />REC {fmtClock((recorder?.ms ?? 0) / 1000)} · {mb(recorder?.bytes ?? 0)}</span>
        <button className="tb-btn rec-save" title="Download the mission recording (.json.gz) to play back later with ?replay" onClick={saveRecording}>Save recording</button>
      </span>
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
        <span className="muted">Plays a saved mission recording on this screen. Drop the recording file here.</span>
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
