import { useSim } from '../store'
import DataPanel from './DataPanel'

const GROUPS = [
  ['Store and forward', [['Held in custody', 'in_flight'], ['Delivered to Command', 'delivered'],
    ['Hops per Command delivery', 'hops_per_delivery'], ['Custody transfers', 'hop_transfers'],
    ['Queued bytes', 'queued_bytes'], ['Simulated bytes transmitted', 'bytes_transmitted']]],
  ['Link repair', [['Bytes corrupted', 'corrupted_bytes'], ['Bytes repaired by Reed-Solomon', 'corrected_bytes'],
    ['FEC blocks that failed', 'fec_failed_blocks'], ['Bundles lost with relays', 'bundles_destroyed']]],
  ['Onboard work', [['Lidar scans', 'lidar_scans'], ['Thermal scans', 'thermal_scans'],
    ['Detector calls', 'detector_calls'], ['Rejected hot spots', 'hotspots_rejected'],
    ['Rescue routes computed', 'rescue_routes_computed'], ['Replans', 'replans']]],
  ['Deadlines and disasters', [['Deadlines met', 'scheduler_deadlines_met'], ['Deadline misses', 'deadline_misses'],
    ['Safety deadline misses', 'safety_deadline_misses'], ['Collapse areas applied', 'aftershock_areas'],
    ['Timeline events played', 'timeline_events_played'], ['Timeline events failed', 'timeline_events_failed']]],
]

export default function UnderHood() {
  const open = useSim((state) => state.hoodOpen)
  const stats = useSim((state) => state.tick?.stats)
  const connected = useSim((state) => state.connected)
  const set = useSim((state) => state.set)
  if (!open) return null
  return <DataPanel title="Under the hood" onClose={() => set({ hoodOpen: false })}>
    <p>{connected ? 'Latest simulator counters' : 'Disconnected · last received counters'} · incident totals reset with the simulation.</p>
    <div className="hood-grid">{GROUPS.map(([title, rows]) => <section key={title}>
      <h3>{title}</h3><dl>{rows.map(([name, key]) => <div key={key}>
        <dt>{name}</dt><dd>{typeof stats?.[key] === 'number' && Number.isFinite(stats[key])
          ? stats[key].toLocaleString(undefined, { maximumFractionDigits: 3 }) : 'Awaiting counter'}</dd>
      </div>)}</dl>
    </section>)}</div>
    <p className="data-panel-note">Measured in simulation. These counters describe system work, not proof of current radio reachability or a guarantee that a rescue route is safe. Missing detector/deadline counters stay marked as awaiting their export.</p>
  </DataPanel>
}
