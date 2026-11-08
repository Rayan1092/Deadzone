# Deadzone demo runbook

The 3-minute live demo, step by step. Seed, plan and timings are fixed, so the story happens on cue every time. Between cues the robots act on their own.

## The fixed setup

| Setting | Value |
|---|---|
| Seed | `7` |
| Robots | `3` (R1 Scout 1, R2 Scout 2, R3 Scout 3) |
| Speed | `2x` (all wall times below are at 2x) |
| Detector | trained model (top bar must say AI model, see the pre-flight checks) |
| Plan | **P-1** preloaded from the laptop; judges fix it on the phone and dispatch it **before** Space |

Zones in the demo plan. R2 is the robot that goes dark on purpose:

| Robot | Zone | Area | comms |
|---|---|---|---|
| R1 | ZW | west offices, x 0–20, y 17–30 | relay |
| **R2** | **ZNE** | **north-east incl. the steel cage, x 32–40, y 17–30** | **lost_link_ok** |
| R3 | ZB | break room, x 20–32, y 17–30 | relay |

P-1 starts with ZNE set to `relay`. The safety checker rejects it, and that rejection is the phone beat. The phone's one-tap fix "Allow ZNE to go dark" switches it to `lost_link_ok` (same plan id), and then it passes. All timings below were measured with exactly that plan.

## Pre-flight checks (T-30 min)

1. `git checkout main; git pull`.
2. Install dependencies, including CPU PyTorch. **Without torch the detector is not used.**
   ```powershell
   cd server
   py -m pip install -r requirements.txt
   py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
   py -m pip install pillow
   cd ..\web; npm install; npm run build; cd ..
   ```
3. Start the server **paused**. Leave `DZ_AUTOSTART` unset.
   ```powershell
   cd server
   $env:DZ_ROBOTS=3; $env:DZ_SEED=7; $env:DZ_SPEED=2
   py -m uvicorn deadzone.app:app --host 0.0.0.0 --port 8000
   ```
4. The server log must say `survivor detector: trained model, threshold 0.60`. If it says `sim sensor fallback (...)`, fix torch before going on stage. The top-bar chip (coming from Yusuf) will show the same thing.
5. Open `http://localhost:8000` on the big screen. Phones join with **Q** (QR) on the same Wi-Fi, or on the phone hotspot.
6. Preload **P-1** so it appears on every phone. Use the first two commands in "Plan fallback" below: send `$p1` to `/api/plan` only, don't dispatch.
7. Record a backup run once (after the last code change): open `http://localhost:8000/?record`, run the whole demo, press **S** to save the gzipped recording, and keep the file next to the backup video.
8. Charger in, notifications off, browser zoom set. Second tab: `ml/results/confusion_matrix.png`. Third tab: the GitHub repo.

## Director keys (big screen)

| Key | Action | Status |
|---|---|---|
| Space | start / pause | live |
| Backspace | reset to seed 7, paused | live |
| `+` / `-` | sim speed ×2 / ÷2 | live |
| 1–3 / 0 | follow robot 1–3 (or click its card) / back to overview. Command follows the robot's last *reported* pose | live |
| R | drop rubble 1.5 m ahead of the **followed** robot (R1 if none) | live |
| F | wheel overcurrent on the **followed** robot (R1 if none) | live |
| G | briefing panel, "Local summary · Command data only" | live |
| Q / Esc | QR join overlay on / off (Esc also closes the briefing) | live |
| T | faint truth survivors and decoys on Reality only | live |
| V | robot's-eye camera of the followed robot (with a Thermal toggle) | live |
| P | performance mode (no shadows, fewer lidar rays); press it if the big screen stutters | live |
| S | save the recording (only when the page was opened with `?record`) | live |
| O | perception overload on the **followed** robot: deadline misses for 3 s | live |
| U | resume the followed robot from SAFE_STOP (also the "Send resume command" button on its card). Travels over the radio, so it needs a route to CMD | live |

REST fallbacks if a key misbehaves: F `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/fault -ContentType application/json -Body '{"type":"overcurrent","robot":"R3"}'`, G `Invoke-RestMethod http://127.0.0.1:8000/api/report`.

## Beat sheet

Space is pressed at **0:40**. Times after it come from a headless seed-7 run with P-2. They are exact until the first director key is pressed. Re-check them at every rehearsal and update this table if they drift.

| Clock | After Space (sim s) | On screen | Who | What to say |
|---|---|---|---|---|
| 0:00 | paused | Building, robots at the door, empty Command side | Rayan | "In a collapse the radio dies first. Today's rescue robots stop when the signal stops. Ours keep searching." |
| 0:15 | paused | Q: judges scan the QR and see **P-1** on the phone. A judge taps **Run safety check**: the card rejects it, *"Zone ZNE predicts a dead zone; use a relay chain or lost_link_ok"*, and ZNE pulses red | Yusuf | "The safety checker only uses what the command post knows. It predicts the steel cage is a radio dead zone, so it blocks the plan until we say that zone may go dark." |
| 0:30 | paused | Judge taps **Allow ZNE to go dark**, runs the check again (pass), taps **Dispatch** | Yusuf | "Robot 2 is now allowed to lose signal in the north-east for up to 60 seconds." |
| 0:40 | 0 | **Space.** Robots enter. Each takes its zone (`plan_applied`) | Aziz | "Every message, even this plan, travels over the simulated radio." |
| 0:47 | +0:07 (14.4) | R1 finds **S3** in Office A while linked. It appears on both sides at once, with its **rescue route** from the entrance (14.2 m) | Aziz | "With signal, the report is instant, and the robot sends responders the safest route in." |
| 1:08 | +0:28 (56.7) | R1's camera sees the **radiator** (D1). The detector rejects it | Rayan | "That's a radiator. Our model, trained on real FLIR thermal images, says it's not a person, so no false alarm." |
| 1:09 | +0:28.5 (57.1) | R3 drops **relay RL1** | Aziz | "Robots drop relays just before the link breaks, like the DARPA SubT teams did." |
| 1:38 | +0:58 | Press **2**: follow R2 | Rayan | |
| 1:40 | +0:59.5 (119.1) | R2 enters the **steel cage** and loses link. Command shows a **ghost R2** (its camera stays at the last reported pose) | Rayan | "Steel kills radio. Command post goes blind, but Robot 2 keeps searching." |
| 1:44 | +1:04.5 (129.0) | R2 finds **S1** in the dark, confidence 1.0, and drops **beacon relay RL2** next to them. **Reality side only** | Rayan | Point at the ghost: "Command doesn't know yet. The report and the rescue route wait in the robot's outbox. It leaves a beacon so responders get radio at the survivor." |
| 1:52 | +1:11.5 (143.1) | R2 reconnects. Map, **S1 and its 49.7 m rescue route burst onto Command**, 14 s after detection | Rayan | "Store and forward: nothing lost, just late. Responders now have the way in." |
| 1:55 | +1:15 (150) | Press **1** then **R**: rubble falls ahead of R1, which goes **REPLANNING** and drives around | Rayan | "Rubble falls. The robot sees it, stops and replans on its own." |
| 2:02 | +1:22.5 (165) | Press **3** then **F**: R3 gets an **OVERCURRENT** fault, backs up 0.5 m and replans | Rayan | "A wheel jams. Fault protection stops it, backs off and tries another way." |
| 2:07 | +1:27.5 (175) | Press **1** then **O**: the scheduler strip shows **perception missing deadlines** (red) for 3 s, while **safety still runs at 0 and 50 ms** | Rayan | "Rate monotonic scheduling: when the AI overloads the CPU, perception misses deadlines, but the safety task always runs on time." |
| 2:20 | | Press **0**, then **G**: briefing panel appears | Yusuf | "This briefing only uses what reached the antenna." |
| 2:43 | +2:03 (245.8) | **S2** found by R2 while linked, with its route (bonus, only if R/F/O landed on time) | | |
| 2:45 | | | Rayan | "The robots are autonomous, and AI detects survivors. Collapsed buildings, mines, wildfires, tunnels." |

Rescue routes draw on Reality as soon as a robot computes them (yellow dashed line, beacon ring). On Command and phones they appear only once Aziz adds delivered `command.routes`; Yusuf's drawing is ready. Until then, point at the Reality route during the survivor burst.

R, F, O and U hit the **followed** robot, so check the follow key first.

**Press R, F and O on time** (1:55, 2:02, 2:07). They change what the robots do next, and late or extra presses push the S2 bonus past the 2:45 close. If they slip, skip S2 and close on time.

PowerShell fallbacks use `127.0.0.1`, not `localhost`: on Windows `localhost` tries IPv6 first and hangs about 2 s per call.

Don't press **R** while the followed robot stands in a doorway: rubble in a doorway seals it in (TRAPPED after 10 s). At 1:55 (sim 150) R1 is near the break-room door and still gets around. That worked in the dry run, but watch it.

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
| Log says `sim sensor fallback` | Stop. Install CPU torch (pre-flight step 2) and restart the server. Without it there's no AI story (the sensor then emits no decoys, so no false survivors, but no rejection cards either). |
| Server crashed | Restart it (pre-flight step 3). The browser reconnects by itself. Then reset and dispatch P-2 again. |
| Phones can't reach the laptop | Move every device to the phone hotspot, or use `cloudflared`. The demo also runs without phones (plan fallback above). |
| Nothing works | Replay the recording: open `/?replay` and drop the file in (Space pauses, Backspace restarts). It needs no sim, but the detection card images only load if the server is running. Last resort: the backup video. |

## Judge questions (one answer each)

- **"Is the AI driving the robot?"** No. Exploration, A\*, relay drops, the scheduler and fault protection are our own algorithms. The trained model only decides whether a hot spot is a person: 96% accuracy on held-out FLIR images (confusion matrix in tab 2).
- **"How do you know the Command view isn't cheating?"** It only changes when a bundle physically arrives at the command post node. A test fails if it ever knows a survivor or map cell before that bundle was delivered. Robot code only sees the world through its sensors (`io`).
- **"How would this run on real robots?"** The robot module only talks to `io` (lidar, thermal, odometry, drive, radio). Swap the sim behind `io` for ROS 2 drivers and the same code runs.
