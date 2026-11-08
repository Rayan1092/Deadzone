# Phone planning and safety API (Person 2)

This milestone supplies the backend for Person 3's phone interface. The phone UI
and the robot behavior that executes an assigned plan belong to their respective
owners. Existing screen messages and robot behavior continue to work.

## REST contract

| Request | Body | Result |
| --- | --- | --- |
| `GET /api/floorplan` | none | Public planning floorplan; hidden survivors and collapse rubble are omitted |
| `GET /api/join` | none | `{ "url": "http://<laptop>:5173/phone" }` in development, or the configured public frontend URL |
| `POST /api/plan` | Search plan below | Save the shared draft, broadcast `plan_state`, run safety and return its result |
| `POST /api/plan?check=false` | Search plan below | Quiet save: `{saved:true, plan_id, checked:false}`; broadcasts only `plan_state`, performs no safety check or dispatch |
| `POST /api/dispatch` | `{ "plan_id": "P-1" }` | Recheck current knowledge; return `{ok: true, plan_id}` and queue plan bundles, or return safety violations |
| `POST /api/fault` | `{type: "rubble", at: [x,y]}` or `{type: "overcurrent", robot: "R1"}` | Validated director fault injection |
| `GET /api/report` | none | `{text, generated_at, source}` briefing, also broadcast to screens |

For the opt-in Gemini briefing setup, tool boundary and local fallback, see
[`GEMINI.md`](GEMINI.md). Source is `gemini` only after a successful tool-grounded
model reply; otherwise `local`. A reset during generation returns 409 `report_reset`.

Safety rejection is HTTP 200 with `ok: false`, so the UI can show the violation card.
Use `?check=false` to preload the demo draft without a phone `safety` message or
screen `safety_reject` event. `saved:true` means stored, not safety-approved.
The default remains `check=true`; explicit phone checks and dispatch always check.
Malformed data is 422, an unknown plan is 404, and changing an already dispatched
plan ID is 409. Error bodies are `{ "detail": { "code": "...", "msg": "..." } }`,
with an `issues` array on request validation errors. Full request schemas are also
available at FastAPI's `/docs`.

```json
{
  "plan_id": "P-1",
  "author": "phone-a",
  "zones": [{
    "id": "Z1",
    "robot": "R1",
    "priority": 1,
    "poly": [[3,14],[6,14],[6,16],[3,16]],
    "comms": "relay",
    "requires": {"stairs": false, "rubble_height": 0}
  }],
  "no_go": [],
  "lost_link_budget_s": 60
}
```

The sample zone is close to the entry. The server now primes one real sim tick
at startup and reset, delivering sensor/telemetry bundles through the network while
leaving the demo paused at T+0.1 s. Safety can run before Space is pressed. Missing
telemetry in other scenarios still produces `battery_reserve` with `value: null`;
no live battery fallback is used.

IDs contain letters, digits, `_`, `-` or `.`, up to 64 characters. Plans contain
1–32 zones, up to 32 no-go regions, and 3–64 vertices per polygon. Coordinates must
be finite numbers inside the building. Polygons must be simple with positive area;
a repeated closing vertex is allowed and removed. IDs are unique across all regions.
Unknown fields are rejected. `priority` is an integer from 1 (first) to 10.

`requires` is an optional extension to the original zone schema. Its default is
`{stairs: false, rubble_height: 0}`. Robot capabilities are declared in `RobotSpec`;
current defaults reject stairs and rubble climbing because neither is supported by
the current motion physics. Person 3 can read these capabilities in phone `hello`.

Repeated dispatch of the same saved ID is idempotent. To modify an already
dispatched plan, create a new `plan_id`. Plans are held in memory and cleared by
simulation reset. Shared draft edits use last-write-wins; CRDT merging is later work.

## Phone WebSocket contract

Connect to `/ws/phone?client=phone-a&role=planner`. If `client` is omitted, the server
assigns a label and returns it in `hello`. Persist a client label in the frontend to
preserve authorship across reconnects. These labels identify sessions, not users.

Every message keeps the existing `{t, seq, time, data}` server envelope.

Immediately after connecting, and again on reset:

1. `hello`: `{floorplan, grid: {w,h,cell}, robots, plan, client, role, relay_id}`.
   `robots` contains static `{id,name,color,capabilities}`. `plan` is the current
   normalized draft or `null`. `relay_id` identifies a relay-role client's node;
   it is `null` for planners.
2. `cmd_view`: the delivered `{robots,survivors,relays,faults,routes}` Command state plus `map`.
   `routes` retains the latest delivered route per survivor; relay records add
   nullable `beacon_for`. Screen and phone `hello` also include active `detector`
   status; see [`BACKEND-SCOPE-HANDOFF.md`](BACKEND-SCOPE-HANDOFF.md).
   Each robot also includes last reported `plan_id` and `zone` (string or null),
   learned only from delivered telemetry. These do not acknowledge a dispatch;
   see [`DEMO-CONTROLS.md`](DEMO-CONTROLS.md).
   `map` is base64 of the row-major `uint8` Command occupancy grid. Dimensions and
   cell size come from `hello.grid`; values remain 0 unknown, 1 free, 2 occupied.
   Further views are sent every five sim ticks (2 Hz in simulation time).

Phones never receive the Reality map, hidden survivor positions, or truth rubble.
Their pre-collapse floorplan uses open door states and known static hazards. The
existing big-screen `hello` still contains the full floorplan for the Reality view.

### Editing and checking

Send `{ "t": "plan_edit", "data": <search plan> }`. The server sets `author` to
the connected client label, validates the data and broadcasts a full normalized
`plan_state` to every connected phone and big screen. The `author` field may be omitted on this
WebSocket message; it remains required on REST submissions.

Send `{ "t": "plan_submit", "data": { "plan_id": "P-1" } }` to run safety.
All phones receive `safety` with the same shape as `POST /api/plan`:

```json
{
  "ok": false,
  "plan_id": "P-1",
  "violations": [{
    "robot": "R1", "zone": "Z1", "rule": "battery_reserve",
    "value": 9, "limit": 20,
    "msg": "R1 estimated reserve 9.0%, minimum 20%"
  }]
}
```

`plan_submit` checks; it does not dispatch. Use `POST /api/dispatch` for the dispatch
button. Rejected checks also emit `event` with `kind: safety_reject` to big screens.

Invalid frames return `error` messages with `{code,msg,issues?}` and leave the socket
open. Codes include `invalid_json`, `invalid_message`, `invalid_plan`, `invalid_request`
(REST validation), `plan_not_found`, `plan_dispatched`, `unsupported_message`, and
`read_only_role`. Unknown roles/invalid client labels are rejected at connection.

`role=relay` can observe Command state and control its own relay, but cannot edit
plans. See [`FRONTEND-HANDOFF.md`](FRONTEND-HANDOFF.md) for the relay lifecycle,
state schema, screen updates, director controls and report contract.

## What safety checks

The checker uses the pre-collapse building, responder no-go regions, static robot
capabilities and **delivered** Command telemetry/map/relay announcements. It never
looks at the live robot battery, live pose, hidden rubble or actual current links.

- `battery_reserve`: from the last reported pose, estimate travel through each
  assigned zone in priority/ID order and return to the entry. Add zone area / 8 m
  of search coverage per zone, then apply cruise power and the simulator's battery
  time scale. All zones on one robot share one budget. Discount stale telemetry for
  possible driving since the report. Reject reserves below 20%.
- `capability`: reject unknown robot IDs and unsupported declared requirements.
- `no_go_overlap`: reject polygons that overlap or touch a static/responder no-go
  region. Overlap uses polygon edges, including thin regions between grid centers.
- `zone_unreachable`: A* must reach a traversable cell near the zone centroid and
  return home. Route planning uses the 0.25 m grid and delivered obstacle cells.
- `comms_plan`: predict a link to Command through announced relays using the
  building prior and -88 dBm threshold, or require `comms: lost_link_ok` and a
  positive `lost_link_budget_s` (maximum 900 seconds).

These are predictions from available knowledge. Unknown collapse debris and relay
power changes not yet reported to Command remain unknown. Dispatch always runs a
new check; an earlier passing result is not stored as a permanent approval.

## Robot integration (Rayan)

Accepted dispatch queues one priority-1 `kind: plan` DTN bundle per assigned robot,
from `CMD` to the robot ID. Each payload is the normalized plan filtered to that
robot's zones, with the plan ID, author, global no-go list and lost-link budget.

Read received bundles with `io.radio.receive()`. This returns and clears complete
delivered bundle records from the IO and legacy peer buffers. It does not read truth, apply
targets, change the robot's no-go mask, or change its state. Robot policy must handle
`kind == "plan"` to apply those instructions. An existing robot-level peer telemetry
inbox can still be read separately without consuming commands. The unified IO API
drains both buffers once, allowing Rayan to remove that legacy attribute later.

## LAN/demo setup

Use `uvicorn ... --host 0.0.0.0 --port 8000` and Vite's LAN-capable dev server. Both
phones and the laptop use the same Wi-Fi/hotspot. `GET /api/join` uses the request's
LAN origin; for localhost it attempts to select a private LAN IPv4 address.

To make the QR destination explicit, set before starting the backend:

```powershell
$env:DZ_PUBLIC_URL = 'http://192.168.1.8:5173'
```

Use the actual laptop IP. After `npm run build`, use port 8000 instead. This setting
is an HTTP(S) origin without a path prefix. It selects the join URL; it does not
change listener bindings. `/phone` and `/phone/` serve the built frontend entry.
If no build exists, the backend returns 503 and the Vite frontend can still be used.

## Verification

`cd server` then `python -m pytest -q` runs the combined backend suite. This includes the original
rescue story and DTN tests plus safety, schema, REST, two simultaneous planner
WebSockets, reconnect/reset, malformed requests, Command-only map updates, join
URLs, and the built frontend entry route. The phone UI still requires Person 3's
implementation; a live phone/Wi-Fi rehearsal remains an integration checkpoint.

This includes merged multi-robot and relay PRs #3 and #5. Robot endpoints do not
forward other nodes' bundles; transport, radio reachability and screen link status
use the same rule. Peer telemetry now travels through DTN and reaches the robot's
peer buffer only after delivery. All robot message kinds are available through
`io.radio.receive()`; the legacy peer reader remains compatible. See `DTN.md` for
peer TTL, IDs and byte accounting.
