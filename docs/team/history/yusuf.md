# Yusuf Nusrat: web frontend (Person 3)

Owns `web/`. Only Yusuf's sessions edit this file.

## Now
- **Working on:** `p3/relays-links` (M2) committed, PR not open yet. Next: M3 plan editor + safety card on `p3/phone-plan`.
- **Works on main:** M1 (PR #10): `/phone` live Command view, sidebar QR + Q overlay, lazy route chunks.
- **In flight (not merged):** `p3/relays-links`:
  - 3D relays (Reality: power lamp, queue, phone flag; Command: announced position only) and real radio link edges (green, amber when weak/`fec`, red dashed robot-to-CMD when a robot has no link). Robot-to-robot edges are not drawn (not routes).
  - Antenna pulse on each `stats.delivered` increase; shockwave when Command first learns a survivor.
  - Toasts for survivor_found (first sighting only), survivor_reported, link_lost, link_restored (`dark_s`), relay_dropped, fault, rubble_fall, safety_reject. Feed folds repeated replan / deadline_miss into one line with a count.
  - Sidebar: fault pill (SAFE_STOP red), `wheel_a` (amber >= 4 A, red >= 6 A), relays left. Top bar: survivors found vs reported (deduped by id).
  - T key: faint truth survivors on Reality only, above the fog. Overview camera now fits the whole building to the pane.
  - Fix: the rubble `hello` no longer wipes the event feed (only a reset, time going back, clears it).
- **Blocked on / need from others:** Aziz's `p2/frontend-backend-contract` merge (`plan_state`, relay phone messages, director control incl. F/O keys, `/api/report`, `bundle_delivered`).
- **Promises to others:** truth survivors show only as a faint outline on the Reality pane, off by default, toggled with T. Never on Command. The UI renders actual robot state and never assumes a dispatch or fault made a robot act.

## Log

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
