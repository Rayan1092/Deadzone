# Aziz: backend + network (Person 2)

Owns `server/deadzone/sim.py`, `app.py`, `floorplan.py`, `network/`, `command/`. Only Aziz's sessions edit this file.

## Now
- **Working on:** PR #22, `p2/demo-controls-sensors`: ready for requested merge after syncing main `1414ec2` and Rayan's new fallback-safety requirement.
- **Works on main:** multi-hop DTN/custody, peer telemetry, planning/safety APIs and all PR #12 contracts (paused first tick, screen plans, phone relay lifecycle, overcurrent/rubble, local report, delivered faults/events). PR #12 is merged. Rayan's plan execution/detector hookup and Yusuf's phone planner/timeline are also on main.
- **In flight (not merged):** PR #22 implements backend items 1-4 and suppresses decoys in sim/model-unavailable fallback. Full backend suite: 161 passed with the CPU model loaded, no skips; latest M5 frontend build passes. Local model environment has Pillow, CPU torch and torchvision.
- **Blocked on / need from others:** Yusuf: bind O to `do:"overload"`, add resume UI, consume delivered phone `plan_id`/`zone` if desired; M5 relay phone UI is now on main. Every demo laptop needs verified model dependencies to demonstrate real decoy rejection; fallback emits survivors only. Newly added scope still needs Aziz's `/crops` static route and detector status in hello, followed by Gemini tool-calling, actual FEC, recorder/replay and full LAN/soak rehearsal; CRDT optional.
- **Promises to others** (PR #12 on main; follow-up additions in flight):
  - Director adds `{do:"overload",robot}` (400 ms perception work for 3 sim seconds) and `{do:"resume",robot}` (priority-1 command queued at CMD, execution only after network delivery). Existing REST fault variants remain rubble/overcurrent.
  - With the model active, `RobotIO.thermal()` includes floorplan decoys with survivor-identical range/FOV/LOS and `{id,pos,crop,conf}` only; no decoy label/flag reaches the robot. In sim/model-unavailable fallback it emits survivors only. Classification remains Rayan-owned.
  - Command/phone robot records add nullable `plan_id`/`zone`. Source status is sampled once into fresh telemetry before DTN fanout; Command changes only on delivery, and queued old reports are never filled with newer live state.
  - Reset/startup runs one real tick, then stays paused. Safety checks work before Space.
  - `plan_state` goes to `/ws/phone` AND `/ws/screen` on edits and accepted dispatch. Screens get the current plan on connect, `null` on reset. A `plan_dispatched` event marks accepted dispatch.
  - F key: `control {action:"director", value:{do:"overcurrent", robot:"R1"}}`, REST `POST /api/fault {type, robot}`.
  - G key: `GET /api/report` returns a Command-only briefing with `source:"local"` (never label it Gemini).
  - Relay phones: `/ws/phone?client=<id>&role=relay`, `hello.relay_id`, send `relay_place {pos}` / `relay_power {on}`, receive `relay_state {id,on,pos,queue,neighbors}`.
  - `bundle_delivered` event for final CMD deliveries only.
  - `io.radio.receive()` drains complete commands/plans and unread legacy peer telemetry once, in priority order. Existing `robot.inbox` peer readers remain compatible; removing that attribute routes all deliveries into the IO buffer. Rayan must handle telemetry too if migrating completely to this API.
  - Reported faults in `command.faults` / phone `cmd_view.faults` are delivered history, not live fault flags. No Command/phone truth fallback.

## Log

### 2026-11-07 14:55 PT · p2/demo-controls-sensors · Sync before merge and protect fallback from false survivors
- **Did:** integrated main `1414ec2` (Rayan's detection events/scope and Yusuf's M5) before the requested PR #22 merge. Added Rayan's newly merged requirement: the thermal sensor emits no decoys when the active detector is in fallback mode. Full combined suite: 161 passed, no skips; frontend production build passes.
- **Contract changes:** model mode still emits visible survivors and decoys with identical rules/shape. `DETECTOR=sim`, missing model/dependencies or model-load failure now suppress decoys at the sensor, so passthrough cannot report them as survivors. Added tests for explicit sim and missing-checkpoint fallbacks.
- **Heads-up for others:** this supersedes the prior entry's fallback warning. Real model tests still verify all three survivor/decoy crop decisions. `/crops` and `hello.detector` are separate newly added scope, not implemented by this PR. O/resume and delivered plan/zone contracts are unchanged.
- **Next:** publish the tested sync and merge PR #22 as requested, then pull merged main.

### 2026-11-07 14:49 PT · p2/demo-controls-sensors · Backend demo controls, decoys and phone plan status
- **Did:** implemented overload and network-delivered resume director controls, real thermal decoy inputs, and delivered Command/phone plan status. Installed CPU torch 2.15.0+cpu, torchvision 0.29.2+cpu and Pillow 13.0.0 in this laptop's uv-managed venv. Verified model mode: all 3 survivor crops accepted, all 3 decoys rejected (0.000, 0.000, 0.003 vs threshold 0.6). Full suite: 159 passed with no skips; production web build passed after syncing Yusuf's M4 main `75f9609` (no new backend changes in that merge).
- **Contract changes:** screen/REST director values add `{do:"overload",robot}` and `{do:"resume",robot}` with strict schema/robot validation. Overload calls Rayan's default hook; resume queues `resume_command()` at CMD and never clears faults directly. `io.thermal()` now returns visible floorplan decoys in the existing hit shape. `tick.command.robots` / `cmd_view.robots` add `plan_id` and `zone` (string or null), learned only from delivered source snapshots. Details/setup: `docs/DEMO-CONTROLS.md`, linked from frontend handoff and phone API docs.
- **Heads-up for others:** Yusuf can wire O/resume and phone following labels against these contracts; acceptance means queued, not executed. Rayan's robot/ML/floorplan files were not edited. The source adapter uses existing public `Robot.telemetry()` only for fresh reports and preserves sender-provided fields if Rayan later includes them directly in `_emit_bundles`. Model fallback still trusts decoys: use the verified model environment for the decoy demo. Tests cover disconnection, real scheduler misses without safety misses, API-to-robot-to-phone roundtrip, stale report ordering, sensor visibility and real model rejection.
- **Next:** publish/review this PR, then the later Gemini/FEC/recorder milestones and a full demo-network rehearsal.

### 2026-11-07 14:14 PT · p2/frontend-backend-contract · Resolve PR #12 against current main
- **Did:** integrated main `5b441e5`, including Rayan's resume PR #13 and detector PR #14, into the previously resolved frontend backend branch. Kept the published PR head as an ancestor, so publishing resolves conflicts without rewriting anyone's remote history. Full backend suite: 139 passed, 1 skipped (optional trained-model test requires torch/torchvision); merge has no unresolved paths or whitespace errors. The frontend build already passed on the unchanged web files.
- **Contract changes:** none beyond the existing PR #12 contracts. Preserved Rayan's network-delivered `command {cmd:"resume"}` reader/builder and plan storage unchanged; director overload/resume wiring remains a separate next task.
- **Heads-up for others:** PR #12 contains latest main plus our existing backend contracts. Imported robot/ML files and teammate histories are upstream changes, not edits to their policies. Detector integration/decoys have not been added; fallback tests do not validate real inference.
- **Next:** push this branch to update PR #12 and verify GitHub reports no merge conflicts; then proceed with the separately tracked backend controls.

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
