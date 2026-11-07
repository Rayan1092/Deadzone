# Yusuf Nusrat: web frontend (Person 3)

Owns `web/`. Only Yusuf's sessions edit this file.

## Now
- **Working on:** `p3/phone-plan` (M3) committed, PR not open yet. Next: M4 task timeline, follow camera, director keys (F, G, O) on `p3/timeline-camera`.
- **Works on main:** M1 phone shell + QR (PR #10). M2 relays/links, toasts, T truth overlay, camera fit (PR #16).
- **In flight (not merged):** `p3/phone-plan`:
  - Phone planner: tap Add zone / Add no-go, drag a rectangle on the map (0.5 m snap, min 1 m), tap a zone to edit robot, priority, radio (relay link / dark OK), delete. Dark budget slider. Edits go out as `plan_edit` (debounced); incoming `plan_state` replaces the draft ("edited by phone-b").
  - Safety card: Run safety check (`plan_submit`) → pass/fail card; failed zones pulse red on the map; `comms_plan` has a one-tap "Allow Zx to go dark" fix. Dispatch = `POST /api/dispatch`; card says "dispatched to R2, starts once the plan reaches it" (never claims the robot acted). Editing a dispatched plan starts P-(n+1); a `plan_dispatched` error from the server forks too.
  - Phone robot cards show delivered `cmd_view.faults` when present (PR #12 field).
  - Big screen: draws `plan_state` zones/no-go on both panes above the fog (dashed draft, solid after `plan_dispatched`); toasts plan_dispatched, plan_applied, resumed; sidebar "Following P-7 · zone Z1" from Reality telemetry `plan_id`/`zone`.
- **Blocked on / need from others:** Aziz: PR #12 merge (screen `plan_state`, `plan_dispatched`, startup tick, F/G, relay phones). Aziz: Command's robot view has no `plan_id`/`zone`, so phones can't show which robots are following a plan.
- **Promises to others:** truth survivors show only as a faint outline on the Reality pane, off by default, toggled with T. Never on Command. The UI renders actual robot state and never assumes a dispatch or fault made a robot act.

## Log

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
