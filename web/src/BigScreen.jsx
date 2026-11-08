import { useEffect } from 'react'
import { connectScreen } from './net/socket'
import Pane from './three/Pane'
import { HelpOverlay, Sidebar, TopBar, useKeyboard } from './panels/Panels'
import { JoinOverlay } from './panels/JoinPanel'
import Toasts from './panels/Toasts'
import Timeline from './panels/Timeline'
import ReportPanel from './panels/ReportPanel'
import AILab from './panels/AILab'
import Intro from './panels/Intro'
import JudgeTest from './panels/JudgeTest'
import UnderHood from './panels/UnderHood'
import { DirectorChip, useDirector } from './panels/Director'
import { ReplayLoader } from './panels/ReplayPanel'
import { REPLAY } from './net/replay'
import { useSim } from './store'

export default function BigScreen() {
  useEffect(() => (REPLAY ? undefined : connectScreen()), []) // replay plays a file, no server
  useKeyboard()
  useDirector()
  const view = useSim((s) => s.view)
  return (
    <div className="app">
      <TopBar />
      <main className={view === 'gap' ? 'split single' : 'split'}>
        {view === 'gap' ? (
          <Pane which="gap" title="Inside the building" subtitle="amber = the command post hasn't heard this yet" />
        ) : (
          <>
            <Pane which="reality" title="What's really happening" subtitle="robots, survivors, radio links" />
            <Pane which="command" title="What the command post knows" subtitle="only what reached its antenna" />
          </>
        )}
        <Toasts />
        <DirectorChip />
        <ReportPanel />
      </main>
      <Sidebar />
      <Timeline />
      <JoinOverlay />
      <ReplayLoader />
      <HelpOverlay />
      <AILab />
      <JudgeTest />
      <UnderHood />
      <Intro />
    </div>
  )
}
