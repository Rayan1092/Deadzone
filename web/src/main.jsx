import React, { useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import './styles.css'
import { connectScreen } from './net/socket'
import Pane from './three/Pane'
import { Sidebar, TopBar, useKeyboard } from './panels/Panels'

function BigScreen() {
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
    </div>
  )
}

function Phone() {
  return <div className="phone">Phone app lands at 5 PM (Person 3). It connects to /ws/phone.</div>
}

const Root = location.pathname.startsWith('/phone') ? Phone : BigScreen
ReactDOM.createRoot(document.getElementById('root')).render(<Root />)
