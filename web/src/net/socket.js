import { useSim, handleMessage } from '../store'

let ws = null

function wsUrl(path) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}

export function connectScreen() {
  const open = () => {
    ws = new WebSocket(wsUrl('/ws/screen'))
    ws.onopen = () => useSim.getState().set({ connected: true })
    ws.onmessage = (e) => handleMessage(JSON.parse(e.data))
    ws.onclose = () => {
      useSim.getState().set({ connected: false })
      setTimeout(open, 1000) // reconnect forever, the server may restart mid demo
    }
  }
  open()
}

export function control(action, value) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ t: 'control', data: { action, value } }))
}
