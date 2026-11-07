# Aziz: backend + network (Person 2)

Owns `server/deadzone/sim.py`, `app.py`, `floorplan.py`, `network/`, `command/`. Only Aziz's sessions edit this file.

## Now
<!-- seeded 2026-11-07 ~16:30 ET from git history by Yusuf's Claude. Aziz's Claude: overwrite this on your next commit. -->
- **Working on:** unknown. Aziz's Claude, fill this in.
- **Works on main:** multi-hop DTN with per-hop custody, phone planning REST + WS, Command-based safety checks
- **In flight (not merged):** `p2/peer-telemetry-dtn` (928738b): peer telemetry delivered through DTN custody queues, replacing Rayan's temporary shim. Also reported: `p2/frontend-backend-contract` (local only, not on origin yet)
- **Blocked on / need from others:** unknown
- **Promises to others** (agreed with Yusuf, not merged yet):
  - Reset/startup runs one real tick, then stays paused. Safety checks work before Space.
  - `plan_state` goes to `/ws/phone` AND `/ws/screen` on edits and accepted dispatch. Screens get the current plan on connect, `null` on reset. A `plan_dispatched` event marks accepted dispatch.
  - F key: `control {action:"director", value:{do:"overcurrent", robot:"R1"}}`, REST `POST /api/fault {type, robot}`.
  - G key: `GET /api/report` returns a Command-only briefing with `source:"local"` (never label it Gemini).
  - Relay phones: `/ws/phone?client=<id>&role=relay`, `hello.relay_id`, send `relay_place {pos}` / `relay_power {on}`, receive `relay_state {id,on,pos,queue,neighbors}`.
  - `bundle_delivered` event for final CMD deliveries only.

## Log

### 2026-11-07 · p2/peer-telemetry-dtn · Peer telemetry through DTN (not merged yet)
- **Did:** robots' telemetry reaches peers via DTN custody queues instead of the sim shortcut.
- **Contract changes:** none known
- **Heads-up for others:** Rayan's temporary shim in `sim.py` goes away when this merges.
- **Next:** unknown

### 2026-11-07 · p2/phone-plans-safety · PR #4 Phone planning APIs + safety checks
- **Did:** phone planning REST/WS endpoints, `command/plan.py`, `command/safety.py` (safety checks use only Command knowledge). Routing aligned with Rayan's robot endpoint contract.
- **Contract changes:** see `docs/PHONE-PLANNING.md` (new) and the `docs/DTN.md` updates.
- **Heads-up for others:** Yusuf's phone planner builds against `docs/PHONE-PLANNING.md`.
- **Next:** frontend-backend contract.

### 2026-11-07 · p2/dtn-multihop · PR #2 Multi-hop DTN with custody
- **Did:** bundles forward through relay queues with per-hop custody. `command/post.py` only updates from delivered bundles.
- **Contract changes:** see `docs/DTN.md` (new).
- **Heads-up for others:** none
- **Next:** phone planning.
