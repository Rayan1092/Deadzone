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

## Version 2 plan (7 PM Saturday)

Version 1 works end to end (every demo beat verified on the testing laptop), so the remaining 12 hours go to a version that targets every prize: a real-looking 3D board, a clearer story on one screen, the AI visible in the world, a real Gemini briefing and an over-engineered backend. The phone stays a controller only (plan, relay, ask Gemini). Yusuf owns the 3D design and decides how it looks; the items below are what each person delivers so it all fits together.

### Guardrails (non-negotiable)

- **Demo guard test first.** `DEMO.md` becomes a pytest that runs seed 7 and asserts every beat time within a small tolerance. Any PR that moves a beat fails. Version 1 stays recordable at all times.
- **Every new feature is behind a toggle or key** until it has passed a full dry run on the testing laptop.
- **Record the Version 1 backup video tonight** (`?record`, then S, plus a screen recording) before big visual changes land.
- **Rayan announces the feature freeze.** After it: fixes, recording, Devpost, rehearsal only.

### UX fixes the team agreed on

- **One main 3D view instead of two side-by-side maps.** The big view shows Reality. What Command doesn't know yet is drawn on the same map: a ghost robot at its last reported spot, tied by a dashed line to the real robot; survivors found but not yet reported get a pulsing "Not reported yet" tag; unreported map area is tinted. A small Command inset or a key toggles the pure Command view. When data arrives, the gap closes visibly (the reveal moment).
- **Task timeline collapsed by default.** It shows only for the followed robot, and auto-expands during the overload beat (O) and on deadline misses.
- **Less clutter:** labels only on hover or for the followed robot, the event feed trimmed to the important events, and a clear legend.
- **The AI visible in the world:** survivors and decoys in the 3D scene use the exact thermal crops the detector judges, so the robot's-eye view (thermal mode) shows the same image that the AI card shows. Rendered frames are not fed to the model (that would be a domain gap; the trained model judges real thermal images).

### Visual direction: realistic (8:30 PM update)

The team chose a realistic look over the stylized one. Yusuf owns it. The **simulation stays on the single ground floor** that the demo guard verifies; the multi-story building is visual only, so no robot, radio or test changes are needed.

- **Multi-story shell:** upper floors, a broken facade, a partly collapsed slab and sagging beams around the simulated ground floor. A cutaway or x-ray toggle shows the active floor inside.
- **Materials and light:** free photo-scanned PBR textures (cracked concrete, dusty tiles, rusted metal, rebar) from Poly Haven or ambientCG; a dark interior lit mainly by robot headlights; soft shadows; floating dust; post-processing (ambient occlusion, bloom, light depth of field, film grain).
- **Set dressing:** knocked-over furniture, hanging cables, broken doorframes, dust bursts on rubble falls and aftershocks.
- **Robots:** tracked rescue robots with a mast-mounted spinning lidar, headlights, status LEDs and an antenna. Relays and beacons are rugged boxes with a blinking LED.
- **Survivors:** a realistic person partly under debris that glows white-hot in thermal view, wearing the real crop and heatmap from `ml/` on the AI card.
- **Rules:** clarity first (ghosts, "Not reported yet" tags and routes stay readable over the scene); 60 fps on the RTX 3060 testing laptop with P as the fallback; only CC0 or CC-BY assets, credited in the README.

### AI showcase and scenario generator (8:35 PM update)

**Judges must see the AI recognize a human, and see how it was trained.**

- **Live detection in the robot's-eye view:** a realistic human under debris with a red box and "PERSON 97%, onboard AI" (the real model confidence), followed by the robot's action steps: person detected, marking location, planning rescue route, dropping beacon if there's no signal. Decoys get a box with "NOT A PERSON 0.3%, rejected". The model is a classifier, so the box marks the object it judged; never claim it drew the box itself.
- **AI Lab overlay (key L):** training examples (person and not-a-person thermal crops), the training curve per epoch, the confusion matrix and held-out metrics, and live: the crop the robot just judged with its Grad-CAM heatmap. Rayan exports the assets, Aziz serves them read-only (or Yusuf bundles them), Yusuf builds the overlay.
- **Collapse look:** fallen ceiling slabs at an angle, jagged wall holes, partly missing roof, sagging beams, dangling rebar and cables, broken windows, cracks, debris against walls, overturned furniture, airborne dust. Real photo-scanned textures, a detailed tracked rescue robot model and realistic human survivors (Yusuf).

**Scenario generator (Rayan):** any seed produces a random collapsed building: layout, wall materials, steel dead zones, hazards (gas, fire, flooding, unstable floor), reachable survivors and decoys, plus a disaster timeline built from existing director actions (aftershock, rubble, relay destroyed). New event types such as spreading fire need Aziz (sim) and Yusuf (visuals) and come second. Every generated building is checked for connectivity and reachable survivors. The demo building (seed 7, `collapse_01`) never changes; the generator is for Q&A.

### Voice control with ElevenLabs (8:45 PM update)

Responders can talk to a robot, and it answers in its own ElevenLabs voice. Manual phone control stays as it is. Behind `DZ_VOICE=1` until a dry run passes.

1. **Speech to text:** ElevenLabs speech-to-text, with browser speech recognition as a fallback.
2. **Gemini parses intent only:** the sentence becomes a structured command such as `{robot: "R2", action: "explore_zone", zone: "warehouse"}`. Allowed actions: explore a zone or room, go to a point, return home, hold, resume. Gemini never drives a robot.
3. **Same safety checker** as the phone planner. A refused command gets a spoken reason.
4. **Delivered over the network** as a command bundle. A robot that is dark gets it when it reconnects.
5. **The robot acknowledges** with a priority-1 `command_ack` bundle (accepted with ETA, or refused with reason). The voice reply plays only when that ack reaches Command, so a dark robot answers late (the demo moment).
6. **ElevenLabs text-to-speech** runs on the server with `ELEVENLABS_API_KEY` in `server/.env` (never committed), one voice per robot, with browser speech as a labelled fallback.

Microphones need `https` or `localhost`: push-to-talk works on the big-screen laptop; phones need an https tunnel.

| Part | Owner |
| --- | --- |
| Robot side: handle the voice command actions, send `command_ack` with status, ETA or refusal reason | Rayan |
| `/api/voice` endpoint: speech-to-text, Gemini intent parsing, safety check, command bundle; ack delivery to screens; ElevenLabs text-to-speech proxy; https tunnel for phones | Aziz |
| Push-to-talk on the big screen and the phone, transcript and parsed command card, playing the robot's voice with subtitles | Yusuf |

**HTTPS for phones:** a free Cloudflare tunnel (`cloudflared`) on the demo laptop gives one public `https://` address for the web app, API and WebSockets, so phone microphones work. Vercel and Supabase don't help here: the sim server can't run on Vercel, an https page can't call the laptop over plain http anyway, and the server already holds all state. Aziz sets up and tests the tunnel on the venue Wi-Fi early; big-screen push-to-talk on localhost is the fallback.

**One controller per robot (new, needs building):**

- A phone claims a robot ("Take control of Scout 2"); the server grants an exclusive lease. Nobody else can take it: they see "controlled by \<name>" and a disabled button. No kick-offs, no double control.
- The server rejects voice and manual commands for a robot from anyone who doesn't hold its lease.
- The lease frees itself on disconnect, after about 15 s without a heartbeat, or when the holder taps Release.
- The presenter can free any robot from the big screen (override), so a judge walking away can't strand a robot on stage.
- When all 3 robots are taken, extra phones join as spectators or relays.
- Search planning stays shared (co-planning); only direct robot commands need the lease.

| Part | Owner |
| --- | --- |
| Lease API: claim, release, heartbeat, expiry, presenter override; enforced on `/api/voice` and every direct command; lease state broadcast to phones and screens | Aziz |
| Phone robot picker showing each robot's controller, take and release buttons, locked state; presenter override on the big screen | Yusuf |

### Purpose, trust and visibility pass (midnight update)

Everything we ship from here must pass one test: **a judge can answer "did we find someone, and can rescuers get to them?" from the screen in five seconds, and can verify the AI is real with their own hands.** Rayan owns the story and the judge experience from now on; Aziz and Yusuf own the implementation in their areas.

**Trust: judges verify the AI themselves**

- **Live judge test (key J, Q&A):** shows a random held-out FLIR thermal crop the model has never trained on, hides the label, lets the judge guess person or not, then the model answers with its confidence and the truth is revealed. A running tally ("model 5 of 5, judge 4 of 5"). Rayan ships the held-out pool and labels in `ml/results/judge_pool/` with a manifest; Aziz serves it read-only; Yusuf builds the overlay.
- **Caption every AI image:** "Real thermal camera image, Teledyne FLIR dataset: the same input a thermal camera on a rescue robot produces." On the AI cards, the robot's-eye thermal view and the AI Lab.
- **Show the failures:** the AI Lab keeps the misses visible and the pitch mentions them.
- **Numbers stay real:** confidence is the model's number, never rounded up; the detector chip always shows model vs fallback.

**Purpose: survivors and routes are the headline**

- **Rescue Status strip** at the top of the big screen, judge language only: survivors found, confirmed by onboard AI, reported to command, rescue routes ready, time since collapse. It is the first thing a judge reads.
- **Judge-first labels** everywhere: "No link, keeps searching" not LOST\_LINK\_EXPLORING; "Radio beacon left with survivor" not relay dropped; "Route for rescuers, 52 m, avoids gas" not rescue\_route.
- **Pitch opener:** "72 hours is how long a trapped person usually survives. In a collapsed building the radio dies in the first ten meters. We built robots that keep searching anyway." The inspiration is the DARPA Subterranean Challenge (not NASA).

**Visibility: the backend and ML on screen**

- **Under the hood panel (key I):** live counters from the real system: bundles held in custody and delivered, hops per delivery, bytes repaired by Reed-Solomon, scheduler deadlines met and missed, rescue routes computed, detector calls and rejections. Aziz exposes the counters in `tick.stats`; Yusuf draws the panel; Rayan supplies detector and scheduler counters.

**Proof it is not scripted (judges will ask)**

Robots compute every path live (frontier exploration plus A\* on their own map). Runs look identical only because the demo seed is fixed for reliability. Navigation is classic autonomy, not ML, and the pitch says so: humans decide where to search (phone zones), robots decide how, trained AI decides who is a person.

- **Key N, new scenario:** same building, survivors and decoys shuffled, new seed; the robots find them anyway. Rayan generates validated variants of `collapse_01` (reachable survivors, S1-style dead-zone survivor kept) in `data/floorplans/variants/`; Aziz adds a control to reset into one; Yusuf adds the key and a "new scenario" banner. Q&A only, never the main run.
- **Unsure, moving closer:** when the detector confidence is between about 0.35 and 0.75 the robot approaches and classifies again; the AI card shows "AI unsure 58%, moving closer" then the final verdict. Perception visibly steering the path, with real numbers. Rayan. No effect on the demo beats (all six demo crops score near 0 or near 1).
- Already live: R and A replan around new rubble, phone zones redirect robots, B shows the stop-and-wait baseline, the generator builds any seed.

**Aftershock status:** built and on main (Aziz backend, Yusuf key A, Rayan reroutes), behind `DZ_AFTERSHOCK=1`. Remaining work is rehearsal only: Rayan rehearses A after the 2:45 close on the testing laptop and writes the beat into `DEMO.md` as a Q&A extra.

**Final-stretch decisions (12:20 AM)**

- **Freeze and presentation timing: Rayan decides and announces it**.
- **Earthquake v2:** Aziz adds a strength setting (strong = 2 to 3 collapse areas, a second collapse about 10 s later, 1 to 2 relays destroyed). Yusuf adds 4 to 6 s of shake, falling slabs, dust clouds, flickering lights, a rumble and an "AFTERSHOCK" banner. Robots already reroute. Rayan rehearses A after the close.
- **Map size:** `collapse_01` stays as it is for the main run (beats, radio tuning and the 3-minute script depend on it). The scene gets bigger two ways: Yusuf's exterior shell (collapsed surroundings, an upper floor, the street with the truck) and a big showcase building (about 80 by 60 m) from Rayan's generator for the earthquake and Q&A, loaded through Aziz's floor plan switch.
- **Random maps work by design** (every part reads the floor plan file). To confirm: Aziz adds one reset-into-floorplan control (serves key N variants, the showcase building and generated seeds) and a timeline player for generated disaster scripts; Yusuf makes props generic with a default for unknown rooms; Rayan ships a default search plan with every generated building; the testing laptop runs two generated buildings end to end and reports.
- **Testing laptop is now a builder** for ML and benchmark work in `ml/` and `docs/assets/` (history file `rayan-ml.md`): benchmark refinement (sensitivity sweep over radio settings, random rubble, more seeds, two generated buildings), then the earthquake rehearsal report.
- **Yusuf's cut list tonight:** multi-story interior, voice UI, clinic map. **Handed to Aziz with Yusuf's OK:** the judge test overlay (J) and the Under the hood panel (I), both data panels.
- **Aziz's queue:** short G briefing, B/U presenter fix, earthquake strength, floor plan switch and timeline player, counters in `tick.stats`, judge pool serving, then J and I panels.

Aziz's implemented API/panel contract and acceptance status:
[FINAL-STRETCH-BACKEND.md](FINAL-STRETCH-BACKEND.md). The judge pool and optional
detector/met-deadline instrumentation remain Rayan-owned exports.

**Priority against the 7:30 AM freeze:** live judge test and captions first (cheap, highest trust), Rescue Status strip second, Under the hood third. These rank above multi-story, voice UI and the clinic map. The main run stays exactly as `DEMO.md`; J and I are for after the close and Q&A.

### Owners and priorities

| Priority | Item | Owner | Prize it serves |
| --- | --- | --- | --- |
| 1 | Demo guard test | Rayan | It works |
| 1 | 3D realism pass and the one-view redesign above | Yusuf | Best UI/UX, Best General |
| 1 | Real Gemini briefing (G) over Command data via tool calls, plus a phone "Ask Gemini" box for questions like "where should team 2 go?" Gemini never drives robots | Aziz (server), Yusuf (phone box, spoken briefing on the board) | MLH Best Use of Gemini, Best AI/ML |
| 2 | "Without Deadzone" baseline mode and a 20-seed benchmark (survivors found, time to find, coverage, relays) for a slide and a toggle | Rayan | Best General (usefulness proof) |
| 2 | Grad-CAM "where the AI looked" heatmap per crop, overlaid on the AI card | Rayan (images), Yusuf (overlay) | Best AI/ML |
| 2 | Survivor and decoy crops exported with metadata as 3D textures for the in-world thermal look | Rayan (export), Yusuf (scene) | Best AI/ML, UI/UX |
| 2 | Auto-director camera that cuts to the action (robot going dark, S1 discovery, the reveal) | Yusuf | Pitch, UI/UX |
| 3 | Aftershock event key: part of the building collapses, a relay is destroyed, the network reroutes, robots replan | Aziz (sim, network), Rayan (robot reactions) | X-factor |
| 3 | Real Reed-Solomon on weak links with counts of corrected bytes shown on link lines | Aziz (codec), Yusuf (display) | Most Over Engineered |
| 3 | CRDT offline co-planning on phones (two judges edit offline, plans merge) | Aziz, Yusuf | Most Over Engineered |
| 3 | Judge-picked building: a procedural collapse generator from any seed (Q&A only, never the main demo) | Rayan | Most Over Engineered, X-factor |
| 3 | Sound cues (discovery ping, fault alarm, reconnect chime) | Yusuf | UI/UX |
| 4 | Rescue order list on the phone (route length, risk) | Aziz, Yusuf | Usefulness |
| 4 | Soak test (20 minutes at 10x, no errors, memory flat) | Aziz, Rayan helps if asked | It works |

**Cut order if behind:** priority 4, then 3, then the auto-director camera. Never cut the demo guard, the one-view redesign or Gemini.

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
  "name": "Riverside Block C, post-earthquake",
  "description": "Office block and warehouse after an earthquake: ... three people missing",
  "size": [40, 30],
  "cell": 0.25,
  "wall_height": 3.0,
  "materials": {"concrete": 16, "brick": 10, "drywall": 4, "metal": 22},
  "walls": [{"a": [0, 0], "b": [40, 0], "material": "concrete"}],
  "doors": [{"at": [4.6, 17], "width": 1.2, "axis": "x", "state": "broken"}],
  "rooms": [{"id": "N1", "name": "Office A", "poly": [[0,17],[10,17],[10,30],[0,30]]}],
  "rubble": [{"id": "RB1", "poly": [[21,13],[23,13],[23,15],[21,15]], "height": 1.2}],
  "hazards": [{"id": "H1", "type": "gas", "poly": [[12,0],[24,0],[24,13],[12,13]]}],
  "survivors": [{"id": "S1", "descriptor": "Crouched low in the steel storage cage", "pos": [37, 26], "thermal": "pos_0007.png"}],
  "entry": [1.0, 15.0],
  "command_post": {"pos": [-2.0, 15.0], "tx_dbm": 20}
}
```

User-facing text (the screen shows these, never file ids): `name` and a one-line `description` per building, a short `descriptor` per survivor (ids stay S1, S2 ...) used in captions, and a `label` on every scenario event and timeline entry for the banner.

The door `state` is visual only (`open`, `broken`, `blocked`). A blocked door must also have a rubble polygon so physics agrees with visuals.

#### Scenario events (`events`, optional)

A building's scripted disasters. The sim runs them **every run, deterministically**, in time order, at the start of the tick whose sim time reaches `t` (before the robots step, like a key press). No flag needed; `DZ_SCENARIO_EVENTS=0` switches them off (the benchmarks do, so their published numbers stay reproducible). A failed event (for example `radio_fail` before any relay exists) emits `scenario_event_failed` once and the run carries on. Separate from the opt-in `timeline` player (`DZ_SCENARIO_TIMELINE`). Not part of the planning prior, so the safety checker never sees them.

```json
"events": [{"t": 162.5, "type": "collapse", "near": "R1"}]
```

| type | fields | what happens | events emitted |
|---|---|---|---|
| `collapse` | `near` (robot id, default R1) or `at` [x, y]; `size` m (default 1.4, 0.25–4) | a rubble square at `at`, or 1.5 m ahead of `near`; if that spot would cut any robot off from space it could reach, the nearest safe spot on that robot's planned path; if none, refused | `rubble_fall` with `cause: "collapse"`, `robot` |
| `aftershock` | `at` [x, y] (default the first powered relay's position), `destroy_relay` (default true) | the A-key aftershock: 2 x 2 m rubble, a concrete wall segment, optionally the nearest relay destroyed | `rubble_fall`, `aftershock`, `relay_destroyed` |
| `radio_fail` | `relay` (default the first powered, non-phone relay) | that relay's radio dies; its stored bundles are lost; no rubble | `relay_destroyed` with `cause: "radio_fail"`, `radio_fail` |

Every entry needs `t` (sim seconds, 0–86400) and `type`; `label` is free text. At most 64 events. `collapse_01` carries one: `{"t": 162.5, "type": "collapse", "near": "R1"}`, the demo's secondary collapse on S1's rescue corridor. Variants (`variant_of`) drop the base's events.

### Occupancy grid

Row-major `uint8` array of `w * h` cells, row index = y. Values: `0` unknown, `1` free, `2` occupied, `3` no-go (hazard). Sent as base64 so a 160 x 120 map is 25.6 KB raw. Cell `(ix, iy)` covers `[ix*cell, (ix+1)*cell)` in x.

### Predicted Command RSSI grid (`DZ_COVERAGE_GRID`, default off)

Command samples the shared radio propagation model at every map cell center:
`((ix+0.5)*cell, (iy+0.5)*cell)`. Each value is the strongest predicted received
power from CMD (its configured `tx_dbm`) and relays whose latest **delivered**
telemetry says they are on (the existing fixed 20 dBm relay model). This is a
received-power prediction, not an end-to-end connectivity or live availability
guarantee; relays retain their last delivered position/power state until a newer
report arrives. Out-of-order reports do not rewind the prediction. Robot radios
are not prediction sources.

Geometry is Command's own sanitized pre-collapse prior: known walls and their
material losses, plus known furniture when `DZ_OBSTACLES=1`, using the same
wall-crossing code/constants as `network/propagation.py:rssi`. Hidden rubble,
dynamic walls, live relay/robot state and Reality's link graph are never inputs.
Delivered occupied cells alone do not establish a wall material/loss and therefore
do not add propagation segments. Each incident reset constructs a fresh prior
and discards delivered relay predictions/caches.

Wire samples are row-major **signed int8 dBm**, rounded to the nearest integer
(ties to even), clipped to `[-128,127]`, then zlib-compressed and base64-encoded.
Decode `coverage.data` with base64 -> zlib inflate -> `Int8Array`; index
`iy*coverage.w+ix` is dBm (no offset/scale). `-128` is saturated weak signal,
not an unknown-cell sentinel. All cells, including occupied/unknown occupancy
cells, contain a model prediction. Dimensions/resolution match the occupancy map.

### Thermal hot spots (`DZ_HEAT_SOURCES`, default off)

Schema, as agreed (Rayan, verbatim):
`{"id","type":"generator|space_heater|hot_pipe|server_rack|dog|laptop|sunlit","x","y","temp_c","size_m"}`;
thermal hits carry `kind` (`"survivor"|"decoy"`), `type`, `source_id`, `temp_c`; missing `kind` means survivor.

Every shipped building carries one source of each type in a room that fits it
(`collapse_01`, its five variants, `showcase_01`, `generated/gen_1..3`):
`collapse_01` has a generator on the warehouse floor, a space heater in Office B,
a hot pipe on the Storage wall shared with the boiler room, a server rack in the
Loading Office, a dog in the Break Room, a laptop in Office A and a sunlit patch on
the warehouse's loading side; variants inherit these; `generate.py`
(`place_heat_sources`) picks rooms by name and spots by type for generated buildings,
with no random draws.

The floor-plan producer supplies the user-agreed optional array (Rayan owns the
floor-plan data/schema):

```json
{"heat_sources":[{"id":"H1","type":"generator","x":12.5,"y":4.0,"temp_c":65,"size_m":0.8}]}
```

`type` is one of `generator`, `space_heater`, `hot_pipe`, `server_rack`, `dog`,
`laptop`, `sunlit`. IDs must be unique across sources/survivors/legacy decoys,
centers must be inside the map, all numbers finite and `size_m` positive. Only
when `DZ_HEAT_SOURCES=1` at Sim/Robot/CommandPost construction/reset does the
sensor parse these entries. Flag off ignores the array, preserves old hit and
telemetry shapes, and does no heat-source work.

Heat sources use the **same** 5 m center range, 120-degree forward cone and
line-of-sight test as survivors. Size/temperature do not alter those rules or
create occupancy. A heat-source `io.thermal()` hit is the existing survivor hit
shape plus typed metadata:

```json
{"id":"H1","pos":[12.5,4.0],"crop":"neg_0002.png","conf":0.99,
 "kind":"decoy","type":"generator","source_id":"H1","temp_c":65}
```

Survivor hits get `kind:"survivor"`; **missing kind means survivor**, keeping old
sensor/camera data valid. Existing decoys receive `kind:"decoy"` when enabled.
The available `neg_0001..0003.png` runtime crops are representative thermal
stand-ins, chosen by SHA-256 of `seed:id:type` modulo 3; this is stable across
processes, source ordering and resets and consumes no simulation RNG. These are
not temperature-generated images or newly trained type classifiers. The trained
person detector still scores the actual crop: the metadata never forces a
rejection or conceals a false positive. Without a model/crop score, new decoy
observations stay `verdict:"unsure",conf:null` and do not create rescue targets;
legacy survivor passthrough remains unchanged.

This flag enables the existing delivered camera telemetry path itself; a second
`DZ_CAMERA_TELEMETRY` flag is not required. `telemetry.payload.camera.hits[]` and
delivered phone/tick Command `robots[].camera.hits[]` preserve `kind` and the
optional `type`, `source_id`, `temp_c` alongside existing `{id,pos,crop,verdict,conf}`.
Camera metadata crosses the normal DTN custody/dedupe/TTL/version path; unseen
floor-plan source lists never enter phone hello, and dark phones retain their
last delivered observation/age. Metadata byte cost is included in bundle size.
Reality camera observations preserve it too when `DZ_SENSOR_VIEW` is enabled.
AI events (`hotspot_rejected`, `hotspot_unsure`, `survivor_found`) carry the same
source fields with **`hit_kind`** instead of `kind`, preserving the event name in
`event.kind`. The model verdict/confidence remain separate from source identity.

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

Public display strings (`msg`, `say`, report `text`, `plan_state` and
`detector_reason`) use sentence-case English and public robot/area names at the
HTTP/WebSocket presentation boundary. Error `code`, `rule`, `reason` enums,
identifiers, positions, timestamps and all envelope/response shapes are unchanged.
Safety messages retain the real violation values and outcomes; only their prose
is formatted. Planning, robot telemetry and stored acknowledgements stay intact.
Maps, geometry and camera bytes bypass text formatting. The same formatting is
applied to delivered acknowledgement speech before synthesis.

### Big screen: `WS /ws/screen`

| Direction | `t` | When | `data` |
| --- | --- | --- | --- |
| server to screen | `hello` | on connect and on reset | `floorplan`, `grid {w, h, cell}`, `robots [{id, name, color}]`, `speed`, `running` |
| server to screen | `tick` | every sim tick | `reality`, `command`, `stats` (below) |
| server to screen | `maps` | every 5 ticks | `w`, `h`, `reality` (b64), `command` (b64) |
| server to screen | `event` | when it happens | `kind` + fields, used for toasts, sounds and camera cues |
| server to screen | `report` | after `/api/report` | `text`, `generated_at` |
| screen to server | `control` | keyboard and buttons | `action`: `start`, `pause`, `reset`, `speed`, `director` + `value`; **`rubble` + `robot`** (`{t:"control", data:{action:"rubble", robot:"R2"}}`, REST `POST /api/control {action:"rubble", robot:"R2"}`: the R key on the followed robot, missing `robot` means R1; with `DZ_SMART_RUBBLE=1` the rubble lands on that robot's planned path 3-4 m ahead at a spot that traps nobody, otherwise 1.5 m ahead of it) |

#### Optional RSSI field (`DZ_COVERAGE_GRID`, default off)

When `DZ_COVERAGE_GRID=1` at CommandPost construction/reset, screen `maps.data`
and phone `cmd_view.data` gain the same self-contained `coverage` object:

```json
{"coverage":{"w":160,"h":120,"cell":0.25,"encoding":"zlib-base64",
 "dtype":"int8","unit":"dBm","predicted":true,"sources":["CMD","RL1"],
 "data":"<base64(zlib(signed int8 dBm samples))>"}}
```

`sources` lists the sorted, last-known-on transmitters used. The field has its
own encoding, independent of the surrounding occupancy map's encoding. It is
preserved as metadata by both existing compact protocols; negotiated screen
`map_patch.data` also carries this object, including a coverage-only update with
`grids:{}`. Normal map cadence is unchanged, and propagation/encoding results
are cached until the delivered source positions/on states change. It is absent
from per-tick `command` and AI tools. With the flag off the field is absent and
no prediction work occurs. Frontend rendering is a separate follow-up.

#### Compact screen maps (`DZ_COMPACT_STREAM`, default off)

At Hub construction, `DZ_COMPACT_STREAM=1` enables lossless map deltas for screens
that advertise `/ws/screen?map_deltas=1`. The web advertises this only when native
`DecompressionStream` is available; ordinary clients and the flag-off server keep
the existing base64 `maps` messages. Phones do not receive this screen protocol.
This gate does not enable the older `DZ_STREAM_OPTIMIZE` tick-rate cap. Tick/event
cadence and robot sensor inputs are unchanged. Screen lidar is capped at the
36 endpoints `Actors.Lidar` actually draws (18 via the existing perf-mode filter),
preserving every currently drawn endpoint and the fan geometry.
If `DZ_STREAM_OPTIMIZE` is separately enabled too, its existing 24-point / 15 Hz
profile is retained.

Negotiated `hello.data.compact_stream` declares
`{epoch,map_encoding:"zlib-base64",patch_encoding:"zlib-base64-u32le-u8",lidar_max_points:36}`.
Each connection, incident reset, or grid-dimension/key-set change starts with one
full compressed keyframe, using the ordinary envelope:

```json
{"t":"maps","seq":20,"time":0.1,"data":{
  "w":160,"h":120,"cell":0.25,"epoch":"incident-id","version":0,
  "encoding":"zlib-base64","reality":"<base64(zlib(uint8 grid))>",
  "command":"<base64(zlib(uint8 grid))>"}}
```

After that keyframe, each periodic map update sends **only changed cells**, never
a full periodic grid. Unchanged grids are omitted; no changes means no message:

```json
{"t":"map_patch","seq":30,"time":0.5,"data":{
  "w":160,"h":120,"cell":0.25,"epoch":"incident-id","base":0,"version":1,
  "encoding":"zlib-base64-u32le-u8","grids":{"command":"<compressed records>"}}}
```

Each `grids[key]` is base64 of a zlib stream of packed 5-byte records:
**uint32 little-endian row-major cell index, then uint8 value**. The index is
`iy*w+ix`; records are sorted by index and contain only cells changed since that
socket's last emitted version. Optional `belief` / `belief_command` grids use
the same encoding if already present; they are never fabricated. Optional JSON
metadata such as `missing` is preserved; metadata-only updates may have
`grids:{}`. Versions are per socket, so late joiners get their own independent
keyframe. `epoch` changes on incident reset. A geometry-only `hello` in the same
epoch does not discard the map baseline.

The web decodes messages in wire order, applies patches to new `Uint8Array`
buffers, and feeds the existing map store/renderer. An epoch/base mismatch,
invalid index or malformed record closes that screen connection with 1002 and
reconnects for a fresh keyframe. Recorded compact sessions normalize to legacy
full base64 maps, preserving the existing synchronous replay format.

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

### Phone JPEG frames (`DZ_PHONE_FRAMES`, default off)

At Hub construction/reset, `DZ_PHONE_FRAMES=1` enables screen-rendered robot-eye
JPEG uploads and advertises this in screen/phone `hello.data`:
`phone_frames:{epoch,max_width:320,max_height:180,max_fps:3}`. With the flag off,
this capability and all JPEG fields are absent, no canvas capture occurs, and
the upload endpoint returns 404. Existing thermal-hit camera data is unchanged.

`POST /api/frames/{robot_id}` accepts JSON `{epoch,t,jpeg}`: the advertised
incident epoch, capture time in sim seconds, and **bare base64 JPEG** (no data-URL
prefix). Decoded images must be JPEG, at most 320 pixels wide and 180 high,
and at most 128 KiB; JSON bodies are bounded too. The server validates the image,
keeps one latest accepted frame per robot in memory, and limits acceptance to
3 fps per robot in monotonic wall time across all uploaders. Capture times must
not be future, more than 3 sim seconds old, or older than the last accepted image.
Reset clears images/rate state and changes epoch, rejecting in-flight old uploads.

Admission/publication uses **Command's last delivered robot report**, age <=3
sim seconds, matching the phone's no-signal threshold; SHUTDOWN/no report is
unavailable. Reality's current link graph is never consulted. A dark upload is
refused (409) without changing the cached image; excess rate is 429, malformed
images/JSON are 422, oversized bodies 413, unknown robots 404. Success returns
`{ok:true,robot,t}` and publishes `cmd_view` to phones even when paused.

Only while that Command contact gate is open, phone `cmd_view.data.robots[]`
may contain `phone_frame:{jpeg,mime:"image/jpeg",width,height,t,last_seen_s}`.
The age is sim time since capture. During darkness the server omits this field;
a phone retains only its own previously received JPEG, ages it, and shows its
existing NO SIGNAL overlay. A phone joining while dark receives no hidden image.
New incidents clear the phone's cache. JPEGs never enter tick.command, screen
ticks/maps, Command AI tools, DTN bundles or persistent storage.

The big screen captures its **existing open robot-eye canvas** after rendering,
fits/letterboxes into 320x180 at JPEG quality 0.7, and uploads at most 3 fps while
connected and Command contact is fresh. It creates no extra render canvas or
scene; changing robots closes/aborts the old sender. Closing/hiding the scout
camera stops uploads, so the phone keeps its last received image or uses the
existing delivered thermal-hit/crop fallback. This is rendered simulation imagery,
not detector input or a new ML inference source.

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
| `GET /api/join` |  | `{url}` for Q/QR: local/loopback/wildcard frontend hosts become the routed laptop LAN IPv4 (port preserved), never localhost; public HTTPS/tunnel origins stay unchanged. Returns 503 if no usable LAN address exists. |

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
| R | drop rubble in front of the followed robot: `control` with `action: "rubble"`, `robot: "R2"` (missing means R1) |
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
