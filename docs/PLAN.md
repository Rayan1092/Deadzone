# Deadzone Build Plan (UB Hacking 2026)

Nov 7, 2026 · @Rayan Diya

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
| Coordinates | meters, origin bottom-left, x east, y north, heading in radians CCW from +x | three.js maps sim (x, y) to (x, 0, y) with y up |
| Randomness | one seeded RNG per run | the demo replays identically |

**Honesty rule.** Robot code never reads the World directly. It only sees the world through `sense_lidar()` and only talks to other nodes through network bundles. This keeps the Reality vs Command split real, and it is what you tell judges when they ask whether it is faked.

**Two knowledge views.** Reality = ground truth plus every robot's own map. Command = only what has physically arrived at the command post node through the network. The gap between them is the whole demo.

**AI boundaries.** Autonomy = our algorithms (frontier search, A\*, relay rules, state machines). Trained AI = survivor detector only. Gemini = situation reports through tool calls only.

## Repo structure and module ownership

Three top-level folders map to three people, and the only shared files are `protocol.py` and `docs/protocol.md`. Anyone changing a message shape posts it in the team chat first.

| Path | What it holds | Owner |
| --- | --- | --- |
| `docs/protocol.md` | every message and data format (source of truth for the frontend) | Person 2, everyone reviews |
| `data/floorplans/collapse_01.json` | the demo building | Rayan |
| `server/deadzone/protocol.py` | pydantic models for every message | Person 2 |
| `server/deadzone/app.py` | FastAPI app, WebSocket and REST endpoints, broadcaster | Person 2 |
| `server/deadzone/sim.py` | fixed-tick loop, scenario setup, demo director | Person 2 |
| `server/deadzone/world.py` | truth grid, robots, relays, survivors, rubble events | Person 2 |
| `server/deadzone/floorplan.py` | load floor plan JSON, rasterize walls and rubble | Person 2 |
| `server/deadzone/network/propagation.py` | multi-wall path loss, link graph with hysteresis | Person 2 |
| `server/deadzone/network/dtn.py` | bundles, custody transfer, store and forward routing | Person 2 |
| `server/deadzone/network/fec.py` | Reed-Solomon wrapper (`reedsolo` package) | Person 2 |
| `server/deadzone/command/` | `post.py` command knowledge, `plan.py` plans, `safety.py`, `reports.py` (Gemini) | Person 2 |
| `server/deadzone/robot/robot.py` | Robot class, owns its map, state and outbox | Rayan |
| `server/deadzone/robot/scheduler.py` | RTOS-style priority scheduler and task timeline | Rayan |
| `server/deadzone/robot/lidar.py` `mapping.py` | raycast sensor, occupancy grid | Rayan |
| `server/deadzone/robot/frontier.py` `astar.py` | frontier search, multi-robot split, A\* replanning | Rayan |
| `server/deadzone/robot/power.py` `faults.py` `behavior.py` | battery and motor model, fault FSM, top-level FSM incl. lost link and relay drop | Rayan |
| `server/deadzone/robot/perception.py` | survivor detection (sim sensor + trained model) | Rayan |
| `ml/` | `prepare_crops.py`, `train.py`, `eval.py`, `thermal_samples/`, `detector.pt` | Rayan |
| `server/tests/` | pytest unit and scenario tests | each owner for their modules |
| `web/src/net/` `web/src/store.js` | WebSocket client and zustand store | Person 3 |
| `web/src/three/` | Building, Robots, Lidar, Fog, Relays, Survivors, Cameras, SplitView | Person 3 |
| `web/src/panels/` | TopBar, Sidebar, Timeline, ReportPanel | Person 3 |
| `web/src/phone/` | PlanMap, Zones, SafetyCard, RelayMode | Person 3 |
| `scripts/` | `record.py` (save the WS stream), replay mode, demo launcher | Person 2 |

**The robot boundary.** The sim calls `robot.step(dt, io)` once per tick. `io` is the only door to the outside world:

- `io.lidar()` returns ranges for each beam from the robot's true pose
- `io.thermal(x, y)` returns a thermal crop id when a survivor is in view, else `None`
- `io.drive(v, w)` sets wheel command, the sim integrates motion and checks collisions
- `io.radio.send(bundle)`, `io.radio.inbox()`, `io.radio.neighbors()` with RSSI per neighbor
- `io.drop_relay()` places a relay node at the robot's position if it still carries one
- `io.odometry()` returns pose plus wheel current (for fault detection)

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

`state` values: `IDLE`, `DEPLOYING`, `EXPLORING`, `LOST_LINK_EXPLORING`, `RETURNING_TO_SIGNAL`, `RETURNING_HOME`, `REPLANNING`, `FAULT`, `DONE`. `tasks` is the scheduler timeline for the last 100 ms frame in virtual ms (0 to 100). `lidar` holds beam endpoints for drawing.

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

`kind` and priority (0 = highest): `survivor` 0, `fault` 1, `command` 1, `plan` 1, `telemetry` 2, `map_patch` 3. A `map_patch` payload is `{"robot": "R2", "cells": "<base64 of uint8 list of [ix, iy, value] triples>"}` holding only cells changed since the last patch that got custody.

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

Robots push bundles into their own outbox through `io.radio.send`. Each tick the DTN layer moves bundles along up links (bandwidth limited by RSSI), with custody acks per hop. Bundles that reach `CMD` are handed to `command/post.py`, which updates the Command view. Commands and plans flow the other way as bundles with `dst` = robot id. The broadcaster reads `world` and `post` after the tick and never mutates anything.

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
- Wall loss by material: drywall 4, brick 10, concrete 16, metal 22 dB. Rubble polygons count as concrete.
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
- A\*: 8-connected, octile heuristic, inflation 2 cells (0.5 m), no-go cells blocked, extra cost near hazards. Replan when a path cell turns occupied, after a stuck fault, or on a new command.
- Frontiers that fail twice are blacklisted.

### Battery and motor (Rayan)

- 90 Wh pack, cruise 0.8 m/s. Power = 8 W idle + 5 W compute + 2 W radio + 30 W x (v / 1 m/s).
- Return trigger: battery % minus the % needed to drive home along the A\* path (x 1.25 margin) drops to the 20% reserve.
- Wheel current = 1.5 A + 2.5 A x v, spikes above 6 A when pushing against rubble.

### Fault protection FSM (Rayan)

`NOMINAL` to `OVERCURRENT` (current above 6 A for 0.5 s): stop, reverse 0.5 m, mark cells ahead occupied, go to `REPLANNING`. `NOMINAL` to `STUCK` (commanded v above 0.2 m/s but under 5 cm moved in 3 s): same recovery. `LOW_BATTERY` goes to `RETURNING_HOME`. Three faults in 60 s goes to `SAFE_STOP` and raises a priority-1 fault bundle.

### Lost-link behavior (Rayan)

No path to CMD for 2 s puts the robot in `LOST_LINK_EXPLORING`. It keeps exploring for the plan's `lost_link_budget_s` (default 60 s), or returns at once if it finds a survivor. In `RETURNING_TO_SIGNAL` it A\*s back to the most recent breadcrumb where the link was up. Once the link is back and the outbox drains (or 10 s pass) it resumes exploring.

### Safety checker (Person 2)

Planning uses the pre-collapse floor plan as the prior (rubble is unknown). For each zone assignment: route length entry to zone centroid by A\*, coverage distance = zone area / 8 m swath, energy = (to + coverage + back) / v x cruise power. Reserve % = (current Wh - energy) / capacity. Reject below 20%. Also reject capability mismatches, zones overlapping a no-go area, unreachable zones, and zones whose centroid predicts below -88 dBm with no relay chain unless the zone is marked `lost_link_ok`.

### Survivor detector (Rayan)

- Data: person boxes from the FLIR thermal dataset (COCO-style labels). Positives = person crops, negatives = random background crops of matching size. About 3,000 of each, resized to 96 x 96.
- Model: torchvision ResNet18 or MobileNetV3-Small pretrained on ImageNet, final layer swapped for 2 classes, 3 to 5 epochs.
- Report: accuracy, precision, recall and a confusion matrix PNG on a held-out split. Put it on the Devpost and a slide.
- Runtime: each survivor in the floor plan gets a held-out positive crop. Add 3 decoy hot spots (radiator, engine, coffee machine) with held-out negative crops so judges see the model reject false heat. Threshold 0.6. `DETECTOR=sim` env var switches to the fallback sensor.
- Start the dataset download right away. It is several GB and may need a sign-up form. If it is blocked, use a Kaggle mirror of the same dataset.

## Hour-by-hour plan

The plan assumes hacking ends Sunday around 1:30 PM (24 hours). Confirm the exact Devpost deadline on the official schedule and shift the last block if it differs. Everyone pushes to `main` at least every hour with small commits, and nobody edits another person's folder without asking.

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

- `test_core_story`: with seed 7, survivor S1 is found by 150 s sim time and appears in the Command view by 220 s.
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
| 1:30 | Robot 2 goes dark, keeps exploring, finds a survivor on the Reality side only. Point at the ghost robot on the Command side | Rayan |
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
