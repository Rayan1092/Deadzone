import { useSim, handleMessage } from '../store'
import { RECORDING, REPLAY, recordFrame, replayControl } from './replay'
import { controllerToken, setControllerToken } from './presenter'
import { redactHello } from './leaseState'
import { MapStreamDecoder, recordableFrame } from './mapStream'

let ws = null

export function wsUrl(path) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}

// Returns a cleanup so a remount (hot reload) never leaves a second socket
// feeding every message into the store twice.
export function connectScreen() {
  let closed = false
  let sock = null
  let timer
  const open = () => {
    const decoder = new MapStreamDecoder()
    // Older servers ignore the query; browsers without zlib decoding keep legacy maps.
    const path = typeof DecompressionStream === 'function' ? '/ws/screen?map_deltas=1' : '/ws/screen'
    const connection = sock = ws = new WebSocket(wsUrl(path))
    let pending = Promise.resolve()
    sock.onopen = () => useSim.getState().set({ connected: true })
    sock.onmessage = (e) => {
      // Keep maps, ticks and events in wire order while native zlib decoding is asynchronous.
      pending = pending.then(async () => {
        if (closed || connection !== ws || connection.readyState !== 1) return
        // Strip credentials before decoding/recording or storing the frame.
        const { msg, token } = redactHello(JSON.parse(e.data))
        if (token) setControllerToken(token)
        const decoded = await decoder.decode(msg)
        if (closed || connection !== ws || connection.readyState !== 1) return
        if (RECORDING) recordFrame(JSON.stringify(recordableFrame(decoded)))
        handleMessage(decoded)
      }).catch(() => connection.close(1002, 'Invalid map stream')) // reconnect for a fresh keyframe
    }
    sock.onclose = () => {
      setControllerToken(null) // the server frees this socket's leases on disconnect
      if (closed) return
      useSim.getState().set({ connected: false })
      timer = setTimeout(open, 1000) // reconnect forever, the server may restart mid demo
    }
  }
  open()
  return () => { closed = true; clearTimeout(timer); sock?.close() }
}

export function control(action, value) {
  if (REPLAY) return replayControl(action, value)
  // with control leases on, B and U carry this socket's token (server checks the presenter's leases)
  const token = controllerToken()
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ t: 'control', data: { action, value, ...(token ? { controller_token: token } : {}) } }))
}
