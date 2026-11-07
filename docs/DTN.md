# Multi-hop network milestone (Person 2)

The simulation now transfers bundles one hop at a time through relay nodes.
Command still changes only when a complete bundle reaches `CMD`.

## Transfer rules

- Every robot's existing `outbox` is attached to `sim.network`. Relay queues have
  a 2,000,000-byte capacity. Command has its own outgoing queue too.
- Each tick snapshots the queues, orders bundles by priority, creation time and
  bundle ID, then chooses a Dijkstra route over currently up links. A newly received
  bundle cannot make another hop until the next tick.
- A physical link has one RSSI-dependent byte budget shared by both directions.
  Large bundles take multiple ticks. Other independent links can transfer in parallel.
- Following the multi-robot team contract, simulation robots are endpoints and do
  not forward other nodes' bundles. Route checks, screen status and transport all
  exclude robots as intermediate hops; relays and CMD can forward.
- The sender retains the complete bundle until the receiver stores it and returns
  a custody acknowledgement. The simulation models receipt and acknowledgement as
  one atomic operation, without separate acknowledgement delay or packet loss.
- A broken link cancels partial transfer progress, not the sender's bundle. If a
  relay already accepted custody, it keeps its queue through an outage or power-off.
  Transmission restarts when a usable route returns.
- Receivers acknowledge duplicate `bid`s without enqueuing them again. Destination
  delivery is deduplicated too. Receipt records expire with their bundles.
- TTL cleanup runs even when there is no route. Expired bundles are discarded.
- Under queue pressure, a relay evicts its lowest-priority/newest bundles to admit
  a higher-ranked incoming bundle. If it still cannot fit, it refuses custody and
  the sender retains the incoming bundle. Congestion can therefore discard low
  priority data; this is not an unlimited-storage reliability guarantee.
- Routes avoid previous custodians to prevent a loop being mistaken for a duplicate
  acknowledgement. If no loop-free end-to-end route exists, the current custodian
  holds the bundle. This milestone does not predict future contacts.

## Robot integration (Rayan)

`io.drop_relay()` now places a relay at the robot's odometry position and returns
its ID, such as `RL1`. The robot's own code must enforce its two-relay inventory,
upstream RSSI threshold, spacing and deployment policy. Rayan's merged relay work
now implements automatic deployment, two-relay inventory and actual `relays_left`
telemetry. This backend preserves that policy.

For backend scenarios:

```python
relay_id = sim.add_relay((33, 15), owner="R1")
sim.set_relay_power(relay_id, False)
sim.set_relay_power(relay_id, True)
```

Placement rejects obstacles, no-go zones and positions outside the building.
`phone=True` marks a backend relay as phone-owned. Sessions, placement and power
controls are documented in [`FRONTEND-HANDOFF.md`](FRONTEND-HANDOFF.md).

Outgoing commands can be placed in `sim.network.queues["CMD"]` with a robot ID as
`dst`. Delivered commands collect in `sim.inboxes[robot_id]`; `io.radio.receive()`
consumes that inbox and any unread legacy peer telemetry. Robot policy is
responsible for executing the commands.

## Peer telemetry

The temporary direct inbox-copy shortcut has been removed. Each fresh robot
telemetry report is fanned out at its source into one unicast bundle per other
deployed robot. Copies are queued even if the peer is offline, then use the same
priority ordering, shared link budgets, custody, retry and expiry as other traffic.
Robots remain endpoints; relay nodes and CMD can carry peer traffic.

`DTNNetwork.fanout_telemetry` creates independent payload snapshots. Each peer copy
uses `bid = original_bid + "/" + recipient_id`, keeping delivery/dedupe separate
from the CMD report and other recipients. Repeating fanout of an already queued or
forwarded report does not create another copy. The source and original destination
are excluded from recipient fanout.

Peer copies keep the original creation time and expire after the lesser of the
source TTL and Rayan's `PEER_FRESH_S` (currently 15 sim seconds). The original CMD
report retains its normal TTL, so a long outage can still produce a delayed report
to Command without resurrecting an old peer target claim.

On destination delivery, current robot code can still read peer telemetry from its
existing `inbox`. `io.radio.receive()` now drains both that buffer and the separate
command buffer, in priority order, once. If Rayan removes the legacy peer inbox,
all delivery goes directly into `Sim.inboxes` and remains available through IO.
There are no duplicate copies; clearing a legacy peer buffer cannot drop commands.

Telemetry byte estimates now use at least the UTF-8 JSON payload length plus a
64-byte envelope allowance, on both the CMD report and peer copies. The old fixed
120-byte estimate did not account for targets and relay lists. `in_flight` includes
queued peer copies. Existing WebSocket shapes and telemetry payload fields remain
unchanged; only internal bundle IDs, timing and queue counts change.

## Frontend and protocol integration (Person 3)

Existing WebSocket envelopes and top-level message shapes are unchanged. Previously
empty, already documented relay fields are now populated:

- `tick.reality.relays`: `{id, pos, owner, on, queue, phone}`.
- `tick.reality.links`: actual graph edges, including relay links.
- `tick.command.relays`: `{id, pos}`, populated only after relay telemetry arrives.
- `tick.stats.relays`: relay count; `in_flight`: bundles across all node queues.
- `event.kind = "relay_dropped"`: `{kind, id, pos, owner}` on backend placement.

Internal relay announcements use existing priority-2 `telemetry` bundles with
`payload.node_type = "relay"` plus the relay's fields. They do not use robot pose or
battery fields and are handled separately by `CommandPost.receive`.

Command rejects expired, duplicate and non-delivered bundles. Delayed map patches
cannot overwrite cells from a newer delivered patch. Relay telemetry is sent at
placement and power-on, so the Command view is not a live relay-power monitor.

The frontend's relay rendering and actual edge drawing are still Person 3's work.
The existing robot-to-command visual line does not draw the full relay path yet.

## Verification

Run `python -m pytest -q` from `server/`. Tests cover the original single-robot
story, three-robot reset repeatability, one-hop-per-tick custody, interrupted large
transfers, duplicate replays, disconnected TTL expiry, shared-link bandwidth,
priority/queue pressure, rerouting, reverse-direction commands, relay power/reset,
and delayed Command knowledge. A 100-bundle scenario toggles the middle link every
3 seconds and checks exactly-once delivery. A real floorplan/RSSI scenario also
connects an east-wing robot through a relay at `(33, 15)`. The combined suite passes
the integration tests, including peer payload snapshots, dedupe, disconnected/relay TTL expiry,
outage recovery, partial-transfer retry, survivor priority, shared bandwidth,
endpoint-only routing and preservation of the separate command inbox.

Safety/plan APIs and planner phone sessions are described in
[`PHONE-PLANNING.md`](PHONE-PLANNING.md). FEC, Gemini generation,
recorder/replay and the full soak test remain subsequent Person 2 milestones.
