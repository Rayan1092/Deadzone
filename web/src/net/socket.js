import { useSim, handleMessage } from '../store'
import { REPLAY, recordFrame, replayControl } from './replay'
import { controllerToken, setControllerToken } from './presenter'
import { redactHello } from './leaseState'

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
    sock.onmessage = (e) => {
      // the hello's controller token (control leases on) stays in presenter.js memory: it is
      // taken out before the frame is recorded or reaches the store
      const { msg, token } = redactHello(JSON.parse(e.data))
      if (token) { setControllerToken(token); recordFrame(JSON.stringify(msg)) } else recordFrame(e.data)
      handleMessage(msg)
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
