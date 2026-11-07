# Yusuf Nusrat: web frontend (Person 3)

Owns `web/`. Only Yusuf's sessions edit this file.

## Now
- **Working on:** `p3/phone-shell` PR open for review (M1). Next branch: `p3/relays-links` (M2: relay/link rendering, toasts, truth toggle T, wheel_a readout).
- **Works on main:** starter 3D split view only (Reality vs Command post knows)
- **In flight (not merged):** `p3/phone-shell`:
  - `/phone` route with a landing role picker (planner / relay). The QR links encode `?role=planner` / `?role=relay`.
  - Live Command view on a 2D canvas map (`web/src/phone/PlanMap.jsx`): prior walls/rooms/hazards plus delivered map, robots (ghosted when `stale_s > 3`), relays, reported survivors. Robot cards and survivor list.
  - Relay role currently only watches the Command view (relay controls are M5, waiting on Aziz).
  - Big screen moved into `web/src/BigScreen.jsx`. Each route is a lazy chunk, so phones never download three.js (~50 KB gzip vs 243 KB).
  - Sidebar QR card; Q key opens a full-screen planner + relay QR overlay (`web/src/panels/JoinPanel.jsx`), uses `GET /api/join`.
  - New dep `qrcode.react`. Vite `/api` proxy keeps the browser Host (`changeOrigin:false`) so the dev join link points at :5173.
- **Blocked on / need from others:** Aziz's `p2/frontend-backend-contract` merge (`plan_state`, relay phone messages, director control, `/api/report`). Rayan's `tasks` timeline is merged (PR #7), so the timeline strip is unblocked.
- **Promises to others:** truth survivors show only as a faint outline on the Reality pane, off by default, toggled with T. Never on Command. The UI renders actual robot state and never assumes a dispatch or fault made a robot act.

## Log

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
