# Deadzone demo runbook

The 4-minute live demo, step by step. Seed, plan and timings are fixed, so the story happens on cue every time. Between cues the robots act on their own.

## The fixed setup

| Setting | Value |
|---|---|
| Seed | `7` |
| Robots | `3` (R1 Scout 1, R2 Scout 2, R3 Scout 3) |
| Speed | `1.5x` (all wall times below are at 1.5x: clock = 0:40 + sim seconds / 1.5) |
| Furniture | **`DZ_OBSTACLES=1`**: solid shelves and desks (#119), 1 dB radio loss per piece (#128). Every beat below was measured with it on |
| Detector | trained model (top bar must say AI model, see the pre-flight checks) |
| Plan | **P-1** preloaded from the laptop; judges fix it on the phone and dispatch it **before** Space |

Zones in the demo plan. R2 is the robot that goes dark on purpose:

| Robot | Zone | Area | comms |
|---|---|---|---|
| R1 | ZW | west offices, x 0–20, y 17–30 | relay |
| **R2** | **ZNE** | **north-east incl. the steel cage, x 32–40, y 17–30** | **lost_link_ok** |
| R3 | ZB | break room, x 20–32, y 17–30 | relay |

P-1 starts with ZNE set to `relay`. The safety checker rejects it, and that rejection is the phone beat. The phone's one-tap fix "Allow signal loss here and check again" switches it to `lost_link_ok` (same plan id), and then it passes. All timings below were measured with exactly that plan.

## Pre-flight checks (T-30 min)

1. From the repo root, **run `scripts/preflight.ps1`** (PowerShell), or
   `./scripts/preflight.sh` (macOS/Linux/Git Bash), before starting the demo servers.
   Fix any `FAIL` using the setup below, then rerun until every line says `PASS`.
   The check activates `.venv`, loads the model on CPU, checks the two local API
   keys without printing them, verifies the effective flags against the active
   PowerShell assignments below, checks tools/ports, then runs its own paused
   server for 10 seconds and verifies `hello.detector == "model"` and HTTP access
   through the laptop's LAN IP. A LAN failure prints the Windows Firewall command
   to allow inbound TCP 8000; run it as administrator only if needed. It stops only
   that temporary server. Export the flag blocks below before rerunning; shell
   variables override `server/.env`. Extra nonempty `DZ_` variables fail even if
   their value is `0`; remove them for this exact demo profile. Commented-out
   flags are not allowed. Windows reports `py --version`; Unix reports `py` if
   available, otherwise `python3`. `.venv` Python is used for actual checks.
2. `git checkout main; git pull`.
3. Install dependencies in the activated `.venv`, including CPU PyTorch.
   **Without torch the detector is not used.** Use `python` below to select the
   activated virtual environment explicitly.
   ```powershell
   cd server
   python -m pip install -r requirements.txt
   python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
   python -m pip install pillow
   cd ..\web; npm install; npm run build; cd ..
   ```
4. Start the server **paused**. Leave `DZ_AUTOSTART` unset. The default launcher
   binds `0.0.0.0:8000` so phones can connect.
   ```powershell
   cd server
   $env:DZ_ROBOTS=3; $env:DZ_SEED=7; $env:DZ_SPEED=1.5; $env:DZ_OBSTACLES=1; $env:DZ_ROBOT_COLLISIONS=1; $env:DZ_SMART_RUBBLE=1; $env:DZ_COVERAGE_GRID=1
   python -m deadzone
   ```
   `DZ_OBSTACLES=1` and `DZ_ROBOT_COLLISIONS=1` are **required** for the main run (the demo guard runs with both on). Without `DZ_OBSTACLES` the beat sheet below is wrong: S1 is found at 129.0 s instead of 102.7. Without `DZ_ROBOT_COLLISIONS` the robots can drive through each other and S2 lands at 3:06 (sim 219.4) instead of 3:04.8. `DZ_SMART_RUBBLE=1` makes the R key a no-trap drop for Q&A. `DZ_COVERAGE_GRID=1` lets **W** show the command post's predicted radio coverage (Command view only; no robot behaviour changes, the guard runs with it on). The secondary collapse at 2:28 (sim 162.5) is a scenario event in `collapse_01.json` and runs with no flag; leave `DZ_SCENARIO_EVENTS` unset.
5. The server log must say `survivor detector: trained model, threshold 0.60`. If it says `sim sensor fallback (...)`, fix torch before going on stage. The top-bar detector chip shows the same thing.
   Optional features are off unless their flag is set before starting the server (only turn on what passed a dry run):
   ```powershell
   $env:DZ_AFTERSHOCK=1   # key A
   $env:DZ_AI_LAB=1       # key L (serves ml/results and docs/assets read-only)
   $env:DZ_GEMINI=1       # G briefing and phone Ask through Gemini (GEMINI_API_KEY in server/.env); passed the testing-laptop dry run
   # $env:DZ_VOICE=1      # voice commands: robot side and Aziz's /api/voice are on main; the push-to-talk UI isn't yet, and leases block B/U (below)
   $env:DZ_SENSOR_VIEW=1  # safe: Aziz's Reality-only robot camera frames (#82) for Yusuf's renderer; the demo guard stays green with it on
   # DZ_EXPLORATION_V2    # must stay unset (0) for the main run: Aziz's opt-in exploration policy (#77) moves every beat below
   # DZ_OBSTACLES=1       # already set in step 4: required, every beat below depends on it (rayan.md 20:30)
   # DZ_SMART_RUBBLE=1    # already set in step 4: the smart, no-trap R key for Q&A (rayan.md 22:10)
   # DZ_SCENARIO_EVENTS   # must stay unset: 0 switches off the building's scripted collapse at 2:28 (rayan.md 23:20)
   # DZ_ZONE_PRIORITY     # must stay unset for the main run: robots head straight for their zones and the story runs earlier (R2 dark 48.7 s, S1 found 59.5, S2 193.2; rayan.md 00:55)
   ```
   **Don't set `DZ_VOICE`, `DZ_CONTROL_LEASES` or `DZ_EXPLORATION_V2` for the main run.** With control leases on, the top bar shows the **Operator lock**: **B** and **U** stay locked (with a hint) until you press **Unlock**, which takes every robot for this console ("Console has control"; field units then see the robots locked; R, F, O and A are not affected). **Lock** releases the robots so field units (phones) can take them (Q&A). Unlock fails, naming the holder, while a field unit holds a robot. Leases off: no lock, B and U as before. With `DZ_EXPLORATION_V2=1` the robots explore differently and every beat in the beat sheet moves (S3 found at 23.8 s instead of 14.4, S2 found at 106 s instead of 246). `DZ_SENSOR_VIEW=1` is safe: it only adds camera frames to the Reality pane.
6. **Before the phone test, Rayan starts the tunnel manually** in a second
   PowerShell terminal from the repo root:
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/tunnel.ps1`
   (the execution policy applies only to that process). Install the tool
   first if missing: `winget install Cloudflare.cloudflared`, then open a fresh
   terminal and confirm `cloudflared --version`. The script runs
   `cloudflared tunnel --url http://localhost:8000` and prints **HTTPS URL** and
   **Phone URL** (`/phone`). Leave that terminal open; **Ctrl+C** stops the tunnel.
   It uses the already-running server and does not start/reset it. The URL changes
   on each run. No tunnel is started by preflight or installation.
7. **Test the phone:** open the printed HTTPS URL with `/?nointro` on the big
   screen and the printed **Phone URL** on the phone (or use **Q** for its QR).
   Using the HTTPS origin on both keeps API/WebSocket/QR traffic on the same
   origin and permits phone microphones. For a local Wi-Fi-only check without a
   tunnel, use `http://localhost:8000/?nointro` on the laptop and its Q/QR link on
   the same Wi-Fi/hotspot. **Phones must be on the same Wi-Fi, or use the tunnel.**
   A LAN-IP preflight pass cannot detect guest-network/client isolation; use a
   hotspot or the tunnel if another device still cannot connect. `?nointro` keeps the first-visit explainer off the scene;
   the **H** help popup can still open it.
8. Preload **P-1** so it appears on every phone. Use the first two commands in "Plan fallback" below: send `$p1` to `/api/plan` only, don't dispatch.
9. Record a backup run once (after the last code change): open `http://localhost:8000/?record`, run the whole demo, then click **Save recording** next to the REC status to save the gzipped recording, and keep the file on the demo laptop.
10. Charger in, notifications off, browser zoom set. Second tab: `ml/results/confusion_matrix.png`. Third tab: the GitHub repo.

## Director keys (big screen)

| Key | Action | Status |
|---|---|---|
| Space | start / pause. The page opens on the street shot outside the building; the first Space dives into the building and starts the run | live |
| Backspace | reset to seed 7, paused | live |
| `+` / `-` | sim speed ×2 / ÷2 | live |
| 1–3 / 0 | follow robot 1–3 (or click its card) / back to overview. Command follows the robot's last *reported* pose | live |
| R | drop rubble on the **followed** robot's planned path 3–4 m ahead (R1 if none), at the nearest spot that walls nobody in (`DZ_SMART_RUBBLE=1`; without it, 1.5 m ahead). **Q&A only, never during the beat sheet:** the reroute beat is the building's scripted collapse at 2:28 | live |
| F | wheel overcurrent on the **followed** robot (R1 if none) | live |
| G | **Gemini briefing** from Command data only (`source: "gemini"`, about **6 s** to generate, then read aloud; Voice on/off toggle). Press it ~6 s before you want to talk over it | live with `DZ_GEMINI=1` (dry run passed) |
| Q / Esc | QR join overlay on / off (Esc also closes the briefing) | live |
| H | keyboard help popup, with a link to reopen the intro | live |
| V | robot's-eye camera of the followed robot (with a Thermal toggle). It also opens by itself on a detection, with the AI box and the robot's steps | live |
| P | performance mode (no shadows, fewer lidar rays). **Set it before the demo, never during:** toggling recompiles every material and freezes the screen for several seconds (rayan-ml's profile) | set before |
| Save recording | download the mission recording | button beside REC, shown when opened with `?record` |
| O | perception overload on the **followed** robot: deadline misses for 3 s | live |
| U | resume the followed robot from SAFE_STOP (also the "Send resume command" button on its card). Travels over the radio, so it needs a route to CMD | live |
| B | baseline toggle: every robot switches to "without Deadzone" (stops when its link drops, no relays) and back. Red "Baseline" chip while on. Q&A only, never during the beat sheet | live |
| A | aftershock: part of the building collapses where the first powered relay is, that relay is destroyed, the network reroutes and robots replan (and reroute rescue routes they see blocked) | needs `DZ_AFTERSHOCK=1`; Q&A only |
| L | Model Lab overlay: training examples, training curve, confusion matrix, held-out metrics, and the crop a robot just classified with its Grad-CAM | needs `DZ_AI_LAB=1` |
| J | Model test: a random held-out thermal sample; guess person or not, then see the model's recorded answer. Q&A only | needs the held-out export |
| M | one view (Reality with the Command post inset, bottom right) / split view | live |
| C | one view: swap the Command post inset and the main view; split view: frame the command post | live |
| D | auto-director camera (cuts to dark robots, finds, the reveal, aftershocks). Any drag, wheel or 0–9 hands the camera back for 20 s | live, off by default; good for a hands-free video |

REST fallbacks if a key misbehaves: F `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/fault -ContentType application/json -Body '{"type":"overcurrent","robot":"R3"}'`, G `Invoke-RestMethod http://127.0.0.1:8000/api/report` (check `source` says `gemini`).

## Beat sheet

Space is pressed at **0:40**. The mission clock is in the top bar. Times after it come from the demo guard's headless seed-7 run (`server/tests/test_demo_guard.py`: P-1 rejected, fixed, dispatched; `DZ_OBSTACLES=1`, `DZ_ROBOT_COLLISIONS=1`, `DZ_SMART_RUBBLE=1`; the scenario event in `collapse_01.json`, a collapse on S1's route at 162.5; F / O at sim 177.5 / 187.5). Clock = 0:40 + sim seconds / 1.5. They are exact until the first director key is pressed. Re-check them at every rehearsal and update this table and the guard together if they drift.

| Clock | After Space (sim s) | On screen | Who | What to say |
|---|---|---|---|---|
| 0:00 | paused | Building, robots at the door, empty Command side | Rayan | "In a collapse the radio dies first. Today's rescue robots stop when the signal stops. Ours keep searching." |
| 0:15 | paused | Q: judges scan the QR and see the preloaded search plan on the phone. A judge taps **Run safety check**: the card rejects it, *"Search area 2 may lose radio contact. Add a relay route or allow signal loss for a limited time."*, and the north-east search area pulses red | Yusuf | "The safety checker only uses what the command post knows. It predicts the steel cage is a radio dead zone, so it blocks the plan until we say that zone may go dark." |
| 0:30 | paused | Judge taps **Allow signal loss here and check again**, runs the check again (pass), taps **Send plan** | Yusuf | "Robot 2 is now allowed to lose signal in the north-east for up to 60 seconds." |
| 0:40 | 0 | **Space.** Robots enter. Each takes its zone (`plan_applied`) | Aziz | "Every message, even this plan, travels over the simulated radio." |
| 0:49 | +0:09.4 (14.1) | R1 finds **S3** in Office A while linked. It appears on both sides at once, with its **rescue route** from the entrance (14.2 m) | Aziz | "With signal, the report is instant, and the robot sends responders the safest route in." |
| 1:19 | +0:38.6 (57.9) | R1's camera sees the **radiator** (D1). The detector rejects it | Rayan | "That's a radiator. Our model, trained on real FLIR thermal images, says it's not a person, so no false alarm." |
| 1:25 | +0:45 (67.5) | R3 drops **relay RL1** | Aziz | "Robots drop relays just before the link breaks, like the DARPA SubT teams did." |
| 1:38 | +0:58 (87) | Press **2**: follow R2 | Rayan | |
| 1:41 | +1:00.9 (91.3) | R2 enters the **steel cage** and loses link. Command shows a **ghost R2** (its camera stays at the last reported pose) | Rayan | "Steel kills radio. Command post goes blind, but Robot 2 keeps searching." |
| 1:48 | +1:08.5 (102.7) | R2 finds **S1** in the dark, confidence 1.0, and drops a **beacon relay** next to them. **Reality side only** | Rayan | Point at the ghost: "Command doesn't know yet. The report and the rescue route wait in the robot's outbox. It leaves a beacon so responders get radio at the survivor." |
| 1:59 | +1:19 (118.5) | R2 reconnects. Map, **S1 and its 49.7 m rescue route burst onto Command**, 16 s after detection | Rayan | "Store and forward: nothing lost, just late. Responders now have the way in." |
| 2:02 | | Press **0**, then **G**: the Gemini briefing appears after about 6 s and is read aloud | Yusuf | While it generates: "Gemini writes this briefing only from what reached the antenna, never from the robots' own view." |
| 2:26 | +1:46 (159) | Press **1**: follow R1, now in the corridor below the break room, on S1's rescue route | Rayan | |
| 2:28 | +1:48.3 (162.5) | **Nothing to press.** The building's scripted **secondary collapse** (scenario event in `collapse_01.json`) drops rubble ahead of R1 **on S1's rescue route** (event `rubble_fall`, cause `collapse`). R1 sees it and goes **REPLANNING** a second later (sim 164.0) and drives around; R2, 3 m away, sees the rubble and reroutes S1 at once (sim 162.8): Command's S1 route **redraws around it, 52.1 m** (replaced, not doubled) | Rayan | Narrate it: "A secondary collapse, right on the way in. Robot 1 sees it, stops and replans. Robot 2 saw it too and just sent responders a new route around it." |
| 2:38 | +1:58.3 (177.5) | Press **3** then **F**: R3 gets an **OVERCURRENT** fault, backs up 0.5 m and replans | Rayan | "A wheel jams. Fault protection stops it, backs off and tries another way." |
| 2:45 | +2:05 (187.5) | Press **1** then **O**: the scheduler strip shows **perception missing deadlines** (red) for 3 s, while **safety still runs at 0 and 50 ms** | Rayan | "Rate monotonic scheduling: when the AI overloads the CPU, perception misses deadlines, but the safety task always runs on time." |
| 3:04.8 | +2:24.8 (217.2) | Press **0**. R2 finds **S2** while linked, with its 39.1 m route: all three survivors are on Command | Rayan | "Third survivor, this time with signal, so it's on Command instantly. Three for three." |
| 3:10 | | | Rayan | "The robots are autonomous, and AI detects survivors. Collapsed buildings, mines, wildfires, tunnels." |

That ends at about 3:25, with 35 s of slack before 4:00.

Rescue routes draw on Reality as soon as a robot computes them (yellow dashed line, beacon ring), and on Command and phones only when the route bundle is delivered. A rerouted route replaces the old one with a short flash (2:28).

R, F, O and U hit the **followed** robot, so check the follow key first.

**At 2:28 a secondary collapse blocks R1; narrate it.** The sim drops it by itself at sim 162.5 every run (a scenario event in `collapse_01.json`), so there is no R press in the script. **Press F and O on time** (2:38, 2:45): they change what the robots do next. **Don't press R during the beat sheet**: any rubble before 2:28 changes where the robots are when the collapse falls. R is for Q&A: it now drops on the followed robot's path ahead at a spot that never traps anyone (51 presses between sim 150 and 175 measured: 0 trapped, R1 replans every time).

PowerShell fallbacks use `127.0.0.1`, not `localhost`: on Windows `localhost` tries IPv6 first and hangs about 2 s per call.

With `DZ_SMART_RUBBLE=1`, **R** never seals a doorway: it skips any spot whose rubble would cut a robot off from space it could reach (flood fill on the building), and only falls back to the old 1.5 m-ahead spot when the robot has no planned path 2–6 m long. Without the flag, don't press R while the followed robot stands in a doorway (TRAPPED after 10 s).

## Plan fallback: send it without the phone

Used to preload P-1 (first two commands only). If the planner phone fails, run the rest too: it sends the fixed version as P-2 and dispatches it (same zones as the phone fix). PowerShell:

```powershell
$p1 = '{"plan_id":"P-1","author":"judge-phone","lost_link_budget_s":60,"no_go":[],"zones":[
 {"id":"ZW","robot":"R1","priority":1,"comms":"relay","poly":[[0,17],[20,17],[20,30],[0,30]]},
 {"id":"ZNE","robot":"R2","priority":1,"comms":"relay","poly":[[32,17],[40,17],[40,30],[32,30]]},
 {"id":"ZB","robot":"R3","priority":1,"comms":"relay","poly":[[20,17],[32,17],[32,30],[20,30]]}]}'
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/plan?check=false' -ContentType application/json -Body $p1
# saved quietly; the judge's Run safety check produces the first ZNE rejection

$p2 = $p1.Replace('"P-1"', '"P-2"').Replace('"ZNE","robot":"R2","priority":1,"comms":"relay"', '"ZNE","robot":"R2","priority":1,"comms":"lost_link_ok"')
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/plan -ContentType application/json -Body $p2
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/dispatch -ContentType application/json -Body '{"plan_id":"P-2"}'
```

The safety check needs the command post to have heard each robot once. Startup and reset run one real tick and then pause (T+0.1 s), so checks and dispatch work before Space.

## Recovery

| Problem | What to do |
|---|---|
| Robot in **SAFE_STOP** (F pressed 3 times on it within 60 s) | Follow it and press **U** (or the "Send resume command" button on its card). It arrives over the radio, so the robot needs a route to CMD. If there's no route, say "the watchdog stopped it, a human has to clear it" and carry on. |
| Robot **TRAPPED** (rubble sealed a doorway) | It keeps retrying. It can't be cleared live. Carry on, or reset (below). |
| Story off script (S1 found while linked, wrong plan sent, keys pressed too early) | **Reset:** Backspace (seed 7, paused; the shared plan clears). Preload P-1 again and redo the phone fix, or send and dispatch P-2 with the fallback, then Space. Speed stays where it was; check it reads 2x. |
| G shows "Local summary · Gemini unavailable" (or nothing after ~10 s) | Gemini timed out or the key/network failed; the local summary is still built only from Command data. Say "the briefing falls back to a local summary when the model isn't reachable" and carry on. Check `server/.env` and the Wi-Fi after the demo |
| Log says `sim sensor fallback` | Stop. Install CPU torch (pre-flight step 2) and restart the server. Without it there's no AI story (the sensor then emits no decoys, so no false survivors, but no rejection cards either). |
| Server crashed | Restart it (pre-flight step 3). The browser reconnects by itself. Then reset and dispatch P-2 again. |
| Phones can't reach the laptop | Move every device to the phone hotspot, or use `cloudflared`. The demo also runs without phones (plan fallback above). |
| Nothing works | Mission replay: open `/?replay` and drop the mission recording in (Space pauses, Backspace restarts). It needs no sim, but the detection card images only load if the server is running. |

## Q&A extras (after the close, only what passed a dry run)

| Ask | Show | How |
|---|---|---|
| "Does it actually help?" | **B**: robots stop where the signal dies and drop no relays; press **B** again to switch back | Then the benchmark slide (`docs/assets/benchmark.png`): 60/60 vs 39/60 survivors reported and 90% vs 70% mapped, **in simulation** (radio numbers are chosen, not measured; say so) |
| "What if the building shifts again?" | **A** (with `DZ_AFTERSHOCK=1`): collapse, relay crushed, links reroute, robots replan and resend rescue routes they see blocked | Best after the reveal; it changes everything after it |
| "How was the AI trained?" | **L** (with `DZ_AI_LAB=1`): real FLIR examples, curve, confusion matrix, Grad-CAM "where the AI looked" | The training curve shows once the logged retrain has run on the testing laptop |
| "Can you do a different building?" | **N** (Yusuf): reset into another registered building; **Shift+N** comes back to the main one. Pick-a-seed: `py data/floorplans/generate.py --seed <judge's number>` writes `data/floorplans/generated/gen_<number>.json` (validated: everything reachable, a steel dead zone, 3 survivors, 3 decoys, a disaster script), then reset into `generated/gen_<number>` (`{action:"reset", value:{floorplan:"generated/gen_<number>", timeline:true}}`) | Timelines need `DZ_SCENARIO_TIMELINE=1` (and `DZ_AFTERSHOCK=1`, every script has one aftershock). Robots start without a plan; to give them one, `POST /api/plan` with `data/plans/generated/gen_<number>.plan.json` and dispatch `P-gen_<number>`, until Aziz preloads it |
| "How big can it go?" | **`showcase_01`**: 80 x 60 m, 36 rooms, two steel dead zones (storage cage and vault), 4 survivors, 4 decoys, a **three-area earthquake** at 184 s (warehouse), 194 s (cross hall) and 246 s (far hall), 2 relays crushed. Reset into `showcase_01` with `timeline: true` | **Show the earthquake and the pick-a-seed, not a dead-zone find:** with 3 robots the dead-zone survivors take over 5 minutes of sim time. What does land early: the hall survivor at ~44 s with the "AI unsure 58%, moving closer" card, then "Person 100%". Plan: `data/plans/showcase_01.plan.json` as above (`P-showcase_01`). Big maps run slower (about 6x real time headless on the dev laptop) |
| "Same building, new survivors?" | **N** prefers the five validated variants of the demo building (`variants/collapse_01_v1..v5`): same walls, S1 still deep in the steel cage, the other people and decoys moved; the NEW SCENARIO banner names it | S3 and D3 in every variant use the "unsure from a distance" crops, so the look-closer card shows up here too. Never during the main run |
| "Are there more survivors?" | No: all three are on Command by 3:04.8 (S2 at sim 217.2). After that the robots finish mapping and return home on battery; nothing else is scripted | Only if R / F / O landed on time; otherwise S2 lands between sim 216 and 233 |
| "Can I talk to a robot?" | Voice command | Not yet: robot side and Aziz's `/api/voice` are on main; Yusuf's push-to-talk UI is not |

## Judge questions (one answer each)

- **"Is the AI driving the robot?"** No. Exploration, A\*, relay drops, the scheduler and fault protection are our own algorithms. The trained model only decides whether a hot spot is a person: 96% accuracy on held-out FLIR images (confusion matrix in tab 2).
- **"How do you know the Command view isn't cheating?"** It only changes when a bundle physically arrives at the command post node. A test fails if it ever knows a survivor or map cell before that bundle was delivered. Robot code only sees the world through its sensors (`io`).
- **"How would this run on real robots?"** The robot module only talks to `io` (lidar, thermal, odometry, drive, radio). Swap the sim behind `io` for ROS 2 drivers and the same code runs.
- **"Did you compare against robots without this?"** Yes, in simulation: same robots, but they stop when the link drops. Over 20 random survivor layouts, Deadzone got 60 of 60 survivors to Command and the baseline 39 of 60. The radio model's numbers are chosen, not measured, so it's evidence the idea works in our model, not a field result.
