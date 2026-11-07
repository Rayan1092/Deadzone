# Yusuf Nusrat: web frontend (Person 3)

Owns `web/`. Only Yusuf's sessions edit this file.

## Now
- **Working on:** `p3/timeline-camera` (M4) committed, PR not open yet. Next: M5 relay phone mode on `p3/phone-relay` (backend is on main since PR #12).
- **Works on main:** M1 phone shell + QR (PR #10). M2 relays/links, toasts, T truth overlay, camera fit (PR #16). M3 phone plan editor, safety card, plans on the big screen (PR #18).
- **In flight (not merged):** `p3/timeline-camera`:
  - Scheduler strip under the panes: one row per robot over the last 100 ms, task colors, busy %, missed slices red with a 1.5 s red pulse and "perception missed" flag.
  - Follow camera: keys 1-3 (or click a robot card), 0 back to overview. Reality follows the robot; Command follows its last reported pose so the camera never reveals a dark robot. Orbit angle and zoom stay synced.
  - Director keys act on the followed robot (else R1): R rubble, F overcurrent (`do:"overcurrent"`). G opens the briefing panel from `GET /api/report`, labelled "Local summary · Command data only" unless `source` is gemini.
  - T overlay also shows the floorplan `decoys` (amber, "D2 engine · decoy"), Reality only.
  - 3D labels are a constant size and render under overlays (no more giant labels when zoomed). Screen socket closes on remount (no duplicate events after hot reload).
- **Blocked on / need from others:** Aziz: director `do:"overload"` (O key) and `do:"resume"`; decoys in `RobotIO.thermal()`. Command's robot view has no `plan_id`/`zone` for phones.
- **Promises to others:** truth survivors and decoys show only as faint outlines on the Reality pane, off by default, toggled with T. Never on Command. The UI renders actual robot state and never assumes a dispatch or fault made a robot act.

## Log

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
