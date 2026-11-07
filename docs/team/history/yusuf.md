# Yusuf Nusrat: web frontend (Person 3)

Owns `web/`. Only Yusuf's sessions edit this file.

## Now
- **Working on:** `p3/visual-pass` (M7, stacked on M6 / PR #24): figures, bigger robots, phone last crop, liquid glass and robot's-eye view committed. Rescue route drawing when Rayan's contract lands; then rehearsal fixes and the replay fallback.
- **Works on main:** M1 phone + QR (PR #10), M2 network visuals + toasts + T (PR #16), M3 plan editor + safety card (PR #18), M4 scheduler strip + follow cam + F/G (PR #20), M5 relay phone mode (PR #23).
- **In flight (not merged):** `p3/ai-scope`:
  - AI detection cards (frosted glass): Reality on `survivor_found` ("Person · 100%", "no link, holding the report") and `hotspot_rejected` (faded "Not a person · 0% · rejected"); Command on `survivor_reported` with the delivered record's `crop`. Image `/crops/<crop>`, thermal placeholder until the backend serves it.
  - Detector chip in the top bar from `hello.detector` (hidden until the server sends it).
  - Keys O (`do:"overload"`) and U (`do:"resume"`), plus a "Send resume command" button on a robot card in SAFE_STOP. Key list moved to the sidebar.
  - Phone robot cards: "Following P-1 · zone Z1 (last report)" from delivered `cmd_view.robots[].plan_id/zone` (PR #22).
- **Blocked on / need from others:** Aziz: `/crops/<file>` static route (cards show a placeholder until then) and `hello.detector` (chip hidden until then). Rayan: `rescue_route` contract.
- **Promises to others:**
  - Rayan's asks (19:50 entry): 1 bigger/brighter robots: yes, 3 AM. 2 robot's-eye view: **Yusuf keeps it** (`web/src/three/RobotEye.jsx`), built last, cut first. 3 phone tap-a-robot with `cmd_view.survivors[].crop`: yes, 3 AM. 4 liquid glass: yes, started on the detection cards, full pass by 3 AM. 5 rescue route on Command: yes, as soon as the contract is posted.
  - Truth survivors and decoys show only on the Reality pane (T). Never on Command. The UI renders actual robot state and never assumes a dispatch, fault or resume made a robot act.

## Log

### 2026-11-07 21:20 · p3/visual-pass · M7 part 2: robot's-eye view
- **Did:** V (or a robot card's Camera button) opens a small picture-in-picture on the Reality pane from that robot's forward camera (Reality telemetry pose, smoothed). Thermal toggle: walls cold blue, survivors glow white-hot and decoys glow amber, so judges see why the detector has to decide. It is a third small WebGL canvas (dpr 1, low-power) that only exists while open.
- **Contract changes:** none. New key V.
- **Heads-up for others:** Rayan: robot's-eye view done in `web/src/three/RobotEye.jsx` as agreed; DEMO.md can add V. Closing the camera logs "THREE.WebGLRenderer: Context Lost" in the console; that is the PiP disposing its own context, not a crash.
- **Next:** rescue route drawing (waiting on the `rescue_route` contract), rehearsal fixes.

### 2026-11-07 21:00 · p3/visual-pass · M7 part 1: survivor figures, bigger robots, phone last crop, liquid glass
- **Did:** survivors are low-poly people lying down in thermal colors (head hottest) with a warm floor glow, pulsing ring and arrival shockwave kept. Robots draw 1.8× with stronger emissive and a colored glow pool (ghosts stay dim). Phone: tap a robot card to see the last thermal crop and verdict it reported (delivered `cmd_view.survivors[]` with `by` = that robot). Liquid glass: frosted overlays on the panes, translucent top bar / sidebar / scheduler, phone cards frosted over a soft color wash.
- **Contract changes:** none.
- **Heads-up for others:** robots now look ~0.9 m wide on screen (the physics body is unchanged). Branch is stacked on PR #24 (M6), which still needs merging.
- **Next:** robot's-eye view (`web/src/three/RobotEye.jsx`), rescue route drawing.

### 2026-11-07 20:30 · p3/ai-scope · M6 AI detection cards, detector chip, O / resume, phone plan status
- **Did:** judges now see what the onboard model judged: a card with the crop and verdict when a robot finds a person or rejects a hot spot (Reality), and again when the report reaches Command. O overloads the followed robot's perception, U or a card button sends resume. Tested on main with PR #22 and the CPU model loaded: "Person · 100%" (S3), "Not a person · 0% · hot spot D1 · R2 · rejected", S2 at 88.9%; O → R1 row "perception missed" while safety runs at 0/50 ms; F×3 → SAFE_STOP → resume button → "R2 resumed after safe stop".
- **Contract changes:** none new. Consumes `survivor_found.crop/conf`, `hotspot_rejected`, Command `survivors[].crop`, director `overload` / `resume`, delivered `plan_id` / `zone`, and (when added) `hello.detector` + `/crops/<file>`. Vite dev proxy now forwards `/crops` to the backend.
- **Heads-up for others:** Rayan: answers to your 19:50 asks are in `## Now` (I keep the robot's-eye view). DEMO.md: O is live once this merges; resume is key U or the "Send resume command" button on the robot's card. Aziz: the cards and chip are ready for `/crops` and `hello.detector`.
- **Next:** survivor figures, bigger robots, phone tap-a-robot, liquid glass, rescue route, robot's-eye view.

### 2026-11-07 19:00 · p3/phone-relay · M5 relay phone mode, relay power toasts, feed fix
- **Did:** a phone that scans the relay QR becomes a relay: one big button turns it on/off, it shows what it carries and who it can hear, and it can be moved by tapping the map. The big screen toasts each switch. Tested on main: RL1 created at the entry with 4 neighbors, off/on/off toasts on the big screen, move into the Break Room, rubble tap rejected, reload with the same label keeps RL1 off at its new spot.
- **Contract changes:** none. Uses `relay_state`, `relay_power`, `relay_place`, `hello.relay_id`, `invalid_relay_position` from PR #12.
- **Heads-up for others:** while the sim is paused the big screen gets no ticks, so relay changes show there only after Space (phones update immediately). A relay phone that sleeps or closes the tab switches its relay off (server rule), so keep phones awake during the demo. Each phone needs its own label (automatic per browser).
- **Next:** M6 polish, M7 replay file for the backup demo.

### 2026-11-07 18:40 · p3/timeline-camera · M4 scheduler strip, follow camera, F/G keys, decoys
- **Did:** the big screen shows each robot's scheduler frame live (safety preempting, busy %, missed deadlines in red), follows a robot with keys 1-3 / 0, injects overcurrent with F on the followed robot (the robot's own fault toast follows), opens a typed Command briefing with G, and the T overlay marks decoys. Tested on main at 4x: follow R1/R2, F → "R1 fault: Wheel overcurrent" + replan, G → local briefing incl. the reported fault.
- **Contract changes:** none new. Uses telemetry `tasks`, director `do:"overcurrent"` / `do:"rubble"`, `GET /api/report` + `report` message, floorplan `decoys`.
- **Heads-up for others:** keyboard map for the demo: 1-3 follow, 0 overview, R rubble, F fault, G briefing, T truth, Q join, Space, Backspace, +/-. The strip's red miss styling is untested live until the O key / overload director value exists. Rayan: the Command camera follows the last reported pose by design.
- **Next:** M5 relay phone mode.

### 2026-11-07 18:05 · p3/phone-plan · M3 plan editor, safety card, plans on the big screen
- **Did:** phones draw zones and no-go areas, assign robots, run the safety check, fix a dead-zone rejection in one tap and dispatch. The big screen shows the shared plan (draft dashed, dispatched solid) and which zone each robot follows. Tested end to end on main (reject → allow dark → pass → dispatch → "R2 is following P-1 (Z1)") and against PR #12 merged with main locally (plan before Space at T+0.1, screen zones, plan_dispatched).
- **Contract changes:** none new. Uses `plan_edit`, `plan_submit`, `safety`, `plan_state`, `error`, `POST /api/dispatch`, PR #12's screen `plan_state` / `plan_dispatched` / `cmd_view.faults`, and Rayan's `plan_applied` / `resumed` / telemetry `plan_id` + `zone`.
- **Heads-up for others:** Aziz: PR #12 merges cleanly with current main (checked locally); its relay_dropped `owner` is a phone client label, the UI now words that as "Phone X joined as relay RLn". Rayan: the demo plan works as you suggested (R2 east wing zone, dark OK).
- **Next:** M4 timeline + follow camera + director keys.

### 2026-11-07 17:15 · p3/relays-links · M2 network visuals, toasts, truth toggle
- **Did:** the big screen now shows relays and the real link mesh, pulses the antenna on deliveries, bursts survivors onto Command, toasts key events, shows wheel current / relays left / fault pills, and a found-vs-reported counter. T toggles truth survivors (Reality only). Camera fits the building. Tested on a live 3-robot sim at 8x.
- **Contract changes:** none. Reads existing `tick.reality.relays/links`, `command.relays`, `stats.delivered`, telemetry `wheel_a` / `relays_left` / `fault`, and the documented event kinds.
- **Heads-up for others:** new keyboard shortcut T (truth overlay). `survivors_found` has one record per robot that saw a survivor; the UI dedupes by id. Aziz: when F/O director controls land I'll wire the keys.
- **Next:** M3 plan editor + safety card on `p3/phone-plan`.

### 2026-11-07 17:00 · p3/phone-shell · M1 phone shell + QR join (PR open)
- **Did:** judges scan a QR on the big screen and get `/phone`: live Command view map, robot cards, reported survivors, auto reconnect. Tested against a live 3-robot sim: relays, survivors (incl. S1 in the cage), reset and server restart all reach the phone.
- **Contract changes:** none. Uses only existing `/ws/phone` (`hello`, `cmd_view`, `error`) and `GET /api/join`. Phones never receive Reality data.
- **Heads-up for others:** in dev the phone link is `http://<laptop-ip>:5173/phone`; after `npm run build` the server serves it on :8000. New npm dep: run `npm install` in `web/` after pulling.
- **Next:** M2 on `p3/relays-links`.

### 2026-11-07 · p3/team-context · Team context system (this file)
- **Did:** added `docs/team/` (protocol + per-person history), the `.claude/` hooks (`team_sync`, `history_guard`), and the `/team-sync` and `/log-work` commands.
- **Contract changes:** none (tooling only)
- **Heads-up for others:** after pulling, every Claude session reads these files automatically. Commits made through Claude must stage your own history file (the hook enforces it).
- **Next:** finish and PR the phone shell.
