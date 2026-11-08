# Network traffic stream

`DZ_NETWORK_TRAFFIC=1` at Sim reset enables diagnostic events on `/ws/screen`.
The flag defaults off. Routing, bandwidth, custody and robot behavior are unchanged.

- `event.data.kind = "bundle_hop"`: `bid, src, dst, a, b, bundle_kind, bytes,
  wire_bytes, prio, started_t, arrived_t, hops`. Emitted after a complete hop's
  custody acknowledgment. `a` and `b` are this hop's sender and receiver; `src`
  and `dst` remain the original endpoints. `started_t` is the first observed
  transfer tick and can equal `arrived_t` for a one-tick transfer.
- `event.data.kind = "bundle_held"`: `bid, node, src, dst, bundle_kind, bytes,
  prio, reason, held_since`. Emitted only on entering or changing a hold reason:
  `no_route`, `disabled`, `link_busy`, `custody_refused`, or `fec_retry`.
- `tick.data.reality.queues`: node IDs mapped to `{bundles, bytes}` from actual
  custody queues. `bytes` is declared custody size; hop `wire_bytes` is the
  successful attempt's size charged to the transport budget, including FEC.
- `tick.data.stats.traffic_events_dropped`: diagnostic overflow count. The event
  buffer holds 512 entries; overflow never drops or throttles transport.

Partial transfers, failed FEC and refused custody never emit a successful hop.
Events contain no payloads or invented positions. Command, phones and Gemini
receive no queue inventories or hop/held events. Screen clients can animate the
actual `a` to `b` hop and show a hold at `node`; use the existing node positions.
