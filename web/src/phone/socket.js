import { wsUrl } from '../net/socket'
import { usePhone, handlePhoneMessage } from './store'
import { flush } from './plan'

let ws = null

// A stable label keeps plan authorship across reconnects. ?client= overrides it,
// so two tabs on one laptop can act as two phones.
function clientLabel() {
  const fromUrl = new URLSearchParams(location.search).get('client')
  if (fromUrl) return fromUrl
  try {
    let id = localStorage.getItem('dz-client')
    if (!id) {
      id = `phone-${Math.random().toString(36).slice(2, 6)}`
      localStorage.setItem('dz-client', id)
    }
    return id
  } catch {
    return null // storage blocked (private mode): the server assigns a label
  }
}

export function roleFromUrl() {
  const role = new URLSearchParams(location.search).get('role')
  return role === 'planner' || role === 'relay' ? role : null
}

export function connectPhone(role) {
  const client = clientLabel()
  const qs = new URLSearchParams({ role, ...(client ? { client } : {}) })
  let closed = false
  let retry = null
  let socket = null
  let handshake = null
  let failures = 0
  let joined = false
  usePhone.getState().set({ connected: false, connection: 'connecting' })
  const open = () => {
    socket = new WebSocket(wsUrl(`/ws/phone?${qs}`))
    const current = ws = socket
    handshake = setTimeout(() => {
      if (closed || current !== socket) return
      usePhone.getState().set({ connection: 'unreachable' })
      current.close()
    }, 8000)
    socket.onmessage = (e) => {
      if (closed || current !== socket) return
      let msg
      try { msg = JSON.parse(e.data) } catch { return }
      handlePhoneMessage(msg)
      if (msg.t === 'hello') {
        clearTimeout(handshake)
        failures = 0
        joined = true
        usePhone.getState().set({ connected: true, connection: 'live' })
        flush().then(() => {
          // A save may already have been failing when the hello arrived.
          if (!closed && usePhone.getState().pending && usePhone.getState().connected) flush()
        })
      }
    }
    socket.onclose = () => {
      if (closed || current !== socket) return
      clearTimeout(handshake)
      failures++
      usePhone.getState().set({ connected: false,
        connection: usePhone.getState().connection === 'unreachable' || !joined || failures >= 3 ? 'unreachable' : 'reconnecting',
        relayPending: null, relayAction: null })
      retry = setTimeout(open, 1000) // phones drop off Wi-Fi a lot, keep retrying
    }
  }
  open()
  return () => {
    closed = true
    clearTimeout(retry)
    clearTimeout(handshake)
    socket?.close()
    if (ws === socket) ws = null
    usePhone.getState().set({ connected: false, connection: 'connecting', relayPending: null, relayAction: null })
  }
}

export function sendPhone(t, data) {
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({ t, data }))
    return true
  }
  usePhone.getState().set({ error: { code: 'offline', msg: 'Reconnect before sending this control.', at: Date.now() }, relayPending: null })
  return false
}
