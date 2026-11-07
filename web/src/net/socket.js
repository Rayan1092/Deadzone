import { useSim, handleMessage } from '../store'
import { REPLAY, recordFrame, replayControl } from './replay'

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
    sock = ws = new WebSocket(wsUrl('/ws/screen'))
    sock.onopen = () => useSim.getState().set({ connected: true })
    sock.onmessage = (e) => { recordFrame(e.data); handleMessage(JSON.parse(e.data)) }
    sock.onclose = () => {
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
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ t: 'control', data: { action, value } }))
}
