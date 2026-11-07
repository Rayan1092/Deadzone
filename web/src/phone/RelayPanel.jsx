import { usePhone } from './store'
import { sendPhone } from './socket'

// This phone is a radio relay in the sim. Turning it off breaks real links;
// robots and relays keep their bundles until a path comes back.
const MAX_SHOWN = 4

function bars(rssi) {
  return rssi > -60 ? 4 : rssi > -70 ? 3 : rssi > -80 ? 2 : 1
}

function label(id) {
  if (id === 'CMD') return 'Command post'
  if (/^R\d+$/.test(id)) return `Robot ${id}`
  return `Relay ${id}`
}

export default function RelayPanel() {
  const relay = usePhone((s) => s.relay)
  const relayId = usePhone((s) => s.hello?.relay_id)
  const pending = usePhone((s) => s.relayPending)
  const mode = usePhone((s) => s.mode)
  const set = usePhone((s) => s.set)
  if (!relay) {
    return (
      <section className="m3-card relay-card">
        <b>{relayId ? `Joining as relay ${relayId}…` : 'Connecting your relay…'}</b>
      </section>
    )
  }
  const on = pending ?? relay.on
  const toggle = () => {
    set({ relayPending: !on })
    sendPhone('relay_power', { on: !on })
  }
  const neighbors = [...relay.neighbors].sort((a, b) => b.rssi - a.rssi)
  return (
    <section className="m3-card relay-card">
      <div className="relay-head">
        <div>
          <span className="muted small">This phone is</span>
          <div className="relay-id">Relay {relay.id}</div>
        </div>
        <span className={`chip ${relay.on ? 'ok' : 'bad'}`}>{relay.on ? 'On air' : 'Off'}</span>
      </div>

      <button className={`power${on ? ' on' : ''}${pending != null ? ' pending' : ''}`} onClick={toggle}
              aria-pressed={on} aria-label={on ? 'Turn relay off' : 'Turn relay on'}>
        <span className="power-icon" aria-hidden />
        <span>{pending != null ? (on ? 'Turning on…' : 'Turning off…') : on ? 'Turn off' : 'Turn on'}</span>
      </button>
      <p className="hint">
        {relay.on
          ? 'Robot data hops through your phone. Turn it off and watch the network reroute or hold its data.'
          : 'You are off the network. Robots keep their data until a path comes back.'}
      </p>

      <div className="relay-stats">
        <div><b className="mono">{relay.queue}</b><span className="muted small">bundles carried</span></div>
        <div><b className="mono">{relay.on ? neighbors.length : 0}</b><span className="muted small">in radio range</span></div>
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
              <span>{label(n.id)}</span>
              <span className="muted mono small">{Math.round(n.rssi)} dBm</span>
            </div>
          ))}
        </div>
      )}
      {relay.on && !neighbors.length && <p className="hint">No one in range here. Move closer to the command post or another relay.</p>}

      <button className={`tool${mode === 'place' ? ' on' : ''}`}
              onClick={() => set({ mode: mode === 'place' ? 'view' : 'place', selected: null })}>
        <i className="tool-relay" />{mode === 'place' ? 'Tap the map below to move here' : 'Move my relay'}
      </button>
    </section>
  )
}
