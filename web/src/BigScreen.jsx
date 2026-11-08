import { useEffect } from 'react'
import { connectScreen } from './net/socket'
import Pane from './three/Pane'
import { HelpOverlay, RescueStatus, Sidebar, TopBar, useKeyboard } from './panels/Panels'
import { JoinOverlay } from './panels/JoinPanel'
import Toasts from './panels/Toasts'
import Timeline from './panels/Timeline'
import ReportPanel from './panels/ReportPanel'
import AILab from './panels/AILab'
import Intro from './panels/Intro'
import JudgeTest from './panels/JudgeTest'
import UnderHood from './panels/UnderHood'
import { DirectorChip, useDirector } from './panels/Director'
import Banner from './panels/Banner'
import Connection from './panels/Connection'
import { ReplayLoader } from './panels/ReplayPanel'
import { REPLAY } from './net/replay'
import { useSim } from './store'
import { useOpening } from './three/opening'

export default function BigScreen() {
  useEffect(() => (REPLAY ? undefined : connectScreen()), []) // replay plays a file, no server
  useKeyboard()
  useDirector()
  useOpening() // street-level opening shot, dives in on Space
  const view = useSim((s) => s.view)
  const layout = useSim((s) => s.layout)
  return (
    <div className={`app ${layout}`}>
      <TopBar />
      <main className={view === 'gap' ? 'split single' : 'split'}>
        {view === 'gap' ? (
          <Pane which="gap" title="Inside the building" subtitle="Amber: not reported to the command post yet" />
        ) : (
          <>
            <Pane which="reality" title="What's really happening" subtitle="Robots, survivors and radio links" />
            <Pane which="command" title="What the command post knows" subtitle="Only what reached its antenna" />
          </>
        )}
        <RescueStatus />
        <Banner />
        <Connection />
        <Toasts />
        <DirectorChip />
        <ReportPanel />
      </main>
      {/* judge layout: the sidebar and the scheduler slide in from the edges on hover */}
      <div className="side-peek" aria-hidden />
      <Sidebar />
      <div className="time-peek" aria-hidden />
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
