import { useEffect } from 'react'
import { connectScreen } from './net/socket'
import Pane from './three/Pane'
import { HelpOverlay, Sidebar, TopBar, useKeyboard } from './panels/Panels'
import { JoinOverlay } from './panels/JoinPanel'
import Toasts from './panels/Toasts'
import Timeline from './panels/Timeline'
import ReportPanel from './panels/ReportPanel'
import { ReplayLoader } from './panels/ReplayPanel'
import { REPLAY } from './net/replay'
import { useSim } from './store'

export default function BigScreen() {
  useEffect(() => (REPLAY ? undefined : connectScreen()), []) // replay plays a file, no server
  useKeyboard()
  const view = useSim((s) => s.view)
  return (
    <div className="app">
      <TopBar />
      <main className={view === 'gap' ? 'split single' : 'split'}>
        {view === 'gap' ? (
          <Pane which="gap" title="Reality" subtitle="amber is what the command post hasn't heard yet" />
        ) : (
          <>
            <Pane which="reality" title="Reality" subtitle="where the robots are and what they found" />
            <Pane which="command" title="Command post knows" subtitle="what reached the antenna" />
          </>
        )}
        <Toasts />
        <ReportPanel />
      </main>
      <Sidebar />
      <Timeline />
      <JoinOverlay />
      <ReplayLoader />
      <HelpOverlay />
    </div>
  )
}
