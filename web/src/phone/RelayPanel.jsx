import { usePhone } from './store'
import { sendPhone } from './socket'
import { robotName } from './labels'

// This phone is a radio relay in the sim. Turning it off breaks real links;
// robots and relays keep their bundles until a path comes back.
const MAX_SHOWN = 4

function bars(rssi) {
  return rssi > -60 ? 4 : rssi > -70 ? 3 : rssi > -80 ? 2 : 1
}

function label(id, robots) {
  if (id === 'CMD') return 'Command post'
  if (/^R\d+$/.test(id)) return robotName(id, robots)
  return 'Radio relay'
}

export default function RelayPanel() {
  const robots = usePhone((s) => s.hello?.robots)
  const relay = usePhone((s) => s.relay)
  const connected = usePhone((s) => s.connected)
  const relayId = usePhone((s) => s.hello?.relay_id)
  const pending = usePhone((s) => s.relayPending)
  const mode = usePhone((s) => s.mode)
  const set = usePhone((s) => s.set)
  if (!relay) {
    return (
      <section className="m3-card relay-card">
        <b>{relayId ? 'Joining the radio network...' : 'Connecting your relay…'}</b>
      </section>
    )
  }
  const on = pending ?? relay.on
  const toggle = () => {
    set({ relayPending: !on, relayAction: { kind: 'power', on: !on } })
    sendPhone('relay_power', { on: !on })
  }
  const neighbors = [...relay.neighbors].sort((a, b) => b.rssi - a.rssi)
  return (
    <section className="m3-card relay-card">
      <div className="relay-head">
        <div>
          <span className="muted small">This phone is</span>
          <div className="relay-id">Your radio relay</div>
        </div>
        <span className={`chip ${relay.on ? 'ok' : 'bad'}`}>{relay.on ? 'On air' : 'Off'}</span>
      </div>

      <button className={`power${on ? ' on' : ''}${pending != null ? ' pending' : ''}`} onClick={toggle}
              disabled={!connected || pending != null}
              aria-pressed={on} aria-label={on ? 'Turn relay off' : 'Turn relay on'}>
        <span className="power-icon" aria-hidden />
        <span>{pending != null ? (on ? 'Turning on…' : 'Turning off…') : on ? 'Turn off' : 'Turn on'}</span>
      </button>
      <p className="hint">
        {relay.on
          ? 'Robot messages travel through your phone. Turn it off and the network will find another route or hold its messages.'
          : 'You are off the network. Robots keep their data until a path comes back.'}
      </p>

      <div className="relay-stats">
        <div><b className="mono">{relay.queue}</b><span className="muted small">Messages waiting</span></div>
        <div><b className="mono">{relay.on ? neighbors.length : 0}</b><span className="muted small">Devices in range</span></div>
      </div>

      {relay.on && neighbors.length > 0 && (
        // capped so the map below doesn't jump while you are about to tap it
        <div className="neighbors">
          {neighbors.length > MAX_SHOWN && (
            <span className="muted small">Strongest {MAX_SHOWN} of {neighbors.length}</span>
          )}
          {neighbors.slice(0, MAX_SHOWN).map((n) => (
            <div key={n.id} className="neighbor">
              <span className={`signal s${bars(n.rssi)}`} aria-hidden><i /><i /><i /><i /></span>
              <span>{label(n.id, robots)}</span>
              <span className="muted mono small">{Math.round(n.rssi)} dBm</span>
            </div>
          ))}
        </div>
      )}
      {relay.on && !neighbors.length && <p className="hint">No one in range here. Move closer to the command post or another relay.</p>}

      <button className={`tool${mode === 'place' ? ' on' : ''}`}
              disabled={!connected}
              onClick={() => set({ mode: mode === 'place' ? 'view' : 'place', selected: null })}>
        <i className="tool-relay" />{mode === 'place' ? 'Cancel move' : 'Move relay'}
      </button>
    </section>
  )
}
