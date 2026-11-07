import { wsUrl } from '../net/socket'
import { usePhone, handlePhoneMessage } from './store'

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
  const open = () => {
    ws = new WebSocket(wsUrl(`/ws/phone?${qs}`))
    ws.onopen = () => usePhone.getState().set({ connected: true })
    ws.onmessage = (e) => handlePhoneMessage(JSON.parse(e.data))
    ws.onclose = () => {
      usePhone.getState().set({ connected: false })
      if (!closed) setTimeout(open, 1000) // phones drop off Wi-Fi a lot, keep retrying
    }
  }
  open()
  return () => { closed = true; ws?.close() }
}

export function sendPhone(t, data) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ t, data }))
}
