# Deadzone Build Plan (UB Hacking 2026)

Nov 7, 2026 · @Rayan Diya

## The idea

Deadzone is rescue robots that keep working where the signal dies. Inside collapsed buildings, mines and tunnels, concrete and steel kill radio, and there is no GPS or cell signal. Most rescue robots stop when they lose their link, and the command post goes blind.

The DARPA Subterranean Challenge (2018 to 2021) showed a better way: the winning robots explored on their own, dropped radio relays as they went, and reported back once they reconnected. Deadzone is a fully simulated version of that idea with three layers (robots, network, command post) and a 3D visualization.

- **The memorable moment:** two synced views side by side. Reality shows where robots are and what they found. Command shows only what reached the antenna: a stale map, ghost robots, no survivors. A robot goes dark, finds a survivor, reconnects, and the map and survivor burst onto the Command view.
- **Pitch lines:** "Rescue robots today stop when the signal stops. Ours keep searching." and "The robots are autonomous, and AI detects survivors."
- **Not a GPT wrapper:** autonomy comes from our algorithms (frontier exploration, A\*, relay rules, state machines). Trained AI only detects survivors. Gemini only writes situation reports.
- **Constraints:** no hardware. Laptops and phones only, nothing that depends on lighting, room noise or physical sensors.
- **Why not the space theme:** we skip "Into the Hackosmos" on purpose to compete for Best General.
- **Prize targets:** Best General, Best AI/ML, Most Over Engineered, Best UI/UX, MLH Best Use of Gemini API.
- **Judging (2025 criteria):** It works, Usefulness, Technicality, Effort, Freshness, Pitch, X-factor. A complex project that doesn't work scores nothing.

## Current status (2:30 PM Saturday)

The starter on `main` already runs the core story with one robot. In a headless run with seed 7, survivor S1 is found in the dark at about 213 s sim time and reaches the command post about 9 s later.

**Done**

- Floor plan `collapse_01` with tuned dead zones: the corridor near the entry is solid, the south-east room is dark, and survivor S1 now sits at (36, 27) inside a steel cage (room E2, metal walls, one door facing away from the corridor) so relays outside can't reach it (PR #5)
- Sim server: 10 Hz tick, FastAPI, `/ws/screen` streaming `hello`, `tick`, `maps`, `event`, plus `/api/control` and a `/ws/phone` stub
- One robot: lidar, occupancy map, frontier exploration, A\*, lost-link return to breadcrumbs, sim thermal sensor, battery drain
- Single-hop store and forward: the robot keeps bundles until it has a link, and the Command view only changes from delivered bundles
- Web big screen: Reality vs Command split with synced cameras, fog of war, lidar rays, planned path, link line, ghost robots, survivor markers, sidebar, keyboard controls
- 5 server tests, including the core story and a no-leak test

**Not started:** multi-robot coordination (3 robots currently all explore the same room), relays, multi-hop routing, phone app, scheduler and task timeline, full fault FSM, safety checker, Gemini reports, ML detector, Reed-Solomon, CRDT.

## Added scope (5:45 PM Saturday)

The team agreed to make the trained AI visible to judges and to make survivor detection lead somewhere useful. Owners are the people in the Team roles table below. Cut the robot's-eye view first if time runs short.

| Feature | What judges see | Owner | Target |
| --- | --- | --- | --- |
| AI detection card | On `survivor_found`, a frosted card on the Reality pane with the thermal crop the detector judged and its verdict ("Person, 100%"). Rejected decoys get a faded card ("Not a person, 0.3%, rejected") | Aziz serves `ml/crops/runtime/` as static files, Yusuf builds the card | 10 PM |
| Detector status chip | Top bar shows "Detector: AI model" or "Detector: sim fallback" from `hello` | Aziz adds it to `hello`, Yusuf shows it | 10 PM |
| Decoy safety | In sim fallback, `RobotIO.thermal()` emits no decoys, so a missing PyTorch can never show a radiator as a survivor | Aziz | 10 PM |
| Rescue route and beacon | When a robot confirms a survivor it drops a beacon relay next to them (if it has one left) and sends a safe A\* route from the entrance to CMD as a priority-1 bundle. Command draws it when it arrives (`rescue_route` event: survivor id, path points, length in meters) | Rayan (robot side), Yusuf (drawing) | 10 PM |
| Survivor figures | A low-poly person lying down with a warm thermal glow, keeping the pulsing ring. Robots bigger and brighter so they read from across the room | Yusuf | 3 AM |
| Robot's-eye view | Click a robot: a small picture-in-picture from its camera, with a Thermal toggle where walls go cold blue and survivors and decoys glow. Phone: tap a robot to see its status and last thermal crop. Rendered small and only while open | Yusuf, or Rayan's session with Yusuf's OK | 3 AM, cut first |
| Liquid glass styling | Frosted translucent panels, cards and phone UI | Yusuf | 3 AM |
| ML slide | Training examples, pipeline, confusion matrix, 96.2% accuracy, 96.3% precision, 96.0% recall on 1,200 held-out FLIR images, "runs onboard with no signal" | Rayan | freeze |

Also pending from Aziz: director key O (`inject_perception_overload`) and a resume director action for SAFE\_STOP.

## Team roles and Claude Code

Code, `CLAUDE.md` and this plan refer to roles, not names. Each person tells Claude Code which role they are in their first message.

| Role | Person | Owns | First task |
| --- | --- | --- | --- |
| Rayan (robots and ML) | Rayan | `server/deadzone/robot/`, `ml/`, `data/floorplans/` | 3 robots sharing targets |
| Person 2 (backend and network) | *Aziz* | `sim.py`, `app.py`, `floorplan.py`, `network/`, `command/`, `scripts/` | multi-hop store and forward with custody |
| Person 3 (frontend and phone) | *Yusuf* | `web/` | phone page and QR join |

**Shared context lives in the repo.** Each person's Claude follows `docs/team/INSTRUCTIONS.md`: read every `docs/team/history/*.md` before working, and stage your own history entry with every commit (a hook enforces it). Asks between teammates go in the history files' Heads-up and Blocked sections instead of chat messages.

**The phone app is a web page, not an Android APK.** Judges scan a QR code and it opens in their phone browser at `/phone`. Nothing to install, and it works on iPhone too.

**Person 2 starter prompt for Claude Code**

```
I'm Person 2 on Deadzone. I own backend and network: server/deadzone/sim.py, app.py, floorplan.py, network/, command/ and scripts/. Read CLAUDE.md and docs/PLAN.md first, especially The idea, Current status, the APIs section and my column in the Hour-by-hour plan. Then on branch p2/dtn-multihop, turn the single-hop store and forward in sim.py and network/dtn.py into multi-hop forwarding with per-hop custody, dedupe by bid, TTL and relay queues, so relays can carry bundles. Keep the Command view fed only by delivered bundles and keep the sim deterministic. Run the server tests, open a PR and ask me before merging. Keep me updated in short messages.
```

**Person 3 starter prompt for Claude Code**

```
I'm Person 3 on Deadzone. I own the frontend in web/: the 3D big screen, the dashboard panels and the phone page. Read CLAUDE.md and docs/PLAN.md first, especially The idea, Current status, the APIs section and my column in the Hour-by-hour plan. Then on branch p3/phone-shell, build the phone page at /phone as a Material 3 style dark mode web app that connects to /ws/phone and shows the floor plan with the Command view, and add a QR join panel on the big screen. The big screen must stay at 60 fps with both views. Run npm run build, open a PR and ask me before merging. Keep me updated in short messages.
```

## Setup and git workflow

Everyone uses VS Code with the Claude Code extension on one shared GitHub repo, and `main` is protected so it always runs.

**Setup**

- Install Git, Python 3.11+, Node 20+, VS Code and the Claude Code extension (needs a paid Claude plan or a Console account)
- Clone the repo, then follow the README to install and run the server and web app
- Keep the project out of OneDrive, or pause OneDrive sync, so `node_modules` doesn't get synced
- Secrets: the Gemini API key goes in `server/.env` as `GEMINI_API_KEY`. `.env` is gitignored. Never paste keys into code

**Git rules**

- `main` requires a pull request (0 approvals) and blocks force pushes and deletion
- One short branch per task: `rayan/<feature>`, `p2/<feature>`, `p3/<feature>`
- Always `git checkout main` and `git pull` before starting a new branch
- Merge at least every hour so branches never drift
- Any change to a message shape goes in the PR description and the team chat
- Run `python -m pytest -q` in `server/` before every PR, and `npm run build` in `web/` if web changed

**Demo laptop and phones**

One laptop runs the server. Run `npm run build` in `web/` once and the server serves the web app itself on port 8000. Phones open `http://<laptop-ip>:8000/phone` on the same Wi-Fi, or everyone joins a phone hotspot if the venue Wi-Fi blocks devices from seeing each other.

**Dataset and model**

`ml/data/` is gitignored, so only Rayan downloads the FLIR dataset. The trained model file gets committed if it's under about 50 MB, otherwise it's shared directly with whoever runs the demo laptop.

## Overview and locked decisions

One Python sim server owns the truth and streams two views (Reality and Command) to one web app that serves the big screen and the phones. These decisions are locked so all three of you can code against them in parallel from 1:45 PM.

| Decision | Value | Why |
| --- | --- | --- |
| Sim server | Python 3.11, FastAPI, uvicorn, numpy, pydantic | numpy raycasting is fast, PyTorch lives in the same language |
| Frontend | Vite + React (plain JSX) + @react-three/fiber + drei + zustand | one app: `/` big screen, `/phone` responders and relays |
| ML | PyTorch + torchvision, fine-tune ResNet18 or MobileNetV3 on thermal crops | trains in minutes on a laptop |
| Sim tick | dt = 0.1 s sim time, speed multiplier default 2x | fast enough for a 3 min demo |
| Broadcast | state every tick, occupancy maps every 5 ticks (2 Hz sim) | maps are small, no deltas needed |
| World | single floor, 40 m x 30 m, grid cell 0.25 m (160 x 120 cells) | 1 m doors stay 4 cells wide after inflation |
| Coordinates | meters, origin bottom-left, x east, y north, heading in radians CCW from +x | three.js maps sim (x, y) to (x, height, -y) so north is up on screen (helper w2t in web/src/three/util.js) |
| Randomness | one seeded RNG per run | the demo replays identically |

**Honesty rule.** Robot code never reads the World directly. It only sees the world through the `io` object (`io.lidar()`, `io.thermal()`, `io.odometry()`) and only talks to other nodes through bundles in its outbox. This keeps the Reality vs Command split real, and it is what you tell judges when they ask whether it is faked.

**Two knowledge views.** Reality = ground truth plus every robot's own map. Command = only what has physically arrived at the command post node through the network. The gap between them is the whole demo.

**AI boundaries.** Autonomy = our algorithms (frontier search, A\*, relay rules, state machines). Trained AI = survivor detector only. Gemini = situation reports through tool calls only.

## Repo structure and module ownership

Three areas map to three people, and the table shows what exists on `main` today versus what is still planned. The message shapes in this doc are the contract between server and web. Anyone changing one says so in the PR description and the team chat.

| Path | What it holds | Owner | Status |
| --- | --- | --- | --- |
| `CLAUDE.md` | rules Claude Code reads every session | everyone | exists |
| `docs/PLAN.md` | this plan, exported as Markdown | everyone | exists |
| `data/floorplans/collapse_01.json` | the demo building | Rayan | exists |
| `server/deadzone/app.py` | FastAPI app, sim loop, WebSocket and REST endpoints, broadcaster | Person 2 | exists |
| `server/deadzone/sim.py` | tick loop, world truth, `RobotIO`, link updates, bundle delivery, snapshots, rubble drop | Person 2 | exists |
| `server/deadzone/floorplan.py` | load floor plan JSON, rasterize walls and rubble, `add_rubble` | Person 2 | exists |
| `server/deadzone/geometry.py` | point in polygon, segment crossings, angle wrap | shared | exists |
| `server/deadzone/network/propagation.py` | multi-wall path loss, `LinkGraph` with hysteresis and Dijkstra | Person 2 | exists |
| `server/deadzone/network/dtn.py` | bundles and priority drain (single hop today) | Person 2 | exists |
| `server/deadzone/network/fec.py` | Reed-Solomon wrapper (`reedsolo` package) | Person 2 | planned |
| `server/deadzone/command/post.py` | Command view, updated only by delivered bundles | Person 2 | exists |
| `server/deadzone/command/` `plan.py` `safety.py` `reports.py` | plans, safety checker, Gemini reports | Person 2 | planned |
| `server/deadzone/robot/robot.py` | Robot class, behavior FSM, lost link, bundle emit, telemetry | Rayan | exists |
| `server/deadzone/robot/lidar.py` | raycast sensor | Rayan | exists |
| `server/deadzone/robot/mapping.py` | occupancy grid and map patches | Rayan | exists |
| `server/deadzone/robot/planning.py` | traversability, frontier clusters, A\*, wall cost | Rayan | exists |
| `server/deadzone/robot/power.py` | battery and wheel current | Rayan | exists |
| `server/deadzone/robot/` `scheduler.py` `faults.py` `perception.py` | RTOS-style scheduler, fault FSM, trained detector hook | Rayan | planned |
| `ml/` | crop prep, training, eval, `detector.pt` (`ml/data/` is gitignored) | Rayan | planned |
| `server/tests/test_core.py` | 5 tests including core story and no-leak | each owner adds theirs | exists |
| `web/src/store.js` `web/src/net/socket.js` | zustand store, WebSocket client with auto reconnect | Person 3 | exists |
| `web/src/three/` | `Pane`, `Building`, `Fog`, `Actors`, `util` | Person 3 | exists |
| `web/src/panels/Panels.jsx` | TopBar, Sidebar, keyboard controls | Person 3 | exists |
| `web/src/phone/` | PlanMap, Zones, SafetyCard, RelayMode | Person 3 | planned |
| `scripts/` | stream recorder and replay mode | Person 2 | planned |

**The robot boundary.** The sim calls `robot.step(dt, io)` once per tick. `io` is the only door to the outside world:

- `io.lidar()` returns beam angles, ranges and hit flags from the robot's true pose
- `io.thermal()` returns survivors within 5 m in the 120 degree camera cone with line of sight (sim sensor fallback, the trained model plugs in here)
- `io.odometry()` returns pose, speed and a blocked flag
- `io.drive(v, w)` sets the wheel command, the sim integrates motion and checks collisions
- `io.radio.cmd_reachable()` and `io.radio.neighbors()` give link state
- Outgoing bundles go into `robot.outbox`, and the network takes them when a path exists (custody)
- Planned: `io.drop_relay()` places a relay at the robot's position if it still carries one

Rayan's code lives entirely behind this interface, so Person 2 can stub it on day one.

## Data formats

All positions are meters in sim coordinates, all times are sim seconds, and every id is a short string (`R1`, `RL3`, `CMD`, `S2`).

### Floor plan (`data/floorplans/*.json`)

Walls are line segments and doors are simply gaps between segments. Rubble and hazards are polygons. Survivors are hidden from the command post and only exist in truth.

```json
{
  "id": "collapse_01",
  "name": "Eastside Warehouse Collapse",
  "size": [40, 30],
  "cell": 0.25,
  "wall_height": 3.0,
  "materials": {"concrete": 16, "brick": 10, "drywall": 4, "metal": 22},
  "walls": [{"a": [0, 0], "b": [40, 0], "material": "concrete"}],
  "doors": [{"at": [4.6, 17], "width": 1.2, "axis": "x", "state": "broken"}],
  "rooms": [{"id": "N1", "name": "Office A", "poly": [[0,17],[10,17],[10,30],[0,30]]}],
  "rubble": [{"id": "RB1", "poly": [[21,13],[23,13],[23,15],[21,15]], "height": 1.2}],
  "hazards": [{"id": "H1", "type": "gas", "poly": [[12,0],[24,0],[24,13],[12,13]]}],
  "survivors": [{"id": "S1", "pos": [37, 26], "thermal": "pos_0007.png"}],
  "entry": [1.0, 15.0],
  "command_post": {"pos": [-2.0, 15.0], "tx_dbm": 20}
}
```

The door `state` is visual only (`open`, `broken`, `blocked`). A blocked door must also have a rubble polygon so physics agrees with visuals.

### Occupancy grid

Row-major `uint8` array of `w * h` cells, row index = y. Values: `0` unknown, `1` free, `2` occupied, `3` no-go (hazard). Sent as base64 so a 160 x 120 map is 25.6 KB raw. Cell `(ix, iy)` covers `[ix*cell, (ix+1)*cell)` in x.

### Robot telemetry (one per robot per tick, Reality view)

```json
{
  "id": "R2", "name": "Scout 2",
  "pose": [12.4, 15.1, 1.57],
  "v": 0.8,
  "state": "EXPLORING",
  "battery": {"pct": 64.2, "wh": 57.8, "reserve_needed_pct": 21.0},
  "link": {"up": true, "via": "RL1", "rssi": -79.5, "to_cmd_hops": 2},
  "relays_left": 1,
  "target": [18.0, 22.5],
  "path": [[12.5, 15.0], [13.0, 16.0]],
  "lidar": [[14.1, 15.2], [14.0, 15.6]],
  "fault": null,
  "tasks": [{"name": "motion", "start": 0, "dur": 12, "missed": false}],
  "outbox": 3,
  "last_link_t": 81.2
}
```

`state` values (final): `DEPLOYING`, `EXPLORING`, `LOST_LINK_EXPLORING`, `RETURNING_TO_SIGNAL`, `RETURNING_HOME`, `REPLANNING`, `FAULT`, `DONE`. `fault` values: `null`, `OVERCURRENT`, `STUCK`, `LOW_BATTERY`, `TRAPPED`, `SAFE_STOP` (3 faults in 60 s). `wheel_a` is wheel current in amps.

`tasks` is the scheduler timeline for the last 100 ms frame: a list of `{name, start, dur, missed}` with `start` and `dur` in ms from 0 to 100, sorted by start, never overlapping. A preempted task appears as several pieces. Tasks that didn't run in that frame are absent (comms and mapping every 200 ms, perception every 500 ms, battery every 1000 ms). `missed` turns true for deadline misses in the overload moment. `lidar` holds beam endpoints for drawing.

`relay_dropped` event: `{"kind": "relay_dropped", "id": "RL1", "pos": [x, y], "owner": "R1"}`, ids numbered in drop order, `owner` null for relays placed without a robot. Robots receive plan and command bundles through `io.radio.receive()`. The F key calls `sim.robots[rid].inject_overcurrent()`.

### DTN bundle

```json
{
  "bid": "R2-000123",
  "src": "R2", "dst": "CMD",
  "kind": "survivor",
  "prio": 0,
  "created": 92.4, "ttl": 900,
  "custodian": "RL1",
  "hops": ["R2", "RL1"],
  "size": 412,
  "fec": {"scheme": "rs", "n": 255, "k": 223},
  "payload": {"survivor_id": "S1", "pos": [37.1, 25.8], "conf": 0.93, "crop": "pos_0007.png"}
}
```

`kind` and priority (0 = highest): `survivor` 0, `fault` 1, `command` 1, `plan` 1, `telemetry` 2, `map_patch` 3. Inside the server a `map_patch` payload holds numpy arrays `ix`, `iy` and `v` with the cells changed since the last patch. If a patch ever goes over the wire, encode it as base64 of `[ix, iy, value]` triples.

### Search plan (phone to command post)

```json
{
  "plan_id": "P-7", "author": "phone-a",
  "zones": [{"id": "Z1", "robot": "R1", "priority": 1, "poly": [[24,17],[32,17],[32,30],[24,30]], "comms": "relay"}],
  "no_go": [{"id": "NG1", "reason": "unstable floor", "poly": [[30,2],[32,2],[32,6],[30,6]]}],
  "lost_link_budget_s": 90
}
```

`comms` per zone is `relay` (robot will drop relays) or `lost_link_ok` (zone is allowed to be dark for up to `lost_link_budget_s`).

### Safety result

```json
{"ok": false, "plan_id": "P-7",
 "violations": [{"robot": "R2", "zone": "Z3", "rule": "battery_reserve", "value": 9, "limit": 20,
                 "msg": "Robot 2 battery reserve 9%, minimum 20%"}]}
```

Rules: `battery_reserve`, `capability` (stairs, max rubble height), `comms_plan`, `no_go_overlap`, `zone_unreachable`.

## APIs and WebSocket protocol

Two WebSockets carry everything live: `/ws/screen` for the big screen and `/ws/phone` for phones. REST is only for one-shot actions. Every WebSocket message uses one envelope:

```json
{"t": "tick", "seq": 812, "time": 81.2, "data": {}}
```

### Big screen: `WS /ws/screen`

| Direction | `t` | When | `data` |
| --- | --- | --- | --- |
| server to screen | `hello` | on connect and on reset | `floorplan`, `grid {w, h, cell}`, `robots [{id, name, color}]`, `speed`, `running` |
| server to screen | `tick` | every sim tick | `reality`, `command`, `stats` (below) |
| server to screen | `maps` | every 5 ticks | `w`, `h`, `reality` (b64), `command` (b64) |
| server to screen | `event` | when it happens | `kind` + fields, used for toasts, sounds and camera cues |
| server to screen | `report` | after `/api/report` | `text`, `generated_at` |
| screen to server | `control` | keyboard and buttons | `action`: `start`, `pause`, `reset`, `speed`, `director` + `value` |

`tick.data` shape:

```json
{
  "reality": {
    "robots": ["<robot telemetry>"],
    "relays": [{"id": "RL1", "pos": [9.5, 15], "owner": "R1", "on": true, "queue": 2, "phone": false}],
    "links": [{"a": "CMD", "b": "RL1", "rssi": -71.2, "up": true, "fec": false}],
    "survivors_found": [{"id": "S1", "pos": [37, 26], "by": "R2", "t": 92.4, "conf": 0.93}]
  },
  "command": {
    "robots": [{"id": "R2", "pose": [21.0, 15.0, 0.0], "state": "EXPLORING", "battery_pct": 71, "last_seen": 50.3}],
    "survivors": [{"id": "S1", "pos": [37.1, 25.8], "by": "R2", "reported_t": 141.0, "conf": 0.93}],
    "relays": [{"id": "RL1", "pos": [9.5, 15]}]
  },
  "stats": {"robots": 3, "relays": 2, "links_up": 4, "delivered": 120, "in_flight": 7}
}
```

`event.kind` values: `survivor_found`, `survivor_reported`, `relay_dropped`, `link_lost`, `link_restored`, `fault`, `replan`, `safety_reject`, `bundle_delivered`, `rubble_fall`.

### Phones: `WS /ws/phone?client=<id>&role=planner|relay`

| Direction | `t` | `data` |
| --- | --- | --- |
| server to phone | `hello` | floor plan, robots, current plan, your relay id if role = relay |
| server to phone | `cmd_view` (2 Hz) | the `command` block only, phones never see Reality |
| server to phone | `plan_state` | full current plan (CRDT later) |
| server to phone | `safety` | safety result for the last submit |
| server to phone | `relay_state` | `{id, on, queue, neighbors}` |
| phone to server | `plan_edit` | a plan or a CRDT update |
| phone to server | `plan_submit` | `{plan_id}`, server answers with `safety` |
| phone to server | `relay_power` | `{on: true or false}` |
| phone to server | `relay_place` | `{pos: [x, y]}` (tap on the floor plan) |

### REST

| Endpoint | Body | Returns |
| --- | --- | --- |
| `GET /api/health` |  | `{ok, tick, time}` |
| `GET /api/floorplan` |  | floor plan JSON |
| `POST /api/control` | `{action, value}` | `{ok}` (same as the WS control, handy for curl) |
| `POST /api/plan` | search plan | safety result |
| `POST /api/dispatch` | `{plan_id}` | `{ok}` or safety result with violations |
| `POST /api/fault` | `{type: "rubble", at: [x, y]}` or `{type: "overcurrent", robot: "R1"}` | `{ok}` |
| `GET /api/report` |  | `{text}` from Gemini, also pushed as `report` |
| `GET /api/join` |  | phone join URL for the QR code |

### Inside the server

Robots append bundles to their own `robot.outbox` (there is no `io.radio.send`). Each tick the DTN layer moves bundles along up links (bandwidth limited by RSSI), with custody per hop. Bundles that reach `CMD` are handed to `command/post.py`, which updates the Command view. Commands, plans and robot-to-robot telemetry (for target sharing) flow the other way as bundles with `dst` = robot id or broadcast, delivered into a `robot.inbox`. The broadcaster reads the sim and `post` after the tick and never mutates anything. The sim currently also emits `link_up` and `link_down` events for every node pair.

### Gemini tools

`reports.py` exposes read-only functions to Gemini through function calling: `get_robots()`, `get_survivors()`, `get_network()`, `get_coverage()`, `get_events(since)`. They read the **Command** view only, so the briefing never contains something the command post could not know. Use the current Flash model listed in the Gemini API docs and a 10 s timeout with a canned fallback text.

## Algorithms and starting parameters

Every number below is a starting value. The 5:00 PM checkpoint includes a coverage test that tunes propagation so the corridor near the entry is solid and the east wing is dead.

### Radio propagation (Person 2)

Multi-wall model: free-space-like loss with a tuned exponent plus a fixed loss for each wall crossed on the straight line between the two nodes.

```latex
P_{rx} = P_{tx} - L_0 - 10\,n\,\log_{10}\!\left(\frac{d}{d_0}\right) - \sum_{i \in \text{walls}} L_{w,i}
```

- P\_tx 20 dBm for robots, relays and the command post. L\_0 = 40 dB at d\_0 = 1 m. n = 2.6 (cluttered collapse).
- Wall loss by material: drywall 4, brick 10, concrete 16, metal 22 dB. Each rubble polygon edge crossed costs 8 dB (the rubble material in the floor plan).
- Link hysteresis: up above -82 dBm, down below -88 dBm. Noise floor -95 dBm.
- Throughput per link per tick falls linearly from 250 kB/s at -60 dBm to 20 kB/s at -88 dBm.
- Weak links (-80 to -88 dBm) get a simulated byte error rate. Without FEC most bundles fail CRC and retry. With RS(255,223) up to 16 byte errors per block are corrected, so the transfer succeeds. Show the `fec` flag on the link line.

### Delay-tolerant routing (Person 2)

- Each tick: build the graph of up links. For each node, sort its queue by priority then age.
- If `dst` is reachable now, forward to the next hop on the cheapest path (Dijkstra, cost = 1 + (-60 - rssi)/10). Otherwise hold the bundle (store).
- Custody transfer: the receiver stores the bundle and sends a custody ack. The sender deletes only after the ack. A link that dies mid-transfer means the sender still holds it, so nothing is lost.
- Receivers dedupe by `bid`. Bundles expire after `ttl`. Relays have a 2 MB queue and drop lowest priority first.

### Relay drop rule (Rayan)

Drop a relay when all four hold: the robot still has a path to CMD, the RSSI to its upstream neighbor is below -80 dBm, it carries at least one relay, and it is at least 4 m from the last relay. Never drop inside a no-go zone. Each robot carries 2 relays. This drops the relay before the link breaks, which is what DARPA SubT teams did.

### Robot scheduler (Rayan)

Fixed-priority preemptive scheduler simulated at 1 ms resolution inside each 100 ms tick. Rate monotonic priorities:

| Task | Period (ms) | WCET (ms) | Priority |
| --- | --- | --- | --- |
| Safety / fault protection | 50 | 2 | 0 |
| Motion control | 100 | 8 | 1 |
| Comms | 200 | 10 | 2 |
| Mapping | 200 | 25 | 3 |
| Perception | 500 | 40 | 4 |
| Battery | 1000 | 2 | 5 |

Total utilization is 0.377, under the Liu and Layland bound for 6 tasks:

```latex
U = \sum_i \frac{C_i}{T_i} = 0.377 \le n\left(2^{1/n} - 1\right) = 0.735
```

The demo can spike perception cost (model inference) to show a deadline miss and the safety task still preempting. Judges who know RTOS will notice this.

### Exploration and planning (Rayan)

- Frontier = known-free cell with an unknown 4-neighbor. One BFS from the robot over inflated free cells finds reachable frontiers. Group them into clusters.
- Score per cluster = size - 1.5 x distance - 40 if within 4 m of another robot's target + zone priority bonus. Coordination happens through targets shared in telemetry bundles, so robots out of contact may overlap, which is realistic.
- A\*: 8-connected, octile heuristic, inflation 1 cell (0.25 m, 2 cells would close the 1.2 m doors), no-go cells blocked, extra cost near hazards. Replan when a path cell turns occupied, after a stuck fault, or on a new command.
- Frontiers that fail twice are blacklisted.

### Battery and motor (Rayan)

- 90 Wh pack, cruise 0.8 m/s. Power = 8 W idle + 5 W compute + 2 W radio + 30 W x (v / 1 m/s).
- Return trigger: battery % minus the % needed to drive home along the A\* path (x 1.25 margin) drops to the 20% reserve.
- Wheel current = 1.5 A + 2.5 A x v, spikes above 6 A when pushing against rubble.

### Fault protection FSM (Rayan)

`NOMINAL` to `OVERCURRENT` (current above 6 A for 0.5 s): stop, reverse 0.5 m, mark cells ahead occupied, go to `REPLANNING`. `NOMINAL` to `STUCK` (commanded v above 0.2 m/s but under 5 cm moved in 3 s): same recovery. `LOW_BATTERY` goes to `RETURNING_HOME`. Three faults in 60 s goes to `SAFE_STOP` and raises a priority-1 fault bundle.

### Lost-link behavior (Rayan)

No path to CMD for 2 s puts the robot in `LOST_LINK_EXPLORING`. It keeps exploring for the plan's `lost_link_budget_s` (default 45 s), or returns at once if it finds a survivor. In `RETURNING_TO_SIGNAL` it A\*s back to the most recent breadcrumb where the link was up. Once the link is back and the outbox drains (or 10 s pass) it resumes exploring.

### Safety checker (Person 2)

Planning uses the pre-collapse floor plan as the prior (rubble is unknown). For each zone assignment: route length entry to zone centroid by A\*, coverage distance = zone area / 8 m swath, energy = (to + coverage + back) / v x cruise power. Reserve % = (current Wh - energy) / capacity. Reject below 20%. Also reject capability mismatches, zones overlapping a no-go area, unreachable zones, and zones whose centroid predicts below -88 dBm with no relay chain unless the zone is marked `lost_link_ok`.

### Survivor detector (Rayan)

- Data: person boxes from the FLIR thermal dataset (COCO-style labels). Positives = person crops, negatives = random background crops of matching size. About 3,000 of each, resized to 96 x 96.
- Model: torchvision ResNet18 or MobileNetV3-Small pretrained on ImageNet, final layer swapped for 2 classes, 3 to 5 epochs.
- Report: accuracy, precision, recall and a confusion matrix PNG on a held-out split. Put it on the Devpost and a slide.
- Runtime: each survivor in the floor plan gets a held-out positive crop. Add 3 decoy hot spots (radiator, engine, coffee machine) with held-out negative crops so judges see the model reject false heat. Threshold 0.6. `DETECTOR=sim` env var switches to the fallback sensor.
- Start the dataset download right away. It is several GB and may need a sign-up form. If it is blocked, use a Kaggle mirror of the same dataset.

## Hour-by-hour plan

The plan assumes hacking ends Sunday around 1:30 PM (24 hours). Confirm the exact Devpost deadline on the official schedule and shift the last block if it differs. Rayan's 1:30 to 5:00 PM robot items are already done in the starter (see Current status), so Rayan starts on the 5:00 PM work now. Everyone merges a PR into `main` at least every hour, and nobody edits another person's folder without asking.

| Time | Rayan (robots + ML) | Person 2 (sim, network, command) | Person 3 (3D, panels, phone) |
| --- | --- | --- | --- |
| 1:30 to 2:00 | Unzip the starter repo, push to GitHub, start the FLIR download | Run the server, read `protocol.md` | `npm install`, run the web app against the server |
| 2:00 to 3:00 | Lidar, mapping and frontier search working in the starter | Floor plan loader, tick loop, broadcaster cleanup, propagation model | Building extrusion, robot meshes, overhead orbit camera |
| **3:00** | **Checkpoint A** |  |  |
| 3:00 to 5:00 | Survivor sim sensor, basic lost-link return, tune exploration | Coverage test and tuning, link lines, Command view syncs only while linked | Fog of war texture, Reality and Command split view, lidar rays, sidebar |
| **5:00** | **Checkpoint B (core story demoable)** |  |  |
| 5:00 to 6:00 | 3 robots and target sharing | DTN bundles and custody transfer | Phone app shell, QR join page |
| 6:00 to 8:00 | Relay drop rule, battery model, return home | Relay nodes in the link graph, store and forward through relays, `map_patch` bundles | Relay glow, link lines green and red, ghost robots, survivor burst animation |
| 8:00 to 10:00 | Breadcrumb lost-link behavior, A\* replanning | Command view fed by delivered bundles only, phone WebSocket, events | Phone floor plan with zones and hatched no-go areas |
| **10:00** | **Checkpoint C** |  |  |
| 10:00 to 12:00 | Scheduler and task timeline, fault FSM | Safety checker and plan submit, rubble fault injection | Task timeline panel, top bar, follow camera |
| 12:00 to 3:00 | Crop prep (30 min), train in background, perception integration, confusion matrix | Phone relays (`relay_power`), Reed-Solomon FEC on weak links | Safety rejection card, relay mode UI, headlights, dust, rubble meshes |
| **3:00 AM** | **Checkpoint D** |  |  |
| 3:00 to 4:30 | Sleep | Gemini reports with tool calls | Cinematic cameras, report panel |
| 4:30 to 6:00 | Demo director script, decoy hot spots, scheduler overload moment | Sleep | Polish pass on colors and type |
| 6:00 to 7:30 | Bug fixes from the first full run | Stream recorder and replay mode, CRDT only if everything else is done | Sleep |
| **7:30** | **Feature freeze** |  |  |
| 7:30 to 9:00 | README and architecture notes | Devpost write-up | Record the backup demo video |
| 9:00 to 12:00 | Rehearse the pitch 5+ times, fix only demo-breaking bugs | Same | Same |
| 12:00 | Submit to Devpost with buffer, repo public |  |  |

Meals: grab food in turns so the 5:00 and 10:00 checkpoints never slip.

## Integration checkpoints

Each checkpoint is a 10 minute stand-up at one laptop on the big screen. If a pass criterion fails, the owner fixes it before starting new work, and the cut list decides what gets dropped.

| Time | Pass criteria |
| --- | --- |
| 3:00 PM (A) | Server streams `hello` and `tick` at 10 Hz. Web app draws the building and a moving robot from streamed state. `pytest` passes. |
| 5:00 PM (B) | One robot explores the whole building on its own. Its link drops in the east wing and the Command view freezes with a ghost robot. A survivor appears on Reality only, then on Command after the robot returns to signal. |
| 10:00 PM (C) | 3 robots, relays dropped automatically, data arrives only through bundles. A phone joined by QR sees the Command view. Battery return works. |
| 3:00 AM (D) | Task timeline live, fault FSM recovers from injected rubble, safety checker rejects the battery plan, phone relay toggles reroute data, trained detector live with sim fallback. |
| 7:30 AM (freeze) | Full scripted demo runs 3 times in a row without a restart. Backup video recorded. |

## Testing plan

"It works" is the first judging criterion, so tests target the exact failures that would kill the demo. All tests run headless with `pytest -q` in under 30 s.

**Unit tests (each owner)**

- Propagation: RSSI falls with distance, each wall subtracts its material loss, a link flaps at most once when a robot sits at the threshold.
- Lidar: a beam toward a known wall returns the right range within one cell.
- A\*: finds a path around a rubble block, returns none through a sealed room, never enters no-go cells.
- Frontier: on a fully known map there are no frontiers, so the robot reports `DONE`.
- DTN: 100 bundles over a chain whose middle link toggles every 3 s all arrive exactly once.
- Safety: the demo's battery plan is rejected with `battery_reserve`, a good plan passes.
- Scheduler: utilization matches the table and the safety task never misses a deadline.

**Scenario tests (headless sim, fixed seed)**

- `test_core_story`: with seed 7, survivor S1 is found while the robot has no link and appears in the Command view afterwards (about 213 s and 222 s today with 1 robot, faster with 3).
- `test_no_leak`: the Command view never contains a survivor or map cell before a bundle carrying it was delivered.
- `test_soak`: 20 minutes of sim time at 10x speed with no exceptions and memory under 500 MB.

**Frontend checks (Person 3)**

- Load the page with the server off, then start it: the app reconnects by itself.
- Big screen holds 60 fps on the demo laptop with both views. If not, halve lidar rays and drop dust particles.
- Two phones plus the big screen on venue Wi-Fi and on a phone hotspot.

**Rehearsal tests**

Run the full 3 minute script at 9:00, 10:00 and 11:00 AM on the actual demo laptop and network, with a timer.

## Demo prep

The demo runs on a fixed seed with a director so every beat happens on cue, while the robots still act on their own between cues.

**Director keys on the big screen** (sent as `control` with `action: director`)

| Key | Action |
| --- | --- |
| Space | start or pause |
| 1 to 3 | follow cam on robot 1 to 3 |
| 0 | overhead cutaway |
| R | drop rubble in front of the followed robot |
| F | inject wheel overcurrent on the followed robot |
| G | request a Gemini briefing |
| + and - | sim speed |
| Backspace | reset to the seed |

**Script (3:00)**

| Time | Beat | Who talks |
| --- | --- | --- |
| 0:00 | Hook: "In a collapse the radio dies first. Today's rescue robots stop when the signal stops." | Rayan |
| 0:15 | Two judges scan the QR. One assigns Robot 2 to the far zone, the safety card rejects it with the exact reason | Person 3 |
| 0:40 | Space. Robots enter, lidar sweeps, map grows, relays drop as signal weakens | Person 2 |
| 1:05 | "Your phone is relay 3, turn it off." Chain breaks, bundles hold, then reroute | Person 2 |
| 1:30 | Robot 2 goes dark, keeps exploring, finds a survivor on the Reality side only. The AI card shows the thermal image the onboard detector judged ("Person, 100%"), next to a decoy it rejected. Point at the ghost robot on the Command side | Rayan |
| 1:55 | Press R. Rubble blocks the corridor, the task timeline shows the safety task preempt, robot replans | Rayan |
| 2:20 | Robot 2 reconnects, map and survivor burst onto the Command view. Press G, Gemini briefing appears | Person 3 |
| 2:45 | Close: "The robots are autonomous, and AI detects survivors. Collapsed buildings, mines, wildfires, tunnels." | Rayan |

**Backups, in order of use**

1. Live demo on venue Wi-Fi.
2. Same demo with all devices on a phone hotspot.
3. Replay mode: the recorded WebSocket stream of a perfect run, played into the same frontend. Looks identical and needs no sim.
4. The backup video (also uploaded to Devpost).

**Laptop setup:** charger in, notifications off, browser zoom set, a second tab with the confusion matrix, a third with the GitHub repo. Prepare one answer each for: "Is the AI driving the robot?", "How do you know the command view isn't cheating?", "How would this run on real robots?"

## Devpost outline

Write it at 7:30 AM from this skeleton. Lead with the GIF of the split view at the reconnect moment.

1. **Tagline:** Rescue robots that keep searching where the signal dies.
2. **Inspiration:** collapsed buildings, mines and tunnels kill radio. DARPA SubT showed autonomy plus dropped relays works. Most fielded robots still stop on link loss.
3. **What it does:** responders plan on phones, a safety checker blocks unsafe dispatches, robots explore and drop relays, data hops through relays and phones with store and forward, survivors reach the command post when the link returns, Gemini briefs responders.
4. **How we built it:** one paragraph per layer (robots, network, command post, ML, 3D). Mention the multi-wall propagation model, custody transfer, rate monotonic scheduler with the 0.377 utilization number, frontier exploration, A\*, Reed-Solomon.
5. **The ML:** dataset, model, accuracy, precision, recall, confusion matrix image, decoy hot spots.
6. **Challenges:** proving the Command view never leaks truth, tuning propagation so the story happens in a real-looking building, keeping 60 fps with two 3D views.
7. **Accomplishments:** the core loop works end to end with no faked data path.
8. **What we learned**
9. **What's next:** multi-floor, real ROS 2 robots running the same robot module, mesh radios.
10. **Built with:** Python, FastAPI, numpy, PyTorch, Gemini API, React, three.js, react-three-fiber, Reed-Solomon.

Attach: demo video link, repo link, 4 screenshots (split view, phone safety card, task timeline, confusion matrix). Tick the prize categories: Best General, Best AI/ML, Most Over Engineered, Best UI/UX, MLH Best Use of Gemini API.

## Cut order and risks

The core story (explore, lose signal, find survivor, report later) survives every cut. Cut in this order at the first checkpoint that slips:

1. CRDT co-planning (one planner phone is fine)
2. Reed-Solomon (keep the weak-link color, drop the coding)
3. Phone relays (virtual relays only)
4. Trained detector (sim sensor still works)
5. Fancy 3D effects (keep building, robots, fog of war and split view)

| Risk | Mitigation |
| --- | --- |
| Phones cannot reach the laptop on venue Wi-Fi | Phone hotspot for all devices, or a `cloudflared` quick tunnel |
| FLIR dataset download blocked or slow | Start now, Kaggle mirror as backup, sim sensor fallback |
| Two WebGL canvases drop frames | Use drei `View` to share one context, cut particles |
| Signal never drops in the demo or drops everywhere | Coverage test at 5:00 PM, tune `n` and wall losses only |
| Gemini quota or timeout on stage | 10 s timeout, canned briefing generated from the same tool data |
| Live demo crashes | Replay mode, then the backup video |
