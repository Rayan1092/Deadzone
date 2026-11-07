# Aziz: backend + network (Person 2)

Owns `server/deadzone/sim.py`, `app.py`, `floorplan.py`, `network/`, `command/`. Only Aziz's sessions edit this file.

## Now
- **Working on:** `p2/frontend-backend-contract`: sync and integration review against main `059dd63` (PRs #8, #10 and #11 merged). No new feature implementation during this sync.
- **Works on main:** multi-hop DTN with per-hop custody, phone planning REST + WS, Command-based safety checks, peer telemetry through DTN (PR #11; direct-copy shim removed).
- **In flight (not merged):** PR #12, `p2/frontend-backend-contract`: paused startup/reset telemetry, screen plan state, phone relay lifecycle, overcurrent director/API, local report and final-CMD delivery events. GitHub currently reports conflicts on the published PR; local branch integrates latest main and preserves published ancestry, so a normal push of this sync is pending.
- **Blocked on / need from others:** PR #12 merge unblocks Yusuf's relay controls/screen plan/report consumers. Rayan's open PR #13 adds network-delivered SAFE_STOP resume; plan execution remains Rayan's next task. Aziz next wires `do:"overload"` and, once #13 lands, `do:"resume"` through CMD's DTN queue. Current director accepts only rubble/overcurrent. Gemini generation, real FEC and recorder/replay remain later Person 2 milestones; CRDT is optional.
- **Promises to others** (implemented in PR #12, not on main yet):
  - Reset/startup runs one real tick, then stays paused. Safety checks work before Space.
  - `plan_state` goes to `/ws/phone` AND `/ws/screen` on edits and accepted dispatch. Screens get the current plan on connect, `null` on reset. A `plan_dispatched` event marks accepted dispatch.
  - F key: `control {action:"director", value:{do:"overcurrent", robot:"R1"}}`, REST `POST /api/fault {type, robot}`.
  - G key: `GET /api/report` returns a Command-only briefing with `source:"local"` (never label it Gemini).
  - Relay phones: `/ws/phone?client=<id>&role=relay`, `hello.relay_id`, send `relay_place {pos}` / `relay_power {on}`, receive `relay_state {id,on,pos,queue,neighbors}`.
  - `bundle_delivered` event for final CMD deliveries only.
  - `io.radio.receive()` drains complete commands/plans and unread legacy peer telemetry once, in priority order. Existing `robot.inbox` peer readers remain compatible; removing that attribute routes all deliveries into the IO buffer. Rayan must handle telemetry too if migrating completely to this API.
  - Reported faults in `command.faults` / phone `cmd_view.faults` are delivered history, not live fault flags. No Command/phone truth fallback.

## Log

### 2026-11-07 14:08 PT · p2/frontend-backend-contract · Team sync and frontend contract catch-up
- **Did:** pulled main through `059dd63`, read all three histories plus the protocol/hooks, and integrated scheduler/fault PR #8, phone-shell PR #10 and peer-DTN PR #11 into the local backend branch. Preserved the published branch ancestry (no force push required). Combined verification: 134 backend tests pass; new QR dependency installed and production web build passes. Implementation in this entry covers the existing frontend-contract commit; this sync changes only Aziz's history.
- **Contract changes:** PR #12 primes one real tick at startup/reset (paused T+0.1 s); broadcasts `plan_state` to phones/screens and `plan_dispatched` to screens; adds own-node `relay_place {pos}`, `relay_power {on}` and `relay_state {id,on,pos,queue,neighbors:[{id,rssi}]}` for `/ws/phone?client=<id>&role=relay`, with `hello.relay_id`; adds `POST /api/fault` for rubble/overcurrent, director `{do:"overcurrent",robot:"R1"}`, `GET /api/report` / screen `report {text,generated_at,source:"local"}`, delivered `command.faults` and final-CMD `bundle_delivered {src,dst,bundle_kind,hops,delay_s}`. Unified `io.radio.receive()` drains commands and legacy peers exactly once. Details: `docs/FRONTEND-HANDOFF.md`, `docs/PHONE-PLANNING.md`, `docs/DTN.md`.
- **Heads-up for others:** PR #12 is still open; its current GitHub body is an unfilled template (use the prepared contract PR description). Yusuf's main phone shell observes Command; planner editing/safety card, relay controls, screen plan/report consumers and timeline remain frontend work. Rayan's PR #13 was read, not merged: resume must be queued at CMD, never injected directly into a robot. `.claude` hooks target Claude/Bash and `python3`; Codex/PowerShell follows this protocol manually. Hook detection sees only fetched commits, and the history guard accepts any history file, so follow ownership/freshness rules manually too. PLAN.md's starter "Not started" section is historical; use these histories plus code/PR state for current status.
- **Next:** publish this context sync and complete PR #12's description/merge; then wire overload and network resume in our backend area with matching contracts, before Gemini/FEC/recorder work and a full LAN/soak rehearsal. No web or robot policy edits in this sync.

### 2026-11-07 · p2/peer-telemetry-dtn · Peer telemetry through DTN (merged as PR #11)
- **Did:** robots' telemetry reaches peers via DTN custody queues instead of the sim shortcut.
- **Contract changes:** no WS/payload shape changes. Each peer gets a source-queued unicast copy with `bid = original_bid + "/" + recipient_id`, TTL capped at `PEER_FRESH_S` (15 sim seconds), independent payload snapshot and realistic JSON byte accounting; queue/in-flight counts and delivery timing change. Commands remain in their separate IO inbox on main.
- **Heads-up for others:** Rayan's temporary shim in `sim.py` is gone on main. Existing `robot.inbox` receives peer telemetry only after DTN delivery; PR #12 also exposes unread peers through unified IO without duplicate copies.
- **Next:** frontend backend contract PR #12.

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
