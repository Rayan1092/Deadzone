# Yusuf Nusrat: web frontend (Person 3)

Owns `web/`. Only Yusuf's sessions edit this file.

## Now
- **Working on:** `p3/phone-shell`: phone app shell + QR join panel (committed cc5862c, d8e4471; PR not open yet)
- **Works on main:** starter 3D split view only (Reality vs Command post knows)
- **In flight (not merged):** `p3/phone-shell`:
  - `/phone` route with a landing role picker (planner / relay). The QR links encode `?role=planner` / `?role=relay`.
  - Planner: 2D canvas map (`web/src/phone/PlanMap.jsx`), prior plan plus delivered Command knowledge, rectangle zones first.
  - Relay role, own phone store/socket (`web/src/phone/`), screen wake lock.
  - Big screen moved into `web/src/BigScreen.jsx`. Each route is a lazy chunk, so phones never download three.js.
  - Q key: full-screen QR overlay (`web/src/panels/JoinPanel.jsx`), uses `GET /api/join`.
  - New dep `qrcode.react`. Vite `/api` proxy keeps the browser Host (`changeOrigin:false`).
- **Blocked on / need from others:** Aziz's `p2/frontend-backend-contract` merge (`plan_state`, relay phone messages, director control, `/api/report`). Rayan's `tasks` timeline is merged (PR #7), so the timeline strip is unblocked.
- **Promises to others:** truth survivors show only as a faint outline on the Reality pane, off by default, toggled with T. Never on Command. The UI renders actual robot state and never assumes a dispatch or fault made a robot act.

## Log

### 2026-11-07 · p3/team-context · Team context system (this file)
- **Did:** added `docs/team/` (protocol + per-person history), the `.claude/` hooks (`team_sync`, `history_guard`), and the `/team-sync` and `/log-work` commands.
- **Contract changes:** none (tooling only)
- **Heads-up for others:** after pulling, every Claude session reads these files automatically. Commits made through Claude must stage your own history file (the hook enforces it).
- **Next:** finish and PR the phone shell.
