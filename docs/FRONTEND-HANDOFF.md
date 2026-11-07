# Person 2 → Person 3 integration contract

This addresses the demo dependencies raised by the frontend team. All controls
below use the existing `{t,seq,time,data}` server envelopes. No frontend or robot
policy files are changed by this backend work.

## 1. Safety before Space: resolved with real delivery

Hub startup and reset execute one simulation tick before remaining paused. Lidar,
odometry, robot telemetry and DTN delivery run normally; Command receives the
reports through the network. The initial paused clock is T+0.1 s. Do not replace
missing Command battery data with live robot battery or manually inject truth.

This makes the QR → plan/safety → Space demo order usable. The missing-telemetry
rejection remains appropriate when a report genuinely has not arrived.

## 2. Big-screen plans

`/ws/screen` now sends `hello`, `maps`, `tick`, then `plan_state` on connection.
`plan_state.data` is the same normalized plan as the phone message, or `null` when
there is no draft. Saves and phone edits broadcast it to screens and phones.

Accepted REST dispatch broadcasts that plan again and emits a screen event:

```json
{"t":"event","data":{"kind":"plan_dispatched","plan_id":"P1"}}
```

This event means plan bundles were queued, not that a robot has executed them.
The UI can distinguish draft previews from an accepted dispatch. Reset sends
`plan_state: null`; reconnect sends the current plan. Robot policy still owns
actually applying its received zones, no-go regions and lost-link budget.

## 3. Director F and R, plus REST faults

F sends:

```json
{"t":"control","data":{"action":"director","value":{"do":"overcurrent","robot":"R1"}}}
```

The equivalent REST request is `POST /api/fault` with
`{"type":"overcurrent","robot":"R1"}`. Optional `duration_s` defaults to 1.0 and
must be 0.6–10 sim seconds. Successful injection returns `{ok,type,robot,until}`.

R sends `value: {do:"rubble", at:[x,y]}`. REST uses
`{type:"rubble", at:[x,y]}`; optional `size` is 0.25–5 m, default 1.4 m. Existing
building/rubble snapshots and `rubble_fall` events update normally. Phone prior
geometry and Command's map do not receive hidden new rubble.

Overcurrent injection produces 8 A through `io.motor_current()` and
`io.odometry().wheel_current` until its sim-time expiry. It also calls Rayan's
`Robot.inject_overcurrent(seconds=...)` hook when that implementation is present.
The backend does not set a robot's fault/state directly or pretend it recovered.
Detection, reverse/replan and fault bundles remain robot-owned. The screen-only
`fault_injected` event contains `{type,robot,until}` and is distinct from detection.

Missing robot IDs return 404; invalid actions, positions and values return 422.
Bad WebSocket controls return `t:error` and keep the socket open. Reset clears all
injections. Simulation pauses also pause the duration countdown.

## 4. Phone relay milestone

Connect `/ws/phone?client=<persistent-client-label>&role=relay`.

- First connection creates a phone relay at the entry. `hello.relay_id` identifies it.
- Message order is `hello`, `cmd_view`, `relay_state`.
- Send `relay_place` with `data: {pos:[x,y]}` to move that same node. Unsafe/outside
  positions are rejected. It retains carried bundles and its power state.
- Send `relay_power` with `data: {on:true}` or `{on:false}`. The flag is a JSON
  boolean. A client controls its own node; messages do not accept another relay ID.
- Both actions return updated `relay_state`; state is also refreshed every five
  sim ticks and when another relay's power/disconnect changes the neighbor graph.

```json
{"t":"relay_state","data":{
  "id":"RL1","pos":[8,15],"on":true,"queue":2,
  "neighbors":[{"id":"CMD","rssi":-53.4}]
}}
```

`queue` counts stored bundles, not bytes. Neighbors describe this phone node's
local radio observations. Ordinary phone views still contain only Command data;
no hidden survivors or truth map are sent.

Power-off breaks actual graph links without deleting custody queues. The last
socket for a relay client disconnecting turns its relay off. Reconnecting with the
same label reuses its ID, position and requested on/off setting. Multiple sockets
with one label share a node; closing one does not disable the remaining socket.
Use distinct persistent labels for different phones.

Reset clears relay nodes and re-creates connected relay clients at the entry, on,
then sends fresh `hello`, `cmd_view` and `relay_state` messages. Disconnected nodes
are not restored. There is a 32-phone-relay cap per simulation; reset clears it.

Own position announcements are coalesced while queued so dragging a relay while
paused does not flood its queue. Internal announcement revisions prevent reordered
updates at the same sim time from rewinding Command's known position. Command
still learns locations only through delivered announcements. Carried traffic is
preserved; a full queue can postpone a low-priority position announcement until a
later placement/power-on update.

## 5. G/report endpoint

G calls `GET /api/report`. It returns and broadcasts as `t:report`:

```json
{"text":"Command briefing ...","generated_at":0.1,"source":"local"}
```

`generated_at` is sim time in seconds. This is the deterministic local fallback;
Gemini generation is not implemented by this integration milestone. The UI must
not label `source:local` as a Gemini response. Inputs are delivered Command robots,
survivors, relays, last reported faults and delivery counts only.

`command.faults` / phone `cmd_view.faults` now hold the latest delivered fault report
per robot, including `reported_t`. They are reported history, not live fault flags.
Reality telemetry's `fault` remains the live robot field. This supports Rayan's
`TRAPPED` report without leaking an unreported fault.

## 6. Delivery animation event

Successful, nonduplicate final CMD arrivals emit screen `event` with
`kind:bundle_delivered`, `src`, `dst`, `bundle_kind`, `hops`, and `delay_s`.
Intermediate relay hops and peer destinations do not emit this CMD-delivery event.
It corresponds to `stats.delivered`; survivor/fault/plan priorities are unchanged.
Filter high-frequency delivery events out of the human-readable incident sidebar
if needed, while using them for animations/counters.

## Remaining cross-team work

From merged timeline PR #7, `tasks` entries are `{name,start,dur,missed}`. `start`
and `dur` are virtual milliseconds within the latest 100 ms frame. Names are
`safety`, `motion`, `comms`, `mapping`, `perception`, `battery`; preempted jobs can
have multiple slices. The declared robot states are `DEPLOYING`, `EXPLORING`,
`LOST_LINK_EXPLORING`, `RETURNING_TO_SIGNAL`, `RETURNING_HOME`, `REPLANNING`, `FAULT`,
`DONE`. Declared fault labels are `OVERCURRENT`, `STUCK`, `LOW_BATTERY`, `TRAPPED`,
`SAFE_STOP`, or `null`. These labels include planned cases; display actual emitted
state/fault values rather than inferring recovery from a successful HTTP response.

- Rayan: consume plan bundles via `io.radio.receive()` and apply the instructions.
- Rayan: the same IO call now returns peer telemetry too. It drains both buffers
  once, in priority order; the current legacy peer reader is supported until it is
  removed. Backend delivery also works without a robot `inbox` attribute.
- Rayan's merged timeline PR #7 supplies basic overcurrent detection/recovery and
  task telemetry. Further scheduler/fault policy remains robot-owned.
- Person 3: wire the actual UI and rehearse with real phones on the demo network.
- Person 2 later: Gemini tool-calling generation, FEC and recorder/replay.

The related frontend work may be local/unpublished; this document states the
backend behavior it can build against, not completion of that UI.

Verification on merged replanning/timeline main plus this backend: **128 tests
pass**, including API-driven overcurrent detection/reverse/replanning, paused
safety, screen state, relay lifecycle/traffic, reports and unified IO delivery.
