# Rayan Diya: robots + ML

Owns `server/deadzone/robot/`, `ml/`, `data/floorplans/`. Only Rayan's sessions edit this file.

## Now
- **Working on:** `rayan/rescue-route` (PR open): safe A* route entrance → survivor sent to CMD (priority 1), beacon relay when the survivor is in a dead zone. Owners/targets: Added scope table in `docs/PLAN.md`.
- **Works on main:** frontier exploration, 3-robot target sharing, relay auto-drop, A* return home, lost-link + 10 s reconnect hold, REPLANNING around rubble, rate monotonic scheduler with carry-over and deadline misses, full fault FSM (OVERCURRENT, STUCK, SAFE_STOP, LOW_BATTERY, TRAPPED), SAFE_STOP resume command (PR #13), robots follow dispatched plans (PR #15), robots perceive through the trained detector with decoys in the floor plan (PR #14 + #17). Seed 7, 3 robots: S1 found dark at 182.3 s, on Command at 187.3 s, 4 relays.
- **In flight (not merged):** `rayan/rescue-route`: rescue route + beacon. On main: `docs/DEMO.md`, `survivor_found.crop/conf`, `hotspot_rejected` (PR #19), PLAN.md Added scope (PR #21), detector hookup + decoys (PR #17).
- **Blocked on / need from others:** Aziz: `/crops` static, `hello.detector`, `rescue_route` in PRIO + `command.routes` (rescue-route entry). Yusuf (all agreed, 3 AM): survivor figures, bigger robots, phone robot tap, liquid glass, rescue route drawing from `command.routes`, robot's-eye view (his). Done on main: decoys in thermal + none in fallback, O / U resume, detection cards, detector chip (waits for `hello.detector`). Details in the Blocked sections below; owners/targets in `docs/PLAN.md` Added scope. Keep `PEER_FRESH_S` in robot.py (sim.py imports it).
- **Promises to others:** states final: DEPLOYING, EXPLORING, LOST_LINK_EXPLORING, RETURNING_TO_SIGNAL, RETURNING_HOME, REPLANNING, FAULT, DONE. Faults final: null, OVERCURRENT, STUCK, LOW_BATTERY, TRAPPED, SAFE_STOP. `tasks` slices as in PR #7, `missed` can now be true. Robot hooks: `inject_overcurrent(seconds=1.0)`, `inject_perception_overload(seconds=3.0, wcet_ms=400)`.

## Log

### 2026-11-07 20:30 · rayan/rescue-route · Rescue route + beacon relay
- **Did:** when a robot confirms a survivor (first confirmation only; robots skip survivors a peer already reported, via the `found` list in peer telemetry) it computes the safest A* route **from the entrance to the survivor on its own map**: known free cells only, never through rubble, walls, unknown space or no-go areas, centered by the wall cost, with a cost band 1 m around hazards. It sends the route to CMD as a **priority-1 bundle**, so Command only knows it when it arrives. If the survivor is in a **dead zone** (robot has no link) and the robot still has a relay, it also drops a **beacon relay** next to them; where there is coverage no beacon is needed (Rayan's call: beacons in covered areas reshaped the relay network and removed the S1 dark moment). Seed 7 demo plan: S3 route 14.2 m at 14.4 s (instant); S1 found dark at 129.0 s, beacon RL2 in the cage, 49.7 m route delivered to CMD at 143.1 s with the survivor report; every DEMO.md beat unchanged. 150 tests pass (model and `DETECTOR=sim`).
- **Contract changes:**
  - Robot event (Reality knowledge, at computation): `rescue_route {robot, survivor, path:[[x,y],...], length_m, clearance_m, beacon}`. `path` starts at the entrance `[1.0, 15.0]` and ends at the survivor position; `beacon` is the relay id (e.g. `"RL2"`) or null.
  - Bundle to CMD: `kind:"rescue_route"`, `prio:1`, payload `{survivor, by, path, length_m, clearance_m, beacon, t}`. Delivery raises the existing `bundle_delivered` event with `bundle_kind:"rescue_route"`.
  - The beacon is a normal relay: it raises the usual `relay_dropped` event and shows in `reality.relays`.
- **Heads-up for others:** Yusuf: draw routes on **Command only from delivered data** (Aziz's `command.routes`, below), never from the robot's `rescue_route` event, which is Reality knowledge. The Reality pane may draw from the event. Phones get routes through `cmd_view` once Aziz adds them.
- **Blocked:**
  - **Aziz:**
    1. `network/dtn.py`: add `"rescue_route": 1` to `PRIO`. Robots already send the bundle with `prio:1` (built from a known kind until then), so nothing breaks today.
    2. `command/post.py`: on a delivered `rescue_route` bundle, keep one route per survivor (newest `t` wins) and expose it in the Command view as `routes: [{survivor, by, path, length_m, clearance_m, beacon, reported_t}]` (also in phone `cmd_view`). Raise event `rescue_route_reported {survivor, by, length_m, delay_s}`.
  - **Yusuf:** draw `command.routes[]` on the Command pane: a bright dashed line from the entrance to the survivor with "Route to S1 · 49.7 m" at the survivor end, and the beacon relay highlighted when `beacon` is set. Same on the phone map from `cmd_view.routes`.
- **Next:** ML slide for the freeze. (Yusuf took all five asks incl. the robot's-eye view; Aziz's O / resume / decoys are on main and DEMO.md now lists O and U as live. Re-checked on merged main with native decoys: all beats unchanged.)

### 2026-11-07 19:50 · rayan/scope-sync · Added scope (5:45 PM) in docs/PLAN.md
- **Did:** committed Rayan's updated `docs/PLAN.md`, which has a new **"Added scope (5:45 PM Saturday)"** table: owners and target times for the AI detection card, detector chip, decoy safety, rescue route + beacon, survivor figures, robot's-eye view, liquid glass, ML slide. Also final states/faults/tasks/relay_dropped wording and names in the roles table.
- **Contract changes:** none in this commit (rescue route contract comes with `rayan/rescue-route`).
- **Heads-up for others:** **Aziz and Yusuf: the Added scope table in `docs/PLAN.md` is the source for owners and targets (10 PM / 3 AM).** Aziz's six asks are already in my earlier entries (detector-hookup, safe-stop-resume and detection-events entries): `/crops/<file>` static, `hello.detector`, no decoys in sim fallback, decoys from `RobotIO.thermal()` with survivor rules, O → `inject_perception_overload`, resume director action.
- **Blocked:** **Yusuf**, new asks on top of the chip / survivor figure / detection cards already posted. Please tell me in your history file which of these you can fit:
  1. Robots bigger and brighter so they read from across the room (both panes).
  2. Robot's-eye picture-in-picture: click a robot → small view from its camera (pose + heading from Reality telemetry `pose`), with a **Thermal** toggle (walls cold blue; survivors and decoys glow). Render small and only while open; cut first if time is short. **My session can build this in `web/` if you OK it** (say so in your file and name the component path you want).
  3. Phone: tap a robot card to see its status and last thermal crop. Phones only see Command, so use the delivered survivor records: `cmd_view.survivors[].crop` (and `by` for the robot), image `/crops/<crop>`.
  4. Liquid-glass styling (frosted translucent panels, cards, phone UI).
  5. Draw the rescue route on the **Command** view when it arrives. Contract coming from my next PR (`rayan/rescue-route`); I'll post it here.
- **Next:** rescue route + beacon relay.

### 2026-11-07 19:40 · rayan/demo-runbook · DEMO.md updated for M4 keys
- **Did:** runbook key table and beats follow Yusuf's M4: 1–3 / 0 follow cams, R and F act on the followed robot, F and G are live keys. Beats now say which robot to follow before R / F / O.
- **Contract changes:** none
- **Heads-up for others:** none
- **Next:** scope sync PR, then rescue route.

### 2026-11-07 19:20 · rayan/demo-runbook · docs/DEMO.md demo runbook
- **Did:** wrote `docs/DEMO.md`: seed 7, 3 robots, 2x, plan P-1 (R1 west offices, **R2 north-east + steel cage as the dark zone**, R3 break room) preloaded, judges fix it on the phone ("Allow ZNE to go dark") and dispatch before Space. Beat sheet measured headless on merged main with the model live: S3 at +0:07, radiator rejected +0:28, RL1 +0:29, R2 dark +0:59.5, **S1 found dark +1:04.5, on Command +1:11.5 (14.1 s late)**, then R / F / O / G beats, all rehearsed in the dry run. Every director key with status, lines to say per beat, PowerShell plan / fault / report fallbacks, recovery table, judge answers. Also: `_read_commands` now learns peer telemetry if `io.radio.receive()` hands any over (PR #12 drains `robot.inbox` too), so peers can't be lost if the read order changes. 146 tests pass with the model and with `DETECTOR=sim`.
- **Contract changes:** none
- **Heads-up for others:** everyone: read `docs/DEMO.md` before the first rehearsal; the beat times assume P-1 with ZNE dark-OK dispatched before Space. Yusuf: F / G / O keys (M4) are the only missing keys in the runbook. Aziz: O (overload) and resume director values are still open (see the safe-stop-resume entry).
- **Next:** task 6 director pieces when O / resume / decoys land; rehearsal fixes.

### 2026-11-07 18:55 · rayan/demo-runbook · Detection events carry the crop and confidence
- **Did:** `survivor_found` events now carry the thermal crop file the detector scored and its confidence. New `hotspot_rejected` event when the detector turns a hot spot down (once per robot per hot spot). Survivor records (and so the Command view after delivery) carry `crop`. 115 tests pass with the model and with `DETECTOR=sim`.
- **Contract changes:**
  - `survivor_found` gains `crop` (file name, e.g. `"pos_0001.png"`) and `conf` (0 to 1, model probability; 0.99 in sim fallback).
  - New event `hotspot_rejected {robot, id, pos:[x,y], crop:"neg_0001.png", conf}` (conf below 0.6). The robot doesn't know it's a decoy, only "hot but not a person"; `id` is the hot spot id (D1 to D3).
  - Command `survivors[]` records gain `crop`.
- **Heads-up for others:** none beyond the asks below.
- **Blocked:**
  - **Aziz:**
    1. Put detector status in `hello` (screen and phone): `"detector": "model"` or `"sim"`, from `deadzone.robot.perception.get_detector().mode`; optional `"detector_reason"` from `.reason` when in sim.
    2. When `get_detector().mode == "sim"`, `RobotIO.thermal()` must **not** emit decoys (my earlier decoy ask, plus this guard). A missing PyTorch must never put a radiator on screen as a survivor.
    3. Serve `ml/crops/runtime/` as static files at **`/crops/<file>`** (e.g. `/crops/pos_0001.png`) so the big screen can show what the detector saw.
  - **Yusuf:**
    1. Top-bar chip from `hello.detector`: `"model"` → "Detector: AI model", `"sim"` → "Detector: sim fallback" (warning colour).
    2. Replace the survivor dot with a low-poly person lying down with a warm thermal glow; keep the pulsing ring. Reality and Command both.
    3. On `survivor_found`, a small card on the **Reality** pane: thermal image from `/crops/<event.crop>`, "person, 100%" from `event.conf`, robot `event.robot`, survivor `event.survivor`, and "no link, holding report" when `event.linked` is false.
    4. On `hotspot_rejected`, the same card style: image `/crops/<event.crop>`, "not a person, 0%" from `event.conf`, robot `event.robot`. Reality only, never Command.
    5. Command side can show the crop after delivery from `command.survivors[].crop`.
- **Next:** `docs/DEMO.md` runbook.

### 2026-11-07 18:15 · rayan/detector-hookup · Trained detector live in robot perception, decoys in the floor plan
- **Did:** robots now run every thermal hot spot through the trained detector (`filter_hits(io.thermal())`, PR #14's module); found survivors carry the model's probability as `conf`. Sim sensor fallback when `DETECTOR=sim`, no torch or no model. Added 3 decoys to collapse_01.json. Seed 7, 3 robots, model live (decoys injected into thermal by a test harness the way Aziz's change will): S1 dark at 182.3 s by R1 (conf 1.0) → Command 187.3 s, S2 225.1 s (0.889), S3 18.0 s (0.999); decoys in view D1 69 / D2 332 / D3 10 ticks, none reported. 115 tests pass with the model and with `DETECTOR=sim`.
- **Contract changes:** **floorplan** gains `"decoys": [{"id","label","pos","thermal"}]`: D1 radiator (15, 28) `neg_0001.png`, D2 engine (37, 12) `neg_0002.png`, D3 coffee machine (22, 28) `neg_0003.png`. Survivor `conf` is now the model probability (was always 0.99).
- **Heads-up for others:** whoever runs the demo laptop: install CPU torch or the model is not used and decoys (once Aziz's change lands) show up as survivors: `py -m pip install torch torchvision pillow --index-url https://download.pytorch.org/whl/cpu` (pillow from PyPI if the index lacks it). The server log says `survivor detector: sim sensor fallback (...)` when it isn't loaded. Yusuf: optional faint decoy markers on Reality only (never Command), labelled from `decoys[].label`.
- **Blocked:** Aziz, please make `RobotIO.thermal()` in `sim.py` also return decoys from `fp.data["decoys"]`, with exactly the survivor rule and shape: within `THERMAL_RANGE`, inside `THERMAL_FOV`, `line_of_sight`, hit `{"id": d["id"], "pos": (x, y), "crop": d["thermal"], "conf": 0.99}`. The robot's detector rejects them; no flag telling the robot it's a decoy (that would be cheating). Safe to merge any time after this PR is on main.
- **Next:** task 6 director pieces once Aziz wires O / resume / decoys.

### 2026-11-07 17:40 · rayan/plans · Robots follow dispatched plans
- **Did:** a `plan` bundle from CMD (Aziz's `/api/dispatch`, read with `io.radio.receive()`) now drives the robot. While reachable frontiers touch its zone (priority 1 first) it picks only among them; before the zone is on its map it is pulled toward it; once 80% of the zone is mapped it helps anywhere. The plan's `no_go` polygons join the robot's no-go mask (never planned through; a newer plan replaces them). `lost_link_budget_s` replaces the 45 s default. No relay drops inside a `lost_link_ok` zone. Seed 7: Office B zone reached at 21 s instead of 97 s. Demo-style plan (R2 east wing `lost_link_ok`): R2 finds S1 dark at 180.9 s, on Command at 186.0 s.
- **Contract changes:** new event `plan_applied {robot, plan_id, zones:[ids]}` raised when the robot actually starts following a plan. Telemetry gains `plan_id` (or null) and `zone` (active zone id or null).
- **Heads-up for others:** Yusuf: show "following P-7 / zone Z1" from `plan_id`/`zone`, and only after `plan_applied` (a dispatch is not proof the robot got it). Aziz: nothing needed; dispatch already works end to end. Demo plan tip: give the robot that should go dark a `lost_link_ok` zone over the east wing, otherwise relays may light it up.
- **Next:** detector hookup (after the ML PR merges), then task 6 decoys.

### 2026-11-07 17:10 · rayan/safe-stop-resume · SAFE_STOP can be resumed from CMD
- **Did:** robots now read `io.radio.receive()` every step. A `command` bundle with payload `{"cmd": "resume"}` clears SAFE_STOP and the fault counter, raises a `resumed` event, then the robot replans and carries on. Plan bundles that arrive are stored on the robot (acted on in `rayan/plans`). The resume only reaches a robot that has a route to CMD; a robot that safe-stopped in a dead zone stays stopped until a relay reaches it (realistic, by design).
- **Contract changes:** new command bundle `kind:"command"`, `src:"CMD"`, `dst:<robot id>`, `payload:{"cmd":"resume"}` (builder `deadzone.robot.robot.resume_command(rid, now)`). New event `resumed {robot}`.
- **Heads-up for others:** Yusuf: optional toast for the `resumed` event.
- **Blocked:** Aziz, please wire two director values in `app.py` (nothing else needed from my side):
  1. Key **O** → `control {action:"director", value:{do:"overload", robot:"R1"}}` → `sim.robots[robot].inject_perception_overload()`. The scheduler overload moment: perception misses deadlines for 3 s, safety never does.
  2. `{do:"resume", robot:"R1"}` → `sim.network.queues["CMD"].append(resume_command(robot, sim.time))` with `from .robot.robot import resume_command`. Must go through the CMD queue, never straight into the robot, so it obeys the network like every other bundle.
- **Next:** robots follow dispatched plans.

### 2026-11-07 16:56 · rayan/scheduler-faults · PR #8 Scheduler overload and full fault FSM
- **Did:** scheduler carries unfinished jobs across frames, flags slices past their deadline `missed: true`, skips a release while the previous job overruns. `inject_perception_overload()` makes perception cost 400 ms for 3 s: about 1 perception deadline miss per second, safety never misses (still runs at 0 and 50 ms). Fault FSM: OVERCURRENT and STUCK stop, back up 0.5 m, mark ahead, REPLANNING; 3rd motion fault within 60 s gives SAFE_STOP (state FAULT, wheels off); LOW_BATTERY label while heading home; every fault sends a priority-1 `fault` bundle `{robot, fault, pos, t, state}` to CMD.
- **Contract changes:** new event `deadline_miss {robot, task}`. `fault` events now cover all 5 values. `tasks[].missed` can be true. New robot hook `inject_perception_overload(seconds=3.0, wcet_ms=400)`.
- **Heads-up for others:** Aziz: please wire a director key for `sim.robots[rid].inject_perception_overload()` (suggest O). Pressing F 3 times on one robot within 60 s puts it in SAFE_STOP (until the resume command lands next). Yusuf: red `missed` slices and `deadline_miss` events now really happen. Yusuf: the `.claude` hooks call `python3` and match only the Bash tool; on Rayan's Windows laptop only `py` exists and commits go through PowerShell, so neither hook runs there (Rayan's Claude follows the rules by hand).
- **Next:** SAFE_STOP resume command, then robots follow dispatched plans.

### 2026-11-07 · rayan/timeline-contract · PR #7 Timeline contract (merged)
- **Did:** scheduler records per-robot task pieces. Overcurrent fault hook. Final state list.
- **Contract changes:** telemetry gains `tasks`: per robot, `[{name,start,dur,missed}]` over the last 100 ms (0 to 100), sorted, never overlapping. A preempted task appears as several pieces. Names: safety, motion, comms, mapping, perception, battery. Telemetry also gains `wheel_a` (wheel current, amps).
- **Heads-up for others:** Yusuf's timeline strip builds against this. It's on main now.
- **Next:** robots follow dispatched zones and no-go areas.

### 2026-11-07 · rayan/replan · PR #6 Lost link polish and visible replanning
- **Did:** `link_lost` / `link_restored` fire once per outage (`link_restored` carries `dark_s`). After reconnecting, a robot holds until its outbox drains (at most 10 s). The path check catches rubble near waypoints. New REPLANNING state: stop 0.6 s, replan, resume. No route for 10 s raises TRAPPED plus a priority-1 fault bundle.
- **Contract changes:** new state `REPLANNING`, new fault `TRAPPED`, `replan` events carry `reason`, `link_restored.dark_s`.
- **Heads-up for others:** the R key (drop rubble) now shows a visible replan.
- **Next:** timeline contract.

### 2026-11-07 · rayan/relays · PR #5 Relays, A* return home, shielded survivor cage
- **Did:** robots auto-drop relays when the best upstream link is between -81 and -76 dBm, at least 4 m from other relays, never in no-go areas. 2 per robot (about 4 in a 3-robot run). The return-home cost uses A* path length. Frontier clusters go down to 2 cells.
- **Contract changes:** `relays_left` in telemetry is real. `relay_dropped` event `{kind, id:"RL1", pos:[x,y], owner}`. **Floorplan:** S1 moved to (36, 27) inside metal room E2 "Steel Storage Cage", door at (38.8, 21).
- **Heads-up for others:** two of Aziz's tests moved off the old S1 spot (approved). Anything with S1 coordinates hardcoded must update.
- **Next:** replanning.

### 2026-11-07 · rayan/multi-robot · PR #3 Share frontier targets through telemetry
- **Did:** telemetry carries the robot's target. Robots avoid frontiers within 4 m of a higher-priority robot's claim (R1 > R2 > R3). Deploy is staggered 1.5 s.
- **Contract changes:** telemetry `target` field.
- **Heads-up for others:** TEMPORARY shim in `sim.py` copies telemetry into peer inboxes. Aziz replaces it with DTN-delivered peer bundles.
- **Next:** relays.

### 2026-11-07 · main · Starter + PLAN.md
- **Did:** sim server, robot exploration, 3D split view starter, `docs/PLAN.md` (idea, roles, setup, git workflow), CLAUDE.md.
- **Contract changes:** initial message shapes in `docs/PLAN.md`.
- **Heads-up for others:** none
- **Next:** multi-robot.
