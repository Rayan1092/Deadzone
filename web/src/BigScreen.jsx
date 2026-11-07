import { useEffect } from 'react'
import { connectScreen } from './net/socket'
import Pane from './three/Pane'
import { Sidebar, TopBar, useKeyboard } from './panels/Panels'
import { JoinOverlay } from './panels/JoinPanel'

export default function BigScreen() {
  useEffect(() => connectScreen(), [])
  useKeyboard()
  return (
    <div className="app">
      <TopBar />
      <main className="split">
        <Pane which="reality" title="Reality" subtitle="where the robots are and what they found" />
        <Pane which="command" title="Command post knows" subtitle="only what reached the antenna" />
      </main>
      <Sidebar />
      <footer className="timeline muted">Task timeline (Motion, Mapping, Comms, Safety) lands at 10 PM</footer>
      <JoinOverlay />
    </div>
  )
}
