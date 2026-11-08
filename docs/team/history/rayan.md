# Rayan Diya: robots + ML

Owns `server/deadzone/robot/`, `ml/`, `data/floorplans/`. Only Rayan's sessions edit this file.

## Now
- **Working on:** `rayan/route-recompute`: after Aziz's aftershock (PR #42), recompute a survivor's rescue route when new rubble blocks it and resend it as a priority-1 bundle. Then the judge-picked building generator (Q&A only). **Later, only when Rayan asks (before the presentation):** refine the benchmark with more realistic data (published radio wall losses, sensitivity sweep over radio settings, random rubble). **Later, low priority (Rayan said not now):** speed up my robot planner (vectorize the frontier search) so the sim reaches 10x during exploration.
- **Works on main:** frontier exploration, 3-robot target sharing, relay auto-drop, A* return home, lost-link + 10 s reconnect hold, REPLANNING around rubble, rate monotonic scheduler with carry-over and deadline misses, full fault FSM (OVERCURRENT, STUCK, SAFE_STOP, LOW_BATTERY, TRAPPED), SAFE_STOP resume command (PR #13), robots follow dispatched plans (PR #15), robots perceive through the trained detector with decoys in the floor plan (PR #14 + #17). Seed 7, 3 robots: S1 found dark at 182.3 s, on Command at 187.3 s, 4 relays.
- **In flight (not merged):** `rayan/route-recompute`. On main: soak test + PR #28 review (PR #53), benchmark labeled "in simulation" (PR #48), Grad-CAM heatmaps + crop manifest (PR #49), baseline mode + benchmark (PR #41), no attribution setting (PR #43), demo guard (PR #36), Version 2 plan (PR #34), pitch assets (PR #33), demo polish (PR #29), beacon_for tag (PR #32), rescue route + beacon (PR #25), `docs/DEMO.md`, detector hookup + decoys (PR #17).
- **Blocked on / need from others:** **Yusuf: an updated rescue route for the same survivor (a second `rescue_route_reported` with a newer `t`) must replace the old route on screen, never show as a second route** (coming with my aftershock route update). Yusuf: baseline key + "Baseline" chip + `WAITING_FOR_LINK: 'No link, waiting'` label (Aziz's control is done in PR #54: `{action: "mode", value: "baseline" | "deadzone"}`, `mode` echoed in hello/control). Rayan (testing laptop): Gemini key + the keyed G / Ask dry run, report whether both say `source: "gemini"` (Aziz's PR #54). Aziz: quiet P-1 preload (demo-polish entry; or Yusuf), Gemini briefing (pitch-assets entry). Done by Aziz: `/crops`, `hello.detector`, `command.routes` (PR #28). Yusuf (all agreed, 3 AM): survivor figures, bigger robots, phone robot tap, liquid glass, rescue route drawing from `command.routes`, robot's-eye view (his). Done on main: decoys in thermal + none in fallback, O / U resume, detection cards, detector chip (waits for `hello.detector`). Details in the Blocked sections below; owners/targets in `docs/PLAN.md` Added scope. Keep `PEER_FRESH_S` in robot.py (sim.py imports it).
- **Promises to others:** states final: DEPLOYING, EXPLORING, LOST_LINK_EXPLORING, RETURNING_TO_SIGNAL, RETURNING_HOME, REPLANNING, FAULT, DONE, plus WAITING_FOR_LINK (baseline mode only). Robot `mode`: deadzone (default) or baseline, `Robot.set_mode()`. Faults final: null, OVERCURRENT, STUCK, LOW_BATTERY, TRAPPED, SAFE_STOP. `tasks` slices as in PR #7, `missed` can now be true. Robot hooks: `inject_overcurrent(seconds=1.0)`, `inject_perception_overload(seconds=3.0, wcet_ms=400)`.

## Log

### 2026-11-08 03:00 · rayan/plan-sync-v2 · PLAN.md: realistic visual direction + AI showcase and scenario generator
- **Did:** committed Rayan's two new `docs/PLAN.md` sections: "Visual direction: realistic (8:30 PM update)" and "AI showcase and scenario generator (8:35 PM update)".
- **Contract changes:** none
- **Heads-up for others:** **Aziz, Yusuf: pull main and read both sections now.** Yusuf owns the realistic look; the simulation stays on the single ground floor the demo guard checks, so the multi-story building is visual only. My parts: the AI Lab export for key L, then the scenario generator; I'll post format questions in my next entries.
- **Next:** finish `rayan/route-recompute` (aftershock rescue route update), then `rayan/ai-lab`, then `rayan/scenario-gen`.

### 2026-11-08 02:15 · rayan/soak-review · Review of PR #28 + 20-minute soak test
- **Did:** (1) Reviewed Aziz's merged PR #28 against my robot contracts (findings below). (2) `server/tests/test_soak.py`, PLAN.md's `test_soak`, **opt-in** with `DZ_SOAK=1` (skipped in normal runs; `DZ_SOAK_MINUTES` shortens it). 3 robots, seed 7, 20 min of sim. Every tick it builds and JSON-encodes the hub's snapshot (maps every 5 ticks) while a scripted director keeps going: rubble ahead of a robot every 90 s, overcurrent every 120 s, perception overload every 150 s, a relay switched off and back on, and a baseline / deadzone toggle. Asserts no exceptions, RSS under 500 MB, and under 15 MB of growth after minute 16 (Command's dedupe table holds one 900 s bundle TTL). **Result on this laptop: passed, 1200 s of sim in 101 s wall, 4,622 events, RSS flat at 323 MB (torch included) from minute 1 to 20.**
- **Contract changes:** none
- **Review of PR #28 (Aziz), against my contracts:**
  1. **OK, rescue routes.** My `rescue_route` payload (`survivor, by, path, length_m, clearance_m, beacon, t`) parses through your aliases. I validated every route from the 20 benchmark layouts plus the demo layout against `RescueRoute`: **61 of 61 valid and delivered to Command**. The longest route (51.4 m, 99 points) compacts to 25 points, well under your 60-point cap.
  2. **Low, silent rejection.** A route that fails validation (or has `by != src`) makes `receive()` return False with no event or log, so a contract drift would just look like "the route never arrived". Suggestion: emit a `rescue_route_rejected {src, reason}` event or a warning log. Also, the collinear compaction uses exact float equality, so diagonal runs aren't compacted. That's fine in collapse_01 (25 points max), but a bigger generated building could pass 60. I'll keep my routes at 60 points or fewer on my side when I build the building generator, so nothing is needed from you for that.
  3. **OK, beacons.** `drop_relay(beacon_for=...)` refuses while linked (returns None) and validates the id; my robot treats None as "no beacon" and spends no relay. Command relays carry `beacon_for`.
  4. **OK, survivor fields.** `survivor_found` / `hotspot_rejected` untouched. Command copies the whole survivor payload, so `crop`, `conf` (and `heatmap` from my PR #49) arrive with the bundle and never earlier.
  5. **OK, detector modes.** `hello.detector` comes from the same `get_detector()` singleton the robots use, so the chip always matches what robots run (`detector_reason` only in sim mode).
  6. **OK, and needed next.** Command keeps a route only when its `t` is newer and emits `rescue_route_reported` again. That's exactly what my upcoming "recompute the route after an aftershock" needs. **Yusuf:** a second `rescue_route_reported` for the same survivor means "replace the drawn route", not "add one".
- **Heads-up for others:** **speed (my code, not Aziz's):** while the robots are exploring (first ~4 min), one sim tick with 3 robots costs ~15 ms on this laptop, so the sim tops out around 5 to 7x real time even if the speed key says 10x. Later it is faster (average 11.9x over the soak). The cost is my robot planner (frontier search ~55%, A* ~20%), not the network or the messages (snapshot + JSON 0.5 ms). Rayan decided: not now, it's a low-priority later item.
- **Coordination with Aziz's PR #54 (one soak test, not two):** Aziz imported this exact `server/tests/test_soak.py` unchanged (same file, blob ec16654), so main has **one** soak test and this PR's copy is identical. His `scripts/soak.py` is not a second test: it's a paced runner that drives the real Hub at speed 10 and records evidence in `docs/validation/`. Use `test_soak.py` (opt-in, `DZ_SOAK=1`) as the pass/fail check and `scripts/soak.py` for paced measurements. His paced run (7.65x at speed 10) confirms the planner speed note above. He also added logging for rejected rescue routes (my review item 2) and the live baseline control. Aziz: if you change the soak, edit `test_soak.py` in place rather than adding another test.
- **Next:** rescue route recompute after Aziz's PR #42 merges.

### 2026-11-08 01:30 · rayan/gradcam · Grad-CAM "where the AI looked" + crop manifest
- **Did:** `py ml/gradcam.py` computes Grad-CAM (person class, layer `features[8]`, 6 x 6 upsampled to 192 px) with the robot's own detector for every runtime crop and writes, in `ml/crops/runtime/` (already served at `/crops`): `heatmaps/<name>.png` (crop with the heatmap blended on, ready for the AI card), `heatmaps/<name>_alpha.png` (RGBA heatmap only, transparent where the model didn't look, for overlays and 3D textures) and `manifest.json`. On S1 to S3 the heat sits on the people; on the radiator, engine and coffee machine it is spread out. Robot events now carry the heatmap path. 5 new tests; full suite green in both detector modes.
- **Contract changes:** additive only. `survivor_found` and `hotspot_rejected` events gain `heatmap` (path relative to `/crops`, e.g. `"heatmaps/pos_0001.png"`, or null in `DETECTOR=sim` fallback). The `survivor` bundle payload carries it too, so `command.survivors[]` records have `heatmap` when they arrive (Command only knows it once the bundle is delivered).
- **Heads-up for others:** **Yusuf, this is for you:**
  - `/crops/manifest.json` lists every crop: `{id, file, heatmap, heatmap_alpha, label, conf, predicted, role, object, pos}`. `id` is the floor plan id (S1..S3, D1..D3), `label` is the ground truth ("person" / "not person"), `conf` is the model's P(person), the same number as `survivor_found.conf`, `role` is survivor / decoy, `object` is the decoy stand-in name, `pos` is where it sits (m). All paths are relative to `/crops`.
  - AI card overlay: show `/crops/<heatmap>` (pre-blended), or layer `/crops/<heatmap_alpha>` over the crop yourself (a toggle "where the AI looked" works well).
  - In-world thermal look: `file` for the survivor / decoy texture, `heatmap_alpha` as an optional second layer. The images are 96 px crops and 192 px heatmaps.
  - You decide how it looks; nothing here touches web/.
- **Next:** aftershock robot reactions once Aziz posts the aftershock contract.

### 2026-11-08 00:50 · rayan/bench-sim-label · Benchmark numbers labeled "in simulation"
- **Did:** every benchmark number is now marked as a simulation result, never a real-world one. `docs/assets/benchmark.md`: "(in simulation)" in the title, every section and every table, plus a note at the top that the radio wall losses and link thresholds are chosen model values, not measurements. `docs/assets/benchmark.png`: title starts "In simulation:" and a footnote says "Simulation only, not a real-world result". `docs/DEVPOST.md`: new section "Does it actually help? (in simulation)" with the 60/60 vs 39/60 and 90% vs 70% results and the same caveat; the wall-loss numbers are marked as model values. `ml/benchmark.py` writes the labels, so a rerun keeps them (re-rendered from the saved JSON, numbers unchanged).
- **Contract changes:** none
- **Heads-up for others:** **Aziz, Yusuf: if you put any benchmark number on a slide, the board or in the Devpost, say "in simulation" next to it.** The radio numbers are ours, not measured.
- **Later (only when Rayan asks, before the presentation):** refine the benchmark with more realistic data: radio wall losses from published measurements, a sensitivity sweep over the radio settings, random rubble. Not started.
- **Next:** `rayan/gradcam`.

### 2026-11-08 00:25 · rayan/no-attribution · Claude Code attribution off for the repo
- **Did:** `.claude/settings.json` now has `"attribution": {"commit": "", "pr": "", "sessionUrl": false}` (the current setting from the Claude Code settings docs; the deprecated `includeCoAuthoredBy` is not used). Claude Code sessions in this repo no longer add a `Co-Authored-By` trailer to commits, an attribution line to PR descriptions, or a session link. The existing hooks (team_sync, history_guard) are untouched. I used the object form rather than `"attribution": false` because older Claude Code versions reject `false` and skip the whole settings file, which would also switch off our hooks.
- **Contract changes:** none
- **Heads-up for others:** **Aziz, Yusuf: this is shared tooling and it's on for your sessions too** once you pull main (project settings apply to every Claude Code session in the repo). If you want attribution back just for yourself, set `attribution` in your own `.claude/settings.local.json`.
- **Next:** `rayan/gradcam` after PR #41.

### 2026-11-08 00:10 · rayan/baseline · "Without Deadzone" baseline mode + 20-seed benchmark
- **Did:** robots have a `mode`: `deadzone` (default, demo unchanged, demo guard green) or `baseline` = "without Deadzone": same mapping and planning, but the robot **stops and waits as soon as its link drops** (new state `WAITING_FOR_LINK`, like a tethered or teleoperated robot) and carries **no relays**. Start in baseline with `DZ_MODE=baseline`; switch live with `robot.set_mode("baseline" | "deadzone")` (a waiting robot switched back resumes normal Deadzone behavior). `py ml/benchmark.py` runs 20 survivor layouts (the 3 survivors moved to random reachable spots per seed) plus the demo layout, 3 robots, 360 s, both modes, in ~4 min on 14 cores, and writes `docs/assets/benchmark.md`, `benchmark.png` (slide chart) and `benchmark.json`. Results: **survivors reported to Command 60/60 vs 39/60**, **building mapped on Command 90% vs 70%**, relays 4.2 vs 0 per run, 3.0 robots per run stuck waiting in baseline. Demo layout: baseline never finds S1 or S2. 215 tests pass with the model; `DETECTOR=sim` 214 + the D1 skip.
- **Contract changes:** additive only. Reality robot telemetry gains `mode` ("deadzone" | "baseline"). New state `WAITING_FOR_LINK` (only in baseline mode). New robot events: `mode_changed {robot, mode}`, `waiting_for_link {robot}`.
- **Heads-up for others:** Rayan is skipping the Version 1 backup video from the PLAN.md guardrails. The benchmark chart (`docs/assets/benchmark.png`) is ready for a slide.
- **Blocked:** **Live baseline toggle for Q&A, so Rayan can switch all robots between Deadzone and baseline during the demo:**
  - **Aziz (app.py):** a screen control message, e.g. `{"type": "control", "action": "mode", "mode": "baseline" | "deadzone"}`, that calls `robot.set_mode(mode)` on every robot (raises ValueError on anything else) and echoes it like the other controls. Optional: `DZ_MODE` already works at startup without you, since each Robot reads it.
  - **Yusuf (web):** a key for it (B is free I think, your call) that toggles the mode, a visible "Baseline" chip on the board while it's on, and a label in `web/src/format.js` `STATE_LABEL`: `WAITING_FOR_LINK: 'No link, waiting'`. `mode` is in each Reality robot's telemetry.
- **Next:** `rayan/gradcam`.

### 2026-11-07 23:20 · rayan/demo-guard · DEMO.md is now a pytest
- **Did:** `server/tests/test_demo_guard.py` replays the DEMO.md demo headless: seed 7, 3 robots, P-1 rejected (R2 / ZNE / comms_plan) then fixed to lost_link_ok and dispatched, director presses R at 150 s (rubble ahead of R1), F at 165 s (overcurrent R3), O at 175 s (overload R1). It asserts every beat within **0.25 s** (2 ticks): S3 found linked 14.4 s and reported at once, D1 rejected by the model 56.7 s, RL1 by R3 57.1 s, R2 dark 119.1 s, S1 found dark 129.0 s with a beacon and a 45-55 m route, S1 + `rescue_route_reported` on Command 143.1 s (delay >= 10 s), R1 replan / R3 OVERCURRENT / R1 perception misses (no safety misses) inside their key windows, S2 bonus 246.0 s, no decoy ever reported. Runs in ~40 s. Mutation check: REPLAN_PAUSE_S 0.6 -> 0.7 moves RL1, S1_reported and S2 and the guard fails. Fixed DEMO.md S2 row (245.8 -> 246.0, lost before PR #29). 209 tests pass with the model; `DETECTOR=sim` 208 pass + the D1 beat skips (decoys are off in fallback).
- **Contract changes:** none
- **Heads-up for others:** **Aziz, Yusuf: if your PR fails `test_demo_guard`, it moved a demo beat.** Either fix it, or if the move is intended, re-measure and update the `BEATS` table in the test **and** `docs/DEMO.md` together in the same PR, and say so in your file. Web-only changes can't affect it.
- **Next:** `rayan/baseline`.

### 2026-11-07 23:00 · rayan/plan-v2 · Version 2 plan committed to PLAN.md
- **Did:** committed Rayan's "Version 2 plan (7 PM Saturday)" section in `docs/PLAN.md`: guardrails (demo guard test first, every new feature behind a toggle or key until a dry run passes, 7:30 AM freeze), the UX fixes (one main 3D view with the Command gap drawn on it, collapsed task timeline, less clutter, AI crops visible in the world), and the owners and priorities table with the cut order.
- **Contract changes:** none
- **Heads-up for others:** **Aziz and Yusuf: please read the Version 2 section of `docs/PLAN.md` now.** **Yusuf owns the 3D design and decides how it looks**; the table only says what each person delivers so the pieces fit. Your priority-1 items: Yusuf, the 3D realism pass and the one-view redesign; Aziz, the real Gemini briefing (G) with tool calls over Command data, plus the phone "Ask Gemini" box with Yusuf. What I deliver for you: the demo guard (any PR that moves a beat fails it), a crop manifest plus Grad-CAM heatmaps for the in-world thermal look and the AI card overlay (Yusuf), and robot reactions to the aftershock once Aziz posts the aftershock contract (Aziz, please put it in your file).
- **Next:** `rayan/demo-guard`.

### 2026-11-07 22:40 · rayan/pitch-assets · ML slide assets, README, Devpost draft
- **Did:** `docs/assets/`: `confusion_matrix.png` (unchanged from ml/results), `pipeline.png` (thermal camera → 96×96 crop → MobileNetV3-Small 6 MB onboard → person or not), `crops_grid.png` (4 person + 4 rejected warm-object crops from the held-out FLIR val split, scored by the real model; none of the picked crops needed skipping), `stats_card.png` (96.2 / 96.3 / 96.0%, 1,200 held-out images). Rebuild with `py ml/make_slide_assets.py`. Rewrote `README.md` (what it is, demo story, how to run, keys, team) and drafted `docs/DEVPOST.md` from the PLAN.md outline with real numbers (S1 14.1 s late, 49.7 m route, 0.377 utilization, confusion matrix). Gemini and Reed-Solomon are only claimed if they ship (notes at the top of DEVPOST.md). DEMO.md now covers Yusuf's browser record/replay (`?record`, S, `/?replay`) in pre-flight, keys and recovery.
- **Contract changes:** none
- **Heads-up for others:** everyone: skim `README.md` and `docs/DEVPOST.md` and fix anything about your part (your names in the Team section too).
- **Blocked:** **Aziz, two offers, only if you want them (say yes or no in your file, I won't touch your folders otherwise):**
  1. I review PR #28 (already merged) against my robot contracts: `rescue_route` payload, beacon tagging, `survivor_found` / `hotspot_rejected` fields, detector modes.
  2. I write the 20-minute soak test (`test_soak` from PLAN.md: 20 min sim time, 3 robots, no exceptions, memory under 500 MB) in `server/tests/`.
  - **Please move the Gemini briefing up your list.** It's the only thing standing between us and the **MLH Best Use of Gemini API** prize, which is in our target list. Right now G shows a local summary, so the Devpost can't claim Gemini yet. The plan in PLAN.md (read-only tool calls over the Command view, 10 s timeout, local fallback) is already the right shape.
- **Next:** pitch rehearsal fixes only.

### 2026-11-07 22:05 · rayan/beacon-tag · Survivor beacons are tagged with beacon_for
- **Did:** the survivor beacon now calls `io.drop_relay(beacon_for=rec["id"])` (Aziz's PR #28 API), so its `relay_dropped` event and relay record carry `beacon_for`. A refused tagged drop (robot linked) returns None and costs no relay. Seed 7 demo re-run: RL2 at (35.1, 23.6) has `beacon_for: "S1"`; all DEMO.md beats unchanged (S1 dark 129.0 s → Command 143.1 s, S2 246.0 s). 200 tests pass (model and `DETECTOR=sim`).
- **Contract changes:** none new from my side. Reminder for Yusuf: the Command-side arrival event is Aziz's **`rescue_route_reported`** (with `delay_s`); the robot's `rescue_route` event is Reality only.
- **Heads-up for others:** Aziz: done, the call site you asked for.
- **Next:** pitch assets (ML slide images, README, DEVPOST draft).

### 2026-11-07 21:15 · rayan/demo-polish · Fixes from the testing laptop's dry run
- **Did:** (1) DEMO.md PowerShell fallbacks use `127.0.0.1` (Windows `localhost` hangs ~2 s on IPv6), plus a note that R / F / O must land on time or the S2 bonus slips past the close. (2) No more REPLANNING / EXPLORING flip-flop at rubble corners (R3 near (30.2, 26.8)): an obstacle seen again within 5 s of a replan is replanned silently in place; only if that fails does the robot stop and show REPLANNING. (3) A robot that sees an already-reported survivor in the dark (peer's `found` list) keeps exploring instead of returning to signal (R1 / R3 for S1). Seed 7 demo re-run: every beat through S1 unchanged (S1 dark 129.0 s → Command 143.1 s); RL1 57.7 → 57.1 s; S2 bonus moves to 245.8 s (+2:03, clock 2:43, R2 finds it now). DEMO.md updated. 167 tests pass (model and `DETECTOR=sim`).
- **Contract changes:** none. Fewer `replan` events (repeat obstacles within 5 s no longer raise one).
- **Heads-up for others:** the S2 bonus now lands at 2:43; skip it if R / F / O were late.
- **Blocked:** **Aziz (or Yusuf):** preloading P-1 before the demo (`POST /api/plan`) runs the safety check, so phones already get the rejection card and the big screen feed shows a `safety_reject` before the judges tap anything, which spoils the 0:15 beat. Please keep the preload quiet. Suggested (Aziz): `POST /api/plan?check=false` saves and broadcasts `plan_state` only, with no `safety` message to phones and no `safety_reject` event; the judge's "Run safety check" (`plan_submit`) then produces the first rejection. Frontend fallback (Yusuf): clear the feed and the phone's safety card when `plan_state` changes or on Space. Either is fine; say which one you take in your file and I'll update DEMO.md.
- **Next:** robot area is feature complete; rehearsal fixes only.

### 2026-11-07 20:30 · rayan/rescue-route · Rescue route + beacon relay
- **Did:** when a robot confirms a survivor (first confirmation only; robots skip survivors a peer already reported, via the `found` list in peer telemetry) it computes the safest A* route **from the entrance to the survivor on its own map**: known free cells only, never through rubble, walls, unknown space or no-go areas, centered by the wall cost, with a cost band 1 m around hazards. It sends the route to CMD as a **priority-1 bundle**, so Command only knows it when it arrives. If the survivor is in a **dead zone** (robot has no link) and the robot still has a relay, it also drops a **beacon relay** next to them; where there is coverage no beacon is needed (Rayan's call: beacons in covered areas reshaped the relay network and removed the S1 dark moment). Seed 7 demo plan: S3 route 14.2 m at 14.4 s (instant); S1 found dark at 129.0 s, beacon RL2 in the cage, 49.7 m route delivered to CMD at 143.1 s with the survivor report; every DEMO.md beat unchanged. 150 tests pass (model and `DETECTOR=sim`).
- **Contract changes:**
  - Robot event (Reality knowledge, at computation): `rescue_route {robot, survivor, path:[[x,y],...], length_m, clearance_m, beacon}`. `path` starts at the entrance `[1.0, 15.0]` and ends at the survivor position; `beacon` is the relay id (e.g. `"RL2"`) or null.
  - Bundle to CMD: `kind:"rescue_route"`, `prio:1`, payload `{survivor, by, path, length_m, clearance_m, beacon, t}`. Delivery raises the existing `bundle_delivered` event with `bundle_kind:"rescue_route"`.
  - The beacon is a normal relay: it raises the usual `relay_dropped` event and shows in `reality.relays`.
- **Heads-up for others:** Yusuf: draw routes on **Command only from delivered data** (Aziz's `command.routes`, below), never from the robot's `rescue_route` event, which is Reality knowledge. The Reality pane may draw from the event. Phones get routes through `cmd_view` once Aziz adds them.
- **Blocked:**
  - **Aziz:**
    1. `network/dtn.py`: add `"rescue_route": 1` to `PRIO`. Robots already send the bundle with `prio:1` (built from a known kind until then), so nothing breaks today.
    2. `command/post.py`: on a delivered `rescue_route` bundle, keep one route per survivor (newest `t` wins) and expose it in the Command view as `routes: [{survivor, by, path, length_m, clearance_m, beacon, reported_t}]` (also in phone `cmd_view`). Raise event `rescue_route_reported {survivor, by, length_m, delay_s}`.
  - **Yusuf:** draw `command.routes[]` on the Command pane: a bright dashed line from the entrance to the survivor with "Route to S1 · 49.7 m" at the survivor end, and the beacon relay highlighted when `beacon` is set. Same on the phone map from `cmd_view.routes`.
- **Next:** ML slide for the freeze. (Yusuf took all five asks incl. the robot's-eye view; Aziz's O / resume / decoys are on main and DEMO.md now lists O and U as live. Re-checked on merged main with native decoys: all beats unchanged.)

### 2026-11-07 19:50 · rayan/scope-sync · Added scope (5:45 PM) in docs/PLAN.md
- **Did:** committed Rayan's updated `docs/PLAN.md`, which has a new **"Added scope (5:45 PM Saturday)"** table: owners and target times for the AI detection card, detector chip, decoy safety, rescue route + beacon, survivor figures, robot's-eye view, liquid glass, ML slide. Also final states/faults/tasks/relay_dropped wording and names in the roles table.
- **Contract changes:** none in this commit (rescue route contract comes with `rayan/rescue-route`).
- **Heads-up for others:** **Aziz and Yusuf: the Added scope table in `docs/PLAN.md` is the source for owners and targets (10 PM / 3 AM).** Aziz's six asks are already in my earlier entries (detector-hookup, safe-stop-resume and detection-events entries): `/crops/<file>` static, `hello.detector`, no decoys in sim fallback, decoys from `RobotIO.thermal()` with survivor rules, O → `inject_perception_overload`, resume director action.
- **Blocked:** **Yusuf**, new asks on top of the chip / survivor figure / detection cards already posted. Please tell me in your history file which of these you can fit:
  1. Robots bigger and brighter so they read from across the room (both panes).
  2. Robot's-eye picture-in-picture: click a robot → small view from its camera (pose + heading from Reality telemetry `pose`), with a **Thermal** toggle (walls cold blue; survivors and decoys glow). Render small and only while open; cut first if time is short. **My session can build this in `web/` if you OK it** (say so in your file and name the component path you want).
  3. Phone: tap a robot card to see its status and last thermal crop. Phones only see Command, so use the delivered survivor records: `cmd_view.survivors[].crop` (and `by` for the robot), image `/crops/<crop>`.
  4. Liquid-glass styling (frosted translucent panels, cards, phone UI).
  5. Draw the rescue route on the **Command** view when it arrives. Contract coming from my next PR (`rayan/rescue-route`); I'll post it here.
- **Next:** rescue route + beacon relay.

### 2026-11-07 19:40 · rayan/demo-runbook · DEMO.md updated for M4 keys
- **Did:** runbook key table and beats follow Yusuf's M4: 1–3 / 0 follow cams, R and F act on the followed robot, F and G are live keys. Beats now say which robot to follow before R / F / O.
- **Contract changes:** none
- **Heads-up for others:** none
- **Next:** scope sync PR, then rescue route.

### 2026-11-07 19:20 · rayan/demo-runbook · docs/DEMO.md demo runbook
- **Did:** wrote `docs/DEMO.md`: seed 7, 3 robots, 2x, plan P-1 (R1 west offices, **R2 north-east + steel cage as the dark zone**, R3 break room) preloaded, judges fix it on the phone ("Allow ZNE to go dark") and dispatch before Space. Beat sheet measured headless on merged main with the model live: S3 at +0:07, radiator rejected +0:28, RL1 +0:29, R2 dark +0:59.5, **S1 found dark +1:04.5, on Command +1:11.5 (14.1 s late)**, then R / F / O / G beats, all rehearsed in the dry run. Every director key with status, lines to say per beat, PowerShell plan / fault / report fallbacks, recovery table, judge answers. Also: `_read_commands` now learns peer telemetry if `io.radio.receive()` hands any over (PR #12 drains `robot.inbox` too), so peers can't be lost if the read order changes. 146 tests pass with the model and with `DETECTOR=sim`.
- **Contract changes:** none
- **Heads-up for others:** everyone: read `docs/DEMO.md` before the first rehearsal; the beat times assume P-1 with ZNE dark-OK dispatched before Space. Yusuf: F / G / O keys (M4) are the only missing keys in the runbook. Aziz: O (overload) and resume director values are still open (see the safe-stop-resume entry).
- **Next:** task 6 director pieces when O / resume / decoys land; rehearsal fixes.

### 2026-11-07 18:55 · rayan/demo-runbook · Detection events carry the crop and confidence
- **Did:** `survivor_found` events now carry the thermal crop file the detector scored and its confidence. New `hotspot_rejected` event when the detector turns a hot spot down (once per robot per hot spot). Survivor records (and so the Command view after delivery) carry `crop`. 115 tests pass with the model and with `DETECTOR=sim`.
- **Contract changes:**
  - `survivor_found` gains `crop` (file name, e.g. `"pos_0001.png"`) and `conf` (0 to 1, model probability; 0.99 in sim fallback).
  - New event `hotspot_rejected {robot, id, pos:[x,y], crop:"neg_0001.png", conf}` (conf below 0.6). The robot doesn't know it's a decoy, only "hot but not a person"; `id` is the hot spot id (D1 to D3).
  - Command `survivors[]` records gain `crop`.
- **Heads-up for others:** none beyond the asks below.
- **Blocked:**
  - **Aziz:**
    1. Put detector status in `hello` (screen and phone): `"detector": "model"` or `"sim"`, from `deadzone.robot.perception.get_detector().mode`; optional `"detector_reason"` from `.reason` when in sim.
    2. When `get_detector().mode == "sim"`, `RobotIO.thermal()` must **not** emit decoys (my earlier decoy ask, plus this guard). A missing PyTorch must never put a radiator on screen as a survivor.
    3. Serve `ml/crops/runtime/` as static files at **`/crops/<file>`** (e.g. `/crops/pos_0001.png`) so the big screen can show what the detector saw.
  - **Yusuf:**
    1. Top-bar chip from `hello.detector`: `"model"` → "Detector: AI model", `"sim"` → "Detector: sim fallback" (warning colour).
    2. Replace the survivor dot with a low-poly person lying down with a warm thermal glow; keep the pulsing ring. Reality and Command both.
    3. On `survivor_found`, a small card on the **Reality** pane: thermal image from `/crops/<event.crop>`, "person, 100%" from `event.conf`, robot `event.robot`, survivor `event.survivor`, and "no link, holding report" when `event.linked` is false.
    4. On `hotspot_rejected`, the same card style: image `/crops/<event.crop>`, "not a person, 0%" from `event.conf`, robot `event.robot`. Reality only, never Command.
    5. Command side can show the crop after delivery from `command.survivors[].crop`.
- **Next:** `docs/DEMO.md` runbook.

### 2026-11-07 18:15 · rayan/detector-hookup · Trained detector live in robot perception, decoys in the floor plan
- **Did:** robots now run every thermal hot spot through the trained detector (`filter_hits(io.thermal())`, PR #14's module); found survivors carry the model's probability as `conf`. Sim sensor fallback when `DETECTOR=sim`, no torch or no model. Added 3 decoys to collapse_01.json. Seed 7, 3 robots, model live (decoys injected into thermal by a test harness the way Aziz's change will): S1 dark at 182.3 s by R1 (conf 1.0) → Command 187.3 s, S2 225.1 s (0.889), S3 18.0 s (0.999); decoys in view D1 69 / D2 332 / D3 10 ticks, none reported. 115 tests pass with the model and with `DETECTOR=sim`.
- **Contract changes:** **floorplan** gains `"decoys": [{"id","label","pos","thermal"}]`: D1 radiator (15, 28) `neg_0001.png`, D2 engine (37, 12) `neg_0002.png`, D3 coffee machine (22, 28) `neg_0003.png`. Survivor `conf` is now the model probability (was always 0.99).
- **Heads-up for others:** whoever runs the demo laptop: install CPU torch or the model is not used and decoys (once Aziz's change lands) show up as survivors: `py -m pip install torch torchvision pillow --index-url https://download.pytorch.org/whl/cpu` (pillow from PyPI if the index lacks it). The server log says `survivor detector: sim sensor fallback (...)` when it isn't loaded. Yusuf: optional faint decoy markers on Reality only (never Command), labelled from `decoys[].label`.
- **Blocked:** Aziz, please make `RobotIO.thermal()` in `sim.py` also return decoys from `fp.data["decoys"]`, with exactly the survivor rule and shape: within `THERMAL_RANGE`, inside `THERMAL_FOV`, `line_of_sight`, hit `{"id": d["id"], "pos": (x, y), "crop": d["thermal"], "conf": 0.99}`. The robot's detector rejects them; no flag telling the robot it's a decoy (that would be cheating). Safe to merge any time after this PR is on main.
- **Next:** task 6 director pieces once Aziz wires O / resume / decoys.

### 2026-11-07 17:40 · rayan/plans · Robots follow dispatched plans
- **Did:** a `plan` bundle from CMD (Aziz's `/api/dispatch`, read with `io.radio.receive()`) now drives the robot. While reachable frontiers touch its zone (priority 1 first) it picks only among them; before the zone is on its map it is pulled toward it; once 80% of the zone is mapped it helps anywhere. The plan's `no_go` polygons join the robot's no-go mask (never planned through; a newer plan replaces them). `lost_link_budget_s` replaces the 45 s default. No relay drops inside a `lost_link_ok` zone. Seed 7: Office B zone reached at 21 s instead of 97 s. Demo-style plan (R2 east wing `lost_link_ok`): R2 finds S1 dark at 180.9 s, on Command at 186.0 s.
- **Contract changes:** new event `plan_applied {robot, plan_id, zones:[ids]}` raised when the robot actually starts following a plan. Telemetry gains `plan_id` (or null) and `zone` (active zone id or null).
- **Heads-up for others:** Yusuf: show "following P-7 / zone Z1" from `plan_id`/`zone`, and only after `plan_applied` (a dispatch is not proof the robot got it). Aziz: nothing needed; dispatch already works end to end. Demo plan tip: give the robot that should go dark a `lost_link_ok` zone over the east wing, otherwise relays may light it up.
- **Next:** detector hookup (after the ML PR merges), then task 6 decoys.

### 2026-11-07 17:10 · rayan/safe-stop-resume · SAFE_STOP can be resumed from CMD
- **Did:** robots now read `io.radio.receive()` every step. A `command` bundle with payload `{"cmd": "resume"}` clears SAFE_STOP and the fault counter, raises a `resumed` event, then the robot replans and carries on. Plan bundles that arrive are stored on the robot (acted on in `rayan/plans`). The resume only reaches a robot that has a route to CMD; a robot that safe-stopped in a dead zone stays stopped until a relay reaches it (realistic, by design).
- **Contract changes:** new command bundle `kind:"command"`, `src:"CMD"`, `dst:<robot id>`, `payload:{"cmd":"resume"}` (builder `deadzone.robot.robot.resume_command(rid, now)`). New event `resumed {robot}`.
- **Heads-up for others:** Yusuf: optional toast for the `resumed` event.
- **Blocked:** Aziz, please wire two director values in `app.py` (nothing else needed from my side):
  1. Key **O** → `control {action:"director", value:{do:"overload", robot:"R1"}}` → `sim.robots[robot].inject_perception_overload()`. The scheduler overload moment: perception misses deadlines for 3 s, safety never does.
  2. `{do:"resume", robot:"R1"}` → `sim.network.queues["CMD"].append(resume_command(robot, sim.time))` with `from .robot.robot import resume_command`. Must go through the CMD queue, never straight into the robot, so it obeys the network like every other bundle.
- **Next:** robots follow dispatched plans.

### 2026-11-07 16:56 · rayan/scheduler-faults · PR #8 Scheduler overload and full fault FSM
- **Did:** scheduler carries unfinished jobs across frames, flags slices past their deadline `missed: true`, skips a release while the previous job overruns. `inject_perception_overload()` makes perception cost 400 ms for 3 s: about 1 perception deadline miss per second, safety never misses (still runs at 0 and 50 ms). Fault FSM: OVERCURRENT and STUCK stop, back up 0.5 m, mark ahead, REPLANNING; 3rd motion fault within 60 s gives SAFE_STOP (state FAULT, wheels off); LOW_BATTERY label while heading home; every fault sends a priority-1 `fault` bundle `{robot, fault, pos, t, state}` to CMD.
- **Contract changes:** new event `deadline_miss {robot, task}`. `fault` events now cover all 5 values. `tasks[].missed` can be true. New robot hook `inject_perception_overload(seconds=3.0, wcet_ms=400)`.
- **Heads-up for others:** Aziz: please wire a director key for `sim.robots[rid].inject_perception_overload()` (suggest O). Pressing F 3 times on one robot within 60 s puts it in SAFE_STOP (until the resume command lands next). Yusuf: red `missed` slices and `deadline_miss` events now really happen. Yusuf: the `.claude` hooks call `python3` and match only the Bash tool; on Rayan's Windows laptop only `py` exists and commits go through PowerShell, so neither hook runs there (Rayan's Claude follows the rules by hand).
- **Next:** SAFE_STOP resume command, then robots follow dispatched plans.

### 2026-11-07 · rayan/timeline-contract · PR #7 Timeline contract (merged)
- **Did:** scheduler records per-robot task pieces. Overcurrent fault hook. Final state list.
- **Contract changes:** telemetry gains `tasks`: per robot, `[{name,start,dur,missed}]` over the last 100 ms (0 to 100), sorted, never overlapping. A preempted task appears as several pieces. Names: safety, motion, comms, mapping, perception, battery. Telemetry also gains `wheel_a` (wheel current, amps).
- **Heads-up for others:** Yusuf's timeline strip builds against this. It's on main now.
- **Next:** robots follow dispatched zones and no-go areas.

### 2026-11-07 · rayan/replan · PR #6 Lost link polish and visible replanning
- **Did:** `link_lost` / `link_restored` fire once per outage (`link_restored` carries `dark_s`). After reconnecting, a robot holds until its outbox drains (at most 10 s). The path check catches rubble near waypoints. New REPLANNING state: stop 0.6 s, replan, resume. No route for 10 s raises TRAPPED plus a priority-1 fault bundle.
- **Contract changes:** new state `REPLANNING`, new fault `TRAPPED`, `replan` events carry `reason`, `link_restored.dark_s`.
- **Heads-up for others:** the R key (drop rubble) now shows a visible replan.
- **Next:** timeline contract.

### 2026-11-07 · rayan/relays · PR #5 Relays, A* return home, shielded survivor cage
- **Did:** robots auto-drop relays when the best upstream link is between -81 and -76 dBm, at least 4 m from other relays, never in no-go areas. 2 per robot (about 4 in a 3-robot run). The return-home cost uses A* path length. Frontier clusters go down to 2 cells.
- **Contract changes:** `relays_left` in telemetry is real. `relay_dropped` event `{kind, id:"RL1", pos:[x,y], owner}`. **Floorplan:** S1 moved to (36, 27) inside metal room E2 "Steel Storage Cage", door at (38.8, 21).
- **Heads-up for others:** two of Aziz's tests moved off the old S1 spot (approved). Anything with S1 coordinates hardcoded must update.
- **Next:** replanning.

### 2026-11-07 · rayan/multi-robot · PR #3 Share frontier targets through telemetry
- **Did:** telemetry carries the robot's target. Robots avoid frontiers within 4 m of a higher-priority robot's claim (R1 > R2 > R3). Deploy is staggered 1.5 s.
- **Contract changes:** telemetry `target` field.
- **Heads-up for others:** TEMPORARY shim in `sim.py` copies telemetry into peer inboxes. Aziz replaces it with DTN-delivered peer bundles.
- **Next:** relays.

### 2026-11-07 · main · Starter + PLAN.md
- **Did:** sim server, robot exploration, 3D split view starter, `docs/PLAN.md` (idea, roles, setup, git workflow), CLAUDE.md.
- **Contract changes:** initial message shapes in `docs/PLAN.md`.
- **Heads-up for others:** none
- **Next:** multi-robot.
