# Aziz: backend + network (Person 2)

Owns `server/deadzone/sim.py`, `app.py`, `floorplan.py`, `network/`, `command/`. Only Aziz's sessions edit this file.

## Now

- **Working on:** item G release, p2/heat-sources; started after merged F main 5be7c8f and integrated main ee271d9 before PR. A #108, D #143 and F #152 prerequisites satisfied before G source work resumed. Uses the user's confirmed x/y and kind/type/source_id/temp_c schema, superseding the initial class wording.
- **Works on main:** A #108, B #126, delivered camera #115, compact sparse screen stream #137, preflight/private-env setup #143, RSSI coverage #146 and phone JPEG frames #152. F combined backend 651 passed / 1 skipped, web 69/build green. Current DEMO requires obstacles and smart/scripted rubble on, 1.5x; secondary collapse at 162.5 s, F/O keys at 177.5/187.5.
- **Coverage contract:** additive coverage object in maps and phone cmd_view only when enabled: {w,h,cell,encoding:"zlib-base64",dtype:"int8",unit:"dBm",predicted:true,sources,data}. Inflate to w*h row-major signed one-byte dBm samples at cell centers, nearest integer/ties-even, clipped [-128,127]. Command's sanitized prior and accepted delivered relay positions/on states only; strongest CMD/configured tx or relay/20 dBm prediction. Static known furniture follows DZ_OBSTACLES. No truth rubble/dynamic walls/live links/robot radios; no end-to-end connectivity guarantee. Compact map_patch preserves coverage as metadata. No renderer or per-tick/AI grid added. Full shape/semantics in PLAN.md.
- **In flight (not merged):** G release only, implementation complete. Shared survivor range/FOV/LOS; typed sources validate/compile only with DZ_HEAT_SOURCES=1 (default off). Stable SHA-256 seed:id:type negative crop stand-ins, no RNG consumption. Real model decides; unscored decoys stay unsure, never fallback rescues. Delivered camera telemetry preserves kind/type/source_id/temp_c; events use hit_kind, keeping event.kind valid. Combined main ee271d9 full backend 678 passed / 1 skipped (155.82 s), current seed-7 demo guard and 24 G cases included; all 73 web tests and production build pass. No G web renderer/data edits or protected-file changes.
- **Local key safety:** ignored server/.env preserved; backup names ignored except safe .env.example. Existing root/running-app files retain local current-user/SYSTEM-only ACLs. Never print or commit values. Preflight reports only set/missing; it leaves existing servers alone.
- **Blocked on / need from others:** none for G. Rayan owns the floor-plan source data/schema; G consumes the exact user-agreed heat_sources shape and documents its sensor/telemetry contract. Existing negative thermal crops are stand-ins, not generated temperature images or a new type classifier. Earlier provisional class/type stashes remain preserved and unused. Other queued asks stay separate. F's live browser visual check was unavailable because Computer Use could not verify the Windows URL; automated API/cache/capture checks passed.
- **Promises to others:** merge main immediately before opening and merge this PR before a new item. Run complete backend/demo guard; flag off has no new fields or prediction work. Never edit floorplan.py, command/plan.py, command/safety.py or teammate histories, and never stage server/.env. Existing running :8000 app remains undisturbed.

## Log

### 2026-11-08 PT - p2/heat-sources - Integrate current feed/rubble main before G PR
- **Did:** pre-PR sync merged main ee271d9 (#153 ML event feed, #154 robot-targeted rubble control, #155 collapse banner) cleanly. Read their histories and the new control contract. G's source diff is still its nine files; no web/data/protected-source work added.
- **Contract changes:** G unchanged; upstream rubble action/robot and banners remain as merged. AI event kind names stay unchanged by G, so the new feed filters continue to work with typed metadata.
- **Validation:** final combined main ee271d9 full backend 678 passed / 1 skipped (155.82 s), current seed-7 demo guard and all 24 G cases included. All 73 current frontend tests and production build pass. Before integration, G full backend was 675 passed / 1 skipped (152.08 s). No runtime source edits after final validation.
- **Heads-up for others:** test-station history reports a possible preflight false-free on port 5173; separate follow-up, not changed in G. Collision flag remains off for the current DEMO because the station measured S2 early when enabled. G's default remains off too.
- **Next:** finish combined validation, immediate latest-main merge, publish/merge G.

### 2026-11-08 PT - p2/heat-sources - G: typed heat-source observations through the real sensor and DTN
- **Did:** confirmed F #152 merged, fast-forwarded G to main 5be7c8f, then implemented only G with the exact user-confirmed schema. Sources use shared survivor visibility checks and stable seed/id/type negative runtime crop stand-ins, without RNG consumption. Actual detector scores determine verdicts; missing scores keep decoys unsure rather than inventing a survivor. Robot changes only preserve sampled IO metadata and its actual classification; no truth access from robot/Command code.
- **Contract changes:** DZ_HEAT_SOURCES=1 at Sim/Robot/CommandPost construction/reset, off by default. Source shape heat_sources:[{id,type,x,y,temp_c,size_m}], types generator|space_heater|hot_pipe|server_rack|dog|laptop|sunlit. Thermal hits add kind:"survivor" for survivors and kind:"decoy",type,source_id,temp_c for heat sources. Missing kind defaults survivor. Existing camera telemetry is enabled by this flag itself, retains metadata after DTN delivery, and accounts for metadata bytes. Reality/Command camera hits preserve fields; AI events use hit_kind plus source fields without overwriting event.kind. A true model false positive retains source kind in its report. Flag off preserves old sensor/telemetry/event shapes and ignores even invalid optional sources. PLAN.md documents the contract/stand-in limits. No frontend renderer added.
- **Validation:** full backend 675 passed / 1 skipped (152.08 s), current seed-7 demo guard and all 24 G cases included. Actual model rejection of all seven source exemplars, real phone WebSocket metadata, sensor range/FOV/wall occlusion parity, seed/order/reset/RNG determinism, real DTN loss/reconnect, dark frame age, fallback/false-positive honesty, schema validation and default-off compatibility covered. All 69 web tests pass. Protected floorplan.py/command plan/safety and actual .env untouched.
- **Heads-up for others:** A/D/F ordering is satisfied; initial class-based G prototype was never merged or reused. Rayan supplies source entries; source list is not in the phone prior/hello. Crops are existing representative negatives, not physical thermal renders or retraining. User's kind schema takes precedence over earlier class wording.
- **Next:** full backend/guard, immediate main merge, publish and merge the single G PR.

### 2026-11-08 PT - p2/phone-frames - Integrate scripted-collapse and solid-prop main before F PR
- **Did:** pre-PR fetch merged main 3236195 (#149 ML robot cards, #150 Rayan smart/scripted rubble, #151 Yusuf solid props). Resolved only RobotEye's adjacent import conflict by retaining decoyLayout and F's uploader. No teammate behavior rewritten; F's PR diff remains limited to its 15 feature/docs/test files.
- **Contract changes:** F unchanged. Rayan's rubble_fall cause/robot and rubble control smart result are his upstream contract; current DEMO/guard now require DZ_SMART_RUBBLE=1 and script the secondary collapse at 162.5 s. Preserve those flags/guard as merged. Preflight derives them from DEMO automatically.
- **Validation:** combined main 3236195 full backend 651 passed / 1 skipped (153.40 s), current demo guard and all 19 F cases included. All 69 frontend tests and production build pass. Pre-integration backend 645 / 1 and frontend 53/build were also green. Live visual limitation remains documented. Earlier approval-review usage failure cleared on user resume; normal reviewed commands completed without bypass.
- **Heads-up for others:** all new solid-prop and scripted-collapse source is from main, not an added F task. No protected-source edits by Aziz.
- **Next:** combined full suite/build, immediate latest-main merge, publish/merge F, then G.

### 2026-11-08 PT - p2/phone-frames - F: Command-gated screen JPEGs on the phone, default off
- **Did:** synced main a3037b7 first and isolated F from the held G work. Added bounded JPEG admission/cache, existing scout-canvas capture at <=3 fps, and phone JPEG display/frozen cache on the existing NO SIGNAL overlay. Uses delivered Command report age <=3 s (same phone contact rule), never the truth link graph; no new JPEG while dark, no old-incident upload after reset. Paused uploads publish to phones without ticking. No extra render contexts; closing/hiding the scout stops captures. Frontend changes are required by this explicitly requested end-to-end F path; teammate histories/protected source untouched.
- **Contract changes:** DZ_PHONE_FRAMES=1 at Hub init/reset, default off. Screen/phone hello adds phone_frames:{epoch,max_width:320,max_height:180,max_fps:3}; POST /api/frames/{robot_id} accepts {epoch,t,jpeg}, bare base64 JPEG <=128 KiB and <=320x180, capture t in sim seconds. Fresh linked phone cmd_view robots[] gains phone_frame:{jpeg,mime,width,height,t,last_seen_s}. Dark publication omits it; phone preserves only its own previously received frame. Rate limit is per robot across uploaders, monotonic wall time; reset clears caches. PLAN.md documents shapes/errors/gates. Existing thermal camera fields unchanged; no JPEGs in screen ticks/maps, AI tools, bundles or persistent files. Pillow is now an explicit server dependency, lazily used only by upload validation.
- **Validation:** final full backend 645 passed / 1 skipped (181.66 s), unchanged seed-7 demo guard and 19 F API/WebSocket/rate/size/reset/ordering/contact cases included; all 53 frontend tests/build pass. Updated the older coverage test's standalone Hub stub with a disabled frame store. Browser visual check ended because Computer Use could not determine the Windows browser URL; no visual claim. The isolated smoke tree was stopped and port 8012 closed; original running app and private env were not touched.
- **Heads-up for others:** user confirmed G follows F: heat_sources:[{id:"H1",type:"generator",x:12.5,y:4,temp_c:65,size_m:0.8}], type enum generator|space_heater|hot_pipe|server_rack|dog|laptop|sunlit. Heat thermal hits add kind:"decoy",type,source_id,temp_c; survivor kind:"survivor", missing kind defaults survivor. That supersedes initial class wording. Do not apply the old G stash unchanged.
- **Next:** full backend/guard, immediate main merge, one F PR and merge; then complete G with the confirmed schema on its own branch/PR.

### 2026-11-08 PT - p2/coverage-grid - Validate E with latest belief display and zone-less save main
- **Did:** pre-PR fetch integrated main c5d0071 (#144 Yusuf belief display, #145 Rayan zone-less save-and-check fix) without conflicts. Reviewed both histories/contracts. E's nine-file diff still excludes all teammate/protected source; no belief wiring or other queued ask added.
- **Contract changes:** none beyond E's documented opt-in coverage object. Latest belief metadata stays independent; E's field is preserved by both map compression protocols.
- **Validation:** final combined full backend 626 passed / 1 skipped (155.03 s), unchanged current seed-7 demo guard and 19 E cases included. All 48 frontend tests and production build pass. Earlier pre-integration backend was also 626 / 1 (153.82 s); no new runtime edits since validation. Actual .env remains ignored/untracked; existing app untouched.
- **Heads-up for others:** Rayan's app.py no-go-only follow-up is now resolved on main. Yusuf's belief renderer is merged; RSSI rendering remains later. No flag defaults changed.
- **Next:** immediate latest-main merge, publish/merge/confirm this one item E PR.

### 2026-11-08 PT - p2/coverage-grid - Command-only predicted RSSI grid, default off
- **Did:** started only after D #143 merged, synced main 339e680 first, added cached map-resolution radio predictions from Command's sanitized prior plus version-accepted delivered relay reports. Shared wall intersection code/constants match scalar propagation; no live state or occupancy-to-material invention. Reset discards source/cache state. No web rendering in E.
- **Contract changes:** DZ_COVERAGE_GRID=1 at CommandPost construction/reset adds coverage to screen maps and phone cmd_view; self-described zlib/base64 signed int8 dBm (nearest/ties-even, clipped [-128,127]), w/h/cell match occupancy, sorted source IDs, predicted:true. Both compact protocols preserve it as metadata, including coverage-only map_patch with grids:{}. PLAN.md documents shape, decoding, known-source assumptions and prediction limits. Off: no field or computation; tick/AI views unchanged.
- **Validation:** combined main c5d0071 full backend 626 passed / 1 skipped (155.03 s), including unchanged seed-7 demo guard and 19 coverage cases; all 48 frontend tests and build pass. Covers scalar parity, known wall/furniture loss, hidden-truth isolation, actual DTN and WebSocket delivery, stale/expired/misdirected/duplicate reports, cache ownership/bounds, reset and both compact transports. Local timing: 19,200 cells, CMD ~15 ms, six new relays ~84 ms, cached read ~0.005 ms; seven-source data 4596 base64 chars. No protected-source edits, actual .env ignored/untracked, existing server untouched.
- **Heads-up for others:** Yusuf: backend field is available for later rendering, interpret signed dBm rather than occupancy codes; no frontend edits required here. Relay state stays last-delivered even if truth is powered off/destroyed; no hidden geometry or live graph enters the prediction. Existing app/private env and Rayan's protected files are untouched.
- **Next:** finish validation, merge latest main immediately before opening the single E PR, then merge/confirm it.

### 2026-11-08 PT - p2/demo-preflight - Integrate final no-go-only and network-view main
- **Did:** pre-PR fetch merged main a179843 (Rayan no-go-only/WAITING backend and Yusuf network traffic display). No edits to their source; item D's diff still contains only its nine tooling/docs/ignore/example/test files.
- **Contract changes:** none from D; it consumes unchanged hello.data.detector. Rayan's WAITING/plan_state/zone-less plan changes are his main contract. His app.py save-with-check follow-up is outside D and remains queued.
- **Validation:** final combined full suite 607 passed / 1 skipped (153.78 s), current seed-7 demo guard and 25 preflight cases included; real 10 s model/tree/listener smoke passed. Key file remains ignored/untracked and restricted locally; no values exposed.
- **Heads-up for others:** preflight follows current DEMO flags (1.5x and obstacles on); the current app is left running. No local API keys are committed, and no unrelated backend fix is bundled.
- **Next:** finish combined suite, immediate latest-main merge and publish/merge item D.


### 2026-11-08 PT - p2/demo-preflight - Verify Windows probe tree shutdown before declaring PASS
- **Did:** the real smoke test exposed a launcher/listener shutdown gap on Windows. The checker now stops its owned process tree with taskkill /T before losing the launcher, waits for its process and confirms the listener closes. Cleanup failure makes the hello check FAIL even if a real model was reported. Existing servers are never targeted.
- **Contract changes:** none; the same 15 PASS/FAIL checks and exit status. No child logs or key values printed.
- **Validation:** real 10 s current-demo model hello plus tree/listener cleanup passed (12.56 s including shutdown); added native-tree and failed-cleanup regressions. Final combined full suite passed 603 / 1 skip (147.31 s), including current demo guard and 25 preflight cases; no production model/transport behavior changed.
- **Heads-up for others:** current DEMO is 1.5x with furniture on; parser follows it automatically. The separate app on :8000 and private key file remain undisturbed.
- **Next:** final full suite, immediate main merge, publish/merge item D.


### 2026-11-08 PT - p2/demo-preflight - Integrate the new 1.5x furniture-on demo before PR
- **Did:** merged main 504e82d (Rayan's re-baseline plus Yusuf's draw calls). Resolved only the runbook overlap: preserved all new beats, speed 1.5 and required DZ_OBSTACLES=1 while keeping preflight step 1 and activated-python commands. The parser picks up the new flags without checker changes.
- **Contract changes:** no wire changes from D. Rayan's main-run environment now requires DZ_SPEED=1.5 / DZ_OBSTACLES=1. His guard and all robot/web source remain unedited in this PR.
- **Validation:** integrated full suite pending; pre-integration full suite 600 passed / 1 skipped and real CPU/model-hello/secret-safety checks passed. Added decimal-speed/obstacles coverage to the existing runbook fixture.
- **Heads-up for others:** preflight intentionally follows the current DEMO.md rather than the older 2x/no-furniture profile. The running :8000 app is not reset or stopped.
- **Next:** finish integrated validation, merge latest main immediately before the one item D PR, publish/merge.


### 2026-11-08 PT - p2/demo-preflight - Secret-safe cross-platform laptop checks and private key file setup
- **Did:** synced main first, added preflight.ps1/preflight.sh plus one shared checker, and inserted preflight as DEMO step 1. Both wrappers activate .venv and avoid the wrong global interpreter; check keys/flags/tools/ports and a real-model hello from an owned temporary server. Demo producer and runtime behavior unchanged.
- **Contract changes:** none on REST/WebSockets; diagnostic scripts emit one PASS/FAIL line per check and return nonzero for any failure. Exact runbook flag allowlist is derived, not duplicated; commented flags excluded; extra nonempty DZ values (including 0) rejected. No key values, exception payloads or child logs are printed.
- **Validation:** all 22 focused failure/redaction/flag/port/cleanup tests pass; both real wrappers agree (CPU torch/checkpoint pass; missing keys/flags/cloudflared and occupied 8000 fail). Real isolated 10 s model-hello and cleanup pass without touching the running :8000 app; full backend 600 passed / 1 skipped (149.55 s), including fixed seed-7 guard and all 22 preflight regressions.
- **Heads-up for others:** explicit local-key follow-up also added safe blank ELEVENLABS field and .env backup ignore coverage. Existing local key values preserved; git ignore/untracked/add-refusal and HTTP 404 checks passed. Local Windows ACL restricted to current user/SYSTEM for root and existing running-app env copy; ACL metadata backup only is ignored. No secret values in Git/history/chat. preflight.sh gets LF endings and executable mode for Unix; Git Bash and POSIX sh smoke runs pass the checker integration. Root lookup uses shell builtins so it does not depend on dirname being on PATH.
- **Next:** full backend/demo guard, immediate main merge, publish/merge this one item D PR; keys are entered only in the ignored local file.


### 2026-11-08 PT - p2/compact-screen-deltas - True compressed deltas and measured 60 s live screen traffic
- **Did:** synced main, preserved the previous work, and added per-screen sparse map patches with a native web decoder and legacy recording normalization. Kept all 36 currently drawn lidar endpoints (18 in perf mode) and left renderer/sensors/autonomy unchanged. Also fetched everyone's merged updates and launched isolated main 6949ede on localhost:8000 with the trained detector for Aziz's run request.
- **Contract changes:** DZ_COMPACT_STREAM default off, /ws/screen?map_deltas=1 capability negotiation, compressed initial maps then changed-cell-only map_patch records and per-socket epoch/base/version; exact layouts in PLAN.md. No tick/event throttling, no phone deltas. Unsupported clients keep legacy maps. Malformed/gapped deltas reconnect for a keyframe; recordings remain legacy-readable.
- **Validation:** before 349471.867 B/s / 35.983 msg/s; after 146313.383 B/s / 34.967 msg/s, actual speed-2 3-robot 60-wall-second runs. Map traffic 205190.617 to 1910.817 B/s. Actual JS decoder: 482 exact grid comparisons, 1200 identical lidar/pose ticks, 358 replay round trips. All 39 web tests and web build pass; full backend 578 passed / 1 skipped (240.92 s), including fixed seed-7 demo guard; all 20 focused delta/stream cases pass, including both flags together.
- **Heads-up for others:** web support is part of the explicit compatibility request; no web scene source edited. Main 22fbd2e README/slide updates are included; the separately running main checkout was refreshed without restarting the current incident. New helpers are isolated in net/mapStream.js; ordinary sessions and presenter-token redaction remain supported. Rayan's latest no-go-default/facts changes were integrated without editing his protected source. Metrics count UTF-8 JSON before WS/TLS, excluding the initial four connection frames equally; one tick differs at the window boundary.
- **Next:** merge latest main immediately before this release PR, publish/merge/confirm it and report the rates; no requested implementation remains.


### 2026-11-08 PT - p2/stream-payload - Integrate Rayan furniture radio main before PR
- **Did:** final pre-PR fetch found main 92b7c37; merged it and paused PR creation for combined validation. Rayan owns the furniture loss_db change in floorplan.py/test_obstacles.py; C does not edit those files and they are absent from its PR diff.
- **Contract changes:** C stream contract unchanged. Rayan's floor-plan obstacle loss_db metadata remains his main contract; DZ_OBSTACLES still stays off pending his demo rebaseline. No phone/Command leakage or new sensor inputs.
- **Validation:** combined full backend 567 passed / 1 skipped (149.10 s), fixed seed-7 guard included with flags off. The integrated 250 s measurement replay exactly matches the committed results (46,907,785 to 10,560,824 bytes, -77.49%); previous isolated real WS trial also passed.
- **Heads-up for others:** shelf-radio blocker resolved on main by Rayan; belief/prior wiring remains a separate request. Compressed output still requires Yusuf's explicit decoder opt-in; ordinary clients keep base64.
- **Next:** finish integrated validation, immediately merge latest main before PR, then publish/merge/confirm C.


### 2026-11-08 PT - p2/stream-payload - Recover item C after traffic merge and measure actual wire output
- **Did:** confirmed B #126 merged as 51d1509 before creating this branch. Recovered only stream serialization/cadence and tests; added a reproducible measurement script and decoder handoff. Screen thinning never changes sensors, maps or autonomy; phones remain delivered-only.
- **Contract changes:** additive default-off DZ_STREAM_OPTIMIZE protocol in Now and scripts/STREAMING.md; compression requires explicit compact=1 negotiation so ordinary clients keep decodable grids. Optional future belief grids are preserved without claiming belief wiring exists.
- **Validation:** full backend 564 passed / 1 skipped (137.23 s), including fixed seed-7 demo guard with flags off; 37 focused stream/traffic/camera tests also passed. scripts/stream-measurements.json records 250 s seed-7 demo replay: 46,907,785 to 10,560,824 screen JSON bytes (-77.49%, compact), or 26,055,873 with ordinary base64 (-44.45%). Every compact grid decoded identically (630 checks), all 1546 events retained; ticks 2500 to 1250, lidar 36 to 24. Measurement excludes WS/TLS, hello and plan_state, uses modeled 30 Hz input/3x sim, and claims no browser FPS change. Isolated live uvicorn/WS trial passed: initial maps 51,343 to 896 bytes; real plan hops/applications to all 3 robots, delivered phone camera, exclusive leases and tick cap; test server stopped. Physical phones not tested.
- **Heads-up for others:** Yusuf: add opt-in zlib decoder before requesting compact=1; version caches reset on hello. No camera/backend ownership changes. Source exclusions and server/.env remain untouched.
- **Next:** publish this tested item C PR after immediate main integration, merge/confirm it; no requested implementation remains after merge.


### 2026-11-08 PT - p2/network-traffic - Isolate item B from inherited combined WIP
- **Did:** confirmed collision #108 and camera #115 merged, preserved all inherited WIP, integrated main c6b1812 and moved only actual hop/held diagnostics and queue depths into this branch. Added transport and screen/phone boundary checks. C remains uncommitted in the saved WIP for a later branch.
- **Contract changes:** additive default-off DZ_NETWORK_TRAFFIC fields in Now and scripts/TRAFFIC.md; custody acceptance is the only successful-hop trigger, holds coalesce, and diagnostic overflow never changes transport. No legacy flag-off wire change.
- **Validation:** full backend 554 passed / 1 skipped (139.41 s), including the fixed seed-7 demo guard; all 11 traffic cases passed. Windows sandbox temp ACLs required normal temp access; no production change for the environment issue.
- **Heads-up for others:** Yusuf can consume a/b/bid/timing/hops, hold node/reason and Reality queues. No stream compression bundled here. New main includes shelf export/demo caveat, test-laptop refresh and Yusuf's floating scout camera; their source is untouched.
- **Next:** complete backend/demo guard validation, merge main immediately before opening this one PR, merge/confirm it, then start C separately.


### 2026-11-08 PT - p2/global-no-go - Combined belief/no-go validation green
- **Did:** final source combination on main 123c32d passed the full backend after belief integration; no-go source unchanged from the focused trace replay.
- **Contract changes:** none; DZ_GLOBAL_NO_GO remains default off and no new belief wire fields are claimed.
- **Validation:** 540 backend passed / 1 opt-in skipped (127.81 s), including fixed seed-7 guard; exact 80 s no-go replay and delivered inside-start checks remain green.
- **Heads-up for others:** no robot/web/data source edited; existing scope/ownership disclosure in #118 remains accurate.
- **Next:** merge/confirm #118 and delete its branch, then the last batch PR for traffic/stream.


### 2026-11-08 PT - p2/global-no-go - Integrate belief main before no-go merge
- **Did:** #118 opened with 535 backend passed/1 skipped; main advanced with Rayan's display-only belief PR #117 during creation. Integrated main 123c32d without editing his robot/data source; combined backend/guard rerun before merge.
- **Contract changes:** none in this merge. Read Rayan's new belief-map wiring reservation; it is a separate future backend task, not silently added to the current five-item batch. Traffic compression will preserve optional future belief grid keys.
- **Heads-up for others:** no claim that belief grids are already served by Sim.maps. Global no-go stays default off. Rayan's physical escape and Yusuf's phone UI remain included and unchanged.
- **Next:** finish combined validation/merge #118, then the final traffic/stream PR.

### 2026-11-08 PT - p2/global-no-go - Fix the traced global exclusion dispatch and route start
- **Did:** implemented both backend break points in rayan-ml 15:10: send the shared exclusions to every statically deployed robot through DTN, and estimate an exit from a newly excluded delivered start before route planning. Clearing exclusions reaches unassigned robots too. No masks, poses or acknowledgments are injected directly into robot state.
- **Contract changes:** DZ_GLOBAL_NO_GO=1 at construction, default off, reserved before code. Existing plan/API/result shapes remain unchanged. Zones are still required for dispatch; each robot's payload may have zero zones. Escape remains bounded, never crosses known occupied/static-hazard cells, never relaxes destination/home, and its distance counts in battery reserve.
- **Validation:** final full backend 535 passed / 1 opt-in skipped (117.97 s), including fixed guard; 10 focused cases. Exact trace area avoided by all robots through 80 sim seconds; real-building R3 inside-start estimate passes; actual DTN apply/clear/idempotence covered.
- **Heads-up for others:** Rayan's physical escape #116 and Yusuf's UI defaults #112 are included, but not edited. Outside source area: server/tests/test_global_no_go.py and required own history. Flag stays off until testing-laptop dry run. This is batch 5 only, intentionally before traffic.
- **Next:** publish/merge/confirm this PR and delete branch; finish batch 4 traffic/stream separately.


### 2026-11-08 PT - p2/global-no-go - Trace-driven dispatch/safety contract before code
- **Did:** confirmed camera #115 on main 47805df and cleaned branch. Reordered only the remaining work: urgent traced no-go fixes first, traffic/performance last, one PR each. Read Rayan #116 escape and Yusuf #112 priority/assignment/no-go-only UI handoffs.
- **Contract changes BEFORE code:** DZ_GLOBAL_NO_GO=1, broadcast full exclusions to all deployed IDs through ordinary filtered plan bundles; BFS escape estimate from delivered start inside a new exclusion, bounded to Rayan's 6 m coordinate window and counted in energy. Default off. Keep quiet draft vs checked dispatch distinction and >=1-zone requirement. No API/wire changes.
- **Heads-up for others:** these fix rayan-ml 15:10 bugs 1.1/1.2. Rayan already owns/fixed physical escape in #116, and Yusuf fixed UI items in #112. No robot/web edits here, no DTN shortcut or fake plan acknowledgment. Geometry estimates remain from Command knowledge.
- **Next:** reproduce one-zone dispatch with global exclusions, mid-run inside-zone safety, real DTN application/clearing, no-through-wall/hazard cases, idempotence and default guard; finish one PR then traffic.

### 2026-11-08 PT - p2/phone-camera - Delivered thermal frames for phone robot pickers
- **Did:** wired validated delivered camera snapshots into Command and cmd_view, with source/arrival/capture-age metadata and reset/out-of-order handling. Frozen camera payload at DTN enqueue prevents live producer mutation of old queued frames. Integrated real producer #114 and verified real producer and outage custody paths. Existing exclusive leases remain enforced across two phones.
- **Contract changes:** additive flagged camera output and last_seen_s age as reserved before code; no camera when off/no received frame. No live pose/Reality reconstruction, no fabricated confidence, no command/lease changes. Non-camera transport is unchanged.
- **Heads-up for others:** Rayan: age follows your supplied camera.t; please preserve true capture time when perception pauses. Yusuf: robot ID selects the delivered frame, last_seen_s can label staleness without exposing live links. Rayan 14:10 explicitly requested the example gate line. Outside owned source: server/.env.example (that written request), server/tests/test_camera_delivery.py, required own history. No robot/web edits.
- **Validation:** final full backend 523 passed / 1 opt-in skipped (114.80 s), including fixed demo guard; 45 focused real-producer/camera/lease tests passed. The one initial synthetic-phone fixture was updated after genuine startup frames existed; final full suite green.
- **Next:** merge/confirm this camera PR, delete branch, then traffic/stream PR. New feature stays off until laptop acceptance.


### 2026-11-08 PT - p2/phone-camera - Shelves merged; delivered camera contract before code
- **Did:** confirmed #111 merged as f2894a0 and cleaned its branch, fetched/read team context, started only camera backend. Exclusive robot leases already exist and remain unchanged.
- **Contract changes BEFORE code:** camera flag/input/output/age and stale-frame retention are specified in Now. Capture t drives last_seen_s; delayed arrival never creates a fresh image. Rayan's delivered_t name is retained for bundle created; reported_t is true arrival. Flag off keeps legacy shapes. Only delivered validated data, never Reality reconstruction.
- **Heads-up for others:** Rayan produces camera telemetry in his robot PR; Yusuf consumes cmd_view by robot ID. Accepted hits are bounded to 64, verdict person/rejected/unsure, finite in-bounds pos, confidence 0..1/null, local PNG crop/null; unknown fields are stripped. Phone spectating remains read-only; only direct commands require an exclusive lease.
- **Next:** implement/test delivery boundary, no-freshening/out-of-order/reset, malformed frame isolation and lease enforcement, then one PR before traffic.

### 2026-11-08 PT - p2/shelf-obstacles - Include testing-laptop performance profile before merge
- **Did:** #111 opened with 503 backend passed/1 skipped and fixed guard green; integrated main 65fea46 (#110 performance-profile history only), which landed during PR creation. No server/web source delta from this merge; existing validation still applies.
- **Contract changes:** none. The performance diagnosis is recorded in rayan-ml.md 16:10; payload work remains batch 4, scene optimizations remain Yusuf's area.
- **Heads-up for others:** no claim that network payload alone fixes the profiler's shader/draw-call costs. Shelves still default off, actual footprint exports remain external.
- **Next:** merge/confirm #111, delete its branch, then start camera backend with a fresh team-sync.

### 2026-11-08 PT - p2/shelf-obstacles - Known shelf occupancy and material radio loss
- **Did:** added default-off physical obstacle loading with footprint validation, filled/boundary occupancy for shelves, actual material radio loss per edge, and matching known pre-collapse planning metadata. Thin shelves block lidar instead of falling between cell centres. Integrated shutdown main baf9d29 without robot source edits.
- **Contract changes:** DZ_OBSTACLES=1 and obstacles poly/material schema were recorded before code; material defaults metal, loss comes from materials, known shelves enter planning_data only when enabled. No API/event shape changes and no truth rubble or survivor leak.
- **Heads-up for others:** Rayan owns obstacle JSON and Yusuf exports footprints; both can use the backend contract in Now. No data/web/robot source touched. Outside source area: server/tests/test_obstacles.py and required own history. Collision stays independently off pending dry run.
- **Validation:** final full backend 503 passed / 1 opt-in skipped (120.23 s), including fixed demo guard and shutdown integration; 12 focused obstacle cases passed.
- **Next:** publish/merge/confirm this one PR, delete branch, then phone camera backend.


### 2026-11-08 PT - p2/shelf-obstacles - Integrate shutdown main while validating shelves
- **Did:** shelves passed 12 focused cases and full backend 501 passed/1 skipped (122.16 s). Integrated Rayan's shutdown PR #109 on main baf9d29 before publishing; no edits to his robot source.
- **Contract changes:** none from this integration; obstacle contract in Now remains default-off DZ_OBSTACLES. Rayan's shutdown/yielding ownership unchanged.
- **Heads-up for others:** actual shelf footprints remain with Yusuf/Rayan. New material footprints are known pre-collapse structure, not hidden rubble. Full combined validation is rerun after the main integration.
- **Next:** publish/merge shelves after final checks, then delivered camera backend.

### 2026-11-08 PT - p2/shelf-obstacles - Collision merged, shelf contract before code
- **Did:** confirmed #108 merged on main 9144aad and deleted its branch. Started only batch 2 after fetching/reading team context.
- **Contract changes BEFORE code:** DZ_OBSTACLES=1 enables static obstacles poly/material occupancy, thin-boundary rasterization, material loss per crossed edge and public planning metadata as specified in Now. Default off. Rayan owns JSON data and Yusuf exports footprints.
- **Heads-up for others:** Rayan/Yusuf can publish poly footprints now; no source/data edits in their areas. Collision flag remains independently default off. Gemini key remains deferred.
- **Next:** test shelf occupancy, lidar/visibility blocking, propagation loss, public-prior consistency, malformed footprints and guard; finish one PR before camera backend.

### 2026-11-08 PT - p2/robot-collisions - Hard robot bodies and real blocked feedback
- **Did:** added opt-in continuous 0.30 m robot-body collision checks with simultaneous proposals and iterative chain blocking, preserving rotation and legacy flag-off motion. Stops are visible to robot policy through real odometry on the next step. Contact pairs emit one Reality event per encounter; no robot state is injected.
- **Contract changes:** DZ_ROBOT_COLLISIONS=1 at Sim reset, default off. Existing odometry blocked/v is the primary contract; additive flag-on blocked_by is sorted robot IDs, empty for no robot contact. Reality adds blocked/blocked_by/body_radius_m and robot_contact {a,b,pos}, midpoint of stopped bodies, deduplicated while the pair remains blocked. No Command/phone/radio/Gemini additions. Matches Rayan 13:10 radius and backstop proposal.
- **Heads-up for others:** Rayan retains yielding and all autonomy changes. Yusuf may consume robot_contact for a toast. All behavior remains off until testing-laptop dry run. Outside source area: server/tests/test_robot_collisions.py and required own history only. Full seed-7 behavior is unchanged with the flag off.
- **Validation:** final full backend 489 passed/1 skipped (121.97 s), including the fixed seed-7 guard; 12 focused collision tests passed.
- **Next:** finish this one PR, merge/confirm main, delete branch, then obstacles PR.


### 2026-11-08 PT · p2/robot-collisions · Align with Rayan contracts and receive planning trace
- **Did:** integrated origin/main 2fbfb98 (#106 collision/camera contracts, #107 phone diagnosis; history-only commits). Existing collision implementation passed 488 backend tests plus 1 opt-in skip. No robot policy edited.
- **Contract changes BEFORE remaining code:** radius 0.30 m and existing odometry blocked align with Rayan 13:10 entry. Add once-per-contact-pair Reality `robot_contact {a,b,pos}` behind the collision flag, no radio/Command leak. Optional blocked_by remains additive. Camera contract reserved as DZ_CAMERA_TELEMETRY with delivered snapshots only; implemented in its later PR.
- **Heads-up for others:** Rayan/ML's exact no-go breaks (unassigned robot recipients, safety start in exclusion) are now queued for batch 5; pre-#101 trace does not exercise the newer acknowledged phone saves. Yusuf's low-priority/assignment defaults and Rayan's escape policy remain their fixes. No claim that an observed WebSocket/HTTP race caused that trace.
- **Next:** verify contact-event dedupe and finalize collision PR, then batch 2. Continue team-sync at least every 30 minutes using .claude/skills/team-sync/SKILL.md; user already authorizes main integration through the standing PR rules.

### 2026-11-07 PT · p2/robot-collisions · Main integration and collision contract before code
- **Did:** confirmed #101 merged concurrently, included latest main f3b8f3a, preserved the closing history entry, and started only batch 1. No collision implementation yet.
- **Contract changes:** proposed DZ_ROBOT_COLLISIONS, 0.30 m disc radius, continuous simultaneous collision rejection, blocked/v feedback and optional flag-on blocked_by/body_radius_m as recorded in Now. Default off; no robot policy or Command leak.
- **Heads-up for others:** Rayan: read the collision proposal in Now; existing blocked boolean stays the primary IO signal, yielding remains your area. Camera/traffic contracts and trace are pending your other sessions; Aziz explicitly said keep going and sync every 30 minutes.
- **Next:** implement/test swept contacts, reverse motion, crossing, chain blocking, flag-off parity and seed-7 guard, then merge the one collision PR before batch 2.

### 2026-11-07 PT · p2/phone-sync · Close existing PR before Rayan backend batch
- **Did:** fetched origin/main 2da65d2 (#102 demo Q&A, #103 calibration assets) and integrated before closing #101. Those commits change no server or web code; the 477-test backend / 15-test frontend / 754-module validation remains applicable, with guard and asset tests rerun below. New five-item batch queued in Now; one PR each, behavior flags default off.
- **Contract changes:** none in this integration; each batch contract will be recorded before its code.
- **Heads-up for others:** no teammate-owned source edited; no test-laptop trace supplied yet. Existing #101 is finished first per one-PR-at-a-time rule. Gemini key still deferred by Aziz.
- **Validation:** seed-7 guard plus AI asset tests **19 passed** (19.34 s); main's new commits change no server/web source, retaining the 477 backend / 15 frontend / 754-module validation.
- **Next:** merge #101 and confirm on main, then start hard robot collision PR. Aziz confirmed pending contracts/trace are in progress on the other laptops; continue independent collision work.

### 2026-11-07 PT · p2/phone-sync · Integrate last-minute main before phone PR
- **Did:** initial phone fix committed as ba2f5f6. The pre-PR remote-head check caught #99/#100 landing; merged origin/main 80f554e without conflict and re-read Rayan/ML histories. Main's showcase, variants, robot counters, close-look behavior and fused heatmap changes are preserved without edits to their source.
- **Contract changes:** none from this merge; phone contracts remain in the preceding entry. Read Rayan's new hotspot_unsure/close-look and robot.counters contracts. Quiet default-plan preload and reading robot.counters into screen stats remain separate backend follow-ups; they are not claimed as phone fixes here.
- **Validation:** final full backend **477 passed, 1 skipped** (155.80 s), including fixed demo guard. Frontend **15 passed**, build **754 modules**; #99/#100 change no web files. Refreshed preview runs the complete integrated backend; fresh HTTPS QR/pages/assets and two Command-only phone WSS pass, local/public incident epochs match. Gemini key remains explicitly deferred by Aziz; no provider success claimed.
- **Next:** commit this validated merge with own history staged, push and open one PR that includes current main. Keep the generator/default-plan/counter follow-ups separate from this phone fix.

### 2026-11-07 22:55 PT · p2/phone-sync · Shared phone planning and honest Gemini setup
- **Did:** fixed dropped no-go/cleared drafts, offline save acknowledgment, save/check/dispatch races, reconnect/reset state, dispatched-plan forking, immediate paused-screen relay updates, stale map pointer listeners, and stale Gemini answers after reset. One-origin HTTPS preview replaces the disconnected local/public sessions. Integrated main fbc1892 with the latest ML assets, judge pool and Yusuf's random-quake UI.
- **Owner approval:** Aziz confirmed in this session: **“Yusuf approved—record my confirmation in aziz.md”** for fixes in `web/src/phone/`. This is the user's report of Yusuf's approval; no teammate history is edited.
- **Contract refinement BEFORE code:** add `POST /api/plan/check` with `{plan_id,plan_epoch?}` returning the existing safety result without re-saving. `/api/dispatch` also accepts optional `plan_epoch`. Both check the epoch inside the plan lock; legacy callers without it remain compatible. Phone saves/checks/dispatch use ordered HTTP acknowledgments while WebSockets distribute shared changes. Unsaved edits survive reconnection only within the same epoch and remain visibly pending; reset discards old-incident edits. No CRDT or offline merge claims (whole-draft last-write-wins remains the contract).
- **Paused relay fix BEFORE code:** relay join, power/place edits and final disconnect publish an immediate existing screen `tick` snapshot while paused (no simulation step); phone `relay_state` ordering and Command's delivered-only state remain unchanged. No new event shape or simulation behavior.
- **Contract BEFORE code (phone fixes):** quiet draft saves (`POST /api/plan?check=false`, WS `plan_edit`) accept 0–32 zones so no-go-only and cleared drafts synchronize; check/dispatch still require a search zone and return `empty_plan` (422) otherwise. Existing `SearchPlan` remains dispatchable-only. Phone `hello` adds opaque `plan_epoch` (changes on reset/restart) and `dispatched_plan_ids`; successful first dispatch also broadcasts existing `event {kind:"plan_dispatched",plan_id}` to phones. Draft saves may carry optional `plan_epoch`, rejected with `plan_reset` (409) when stale. Gemini local responses add optional `unavailable_reason` with a fixed public code (disabled, missing_key, invalid_model, timeout, provider_error, invalid_response); credentials/provider error bodies never leave the server. No truth added to phones or Gemini; no change to robot contracts, seed-7 behavior, or feature gates.
- **Contract clarification:** `unavailable_reason` is added only to local phone Ask replies; G keeps its exact existing shape. Draft transport remains whole-plan last-write-wins, not an offline merge algorithm.
- **Heads-up for others:** Yusuf's phone-scope approval was explicitly confirmed by Aziz in this session and recorded before edits. Phone-only web files plus a new web regression test are touched; no scene/presenter UI edits. Shared server tests include a detector-status sequence adjustment for immediate relay ticks. User will configure GEMINI_API_KEY later; no key read/output/commit, no genuine model answer claimed. Rayan still announces freeze.
- **Validation:** final backend **464 passed, 1 skipped** (96.34 s); frontend **15 tests passed**; build **754 modules passed**; latest-main explicit demo guard **10 passed**. Fresh HTTPS QR/pages/assets and screen + two Command-only phone WSS passed; local/public phone epoch and trained detector match; public Ask confirms missing_key fallback, judge pool has 40 items. Physical phone test remains external.
- **Next:** publish this single PR for review and run a keyed phone Ask once Aziz configures the private key. Yusuf's new seed-reset/random extra-aftershock proposals are read and deferred to a separate task after this PR; no unapproved generator contract is claimed.


### 2026-11-07 PT - p2/presenter-leases - J/I panels under explicit Yusuf handoff, final validation and Chrome preview
- **Did:** integrated official main 34cc4c5, which records Yusuf's OK for Aziz J/I. Built J with exported held-out evidence only, random no-repeat rounds, hidden answer until guess, model/judge tallies and no rounding-up; missing pool/metadata stays explicit. Built I from measured tick.stats, omitting unavailable totals. Added actual Command hop mean and optional Rayan-owned counter aggregation; no assumed zero detector/met-deadline counts. Shared accessible data modal, keyboard isolation, J/I buttons/keys. Refreshed only our owned preview 8030; public tunnel untouched.
- **Contract changes:** new J/I keys; documented judge manifest examples/file/label/p_person, held_out or split, model threshold or predicted label (existing lab-style conf alias accepted). Optional robot telemetry.counters detector_calls/detector_rejections/scheduler_deadlines_met aggregate only if every robot supplies them. Existing aftershock/reset/counter contracts unchanged. No frontend lease/presenter UI or robot/ML/map source edits.
- **Validation:** final backend **454 passed, 1 skipped** (87.49 s), fixed guard green; **6 Node tests passed**, web build **745 modules**. Live HTTP bytes/WS/stats/catalog passed, raw evidence final-stretch-preview-2026-11-07.json. Actual judge pool absent/404; no actual provider call. User stopped browser automation with physical Esc before final visual QA; no further computer input.
- **Heads-up for others:** Rayan/ML: export the held-out pool + metadata in FINAL-STRETCH-BACKEND.md, then J can run real rounds; detector/met-deadline counters retain your ownership. Yusuf: J/I handoff implemented; rest of your frontend untouched except their keys/top-bar/store/modal CSS. Presenter B/U UI remains your handoff. Rayan announces freeze.
- **Next:** publish complete #90 for review. Dataset/instrumentation exports, presenter UI and joint rehearsal remain explicitly tracked; do not call the whole project accepted based on backend tests.

### 2026-11-07 PT - p2/presenter-leases - Final-stretch backend controls and diagnostics
- **Did:** implemented strong earthquake (2 areas now + 1 at 10 sim s; up to 2 actual relay losses), validated atomic reset into registered maps, opt-in generated timeline player with explicit runtime failure events, actual sensor/transport/FEC/robot/scheduler counters in screen stats. Confirmed nested judge_pool serving with delayed asset arrival/read-only tests. #89 is already merged; reran its real protocol/fallback/privacy tests. Opened a separate paused Chrome test preview on 8030 without replacing the public tunnel.
- **Contract changes:** as reserved in Now and docs/FINAL-STRETCH-BACKEND.md: strength, reset selection, /api/scenarios, startup floorplan/timeline gate and screen-only counters. Original normal aftershock/default demo, phone/Command/Gemini knowledge and source labels preserved.
- **Validation:** final full backend **453 passed, 1 opt-in soak skipped** (107.89 s); 24 final-stretch regressions, fixed demo guard green; diff check clean. Existing merged web rebuilt 741 modules before opening Chrome. No actual provider calls.
- **Heads-up for others:** new main 34cc4c5 explicitly records Yusuf's OK for Aziz J/I; proceeding only with those data panels. Rayan: registered nested map IDs/timeline ready; judge_pool assets are still absent in this checkout. Rayan owns future detector/met-deadline counters and exports; no fake counts or judge score. Keep fixed-demo gates unchanged until accepted.
- **Next:** integrate official plan update, build/verify J/I, refresh the owned preview, then publish the complete PR. Freeze is announced by Rayan.

### 2026-11-07 PT - p2/presenter-leases - Atomic presenter groups and backend-only UI handoff
- **Did:** implemented preposted group claim/heartbeat/release APIs. Fleet conflicts cannot partially acquire or renew grants; missing/foreign heartbeat/release targets cannot mutate the other grants. Added screen B/U admission, reset/disconnect/expiry, overlapping race, malformed/session/gate/privacy regressions. User explicitly requested backend only; wrote docs/PRESENTER-LEASE-HANDOFF.md for Yusuf instead of changing web source.
- **Contract changes:** exactly the reserved 3 POST /api/leases/group/* routes, robots list and name for claim; same X-Controller-Token, public leases state/errors, 15 s TTL and 5 s client heartbeat. Existing single-target APIs/B/U/override semantics remain; no bypass or forced takeover.
- **Validation:** full backend **427 passed, 1 opt-in soak skipped** (119.22 s), including fixed DEMO guard; initial focused 41 passed; diff check clean. No new frontend build/source edits, provider call, public tunnel restart or device acceptance.
- **Heads-up for others:** Yusuf: follow the handoff for explicit Take/Release, heartbeat, token on B/U, revision handling and reset/reconnect. Redact the private hello token before recordFrame; current raw recording path is a frontend follow-up. Keep voice/leases off in the fixed demo until UI + joint acceptance pass. Rayan: no robot/ML/map change.
- **Next:** PR review; Yusuf UI and joint dry run. Remaining Aziz integration work is optional startup floorplan/timeline and honest paced-soak acceptance; robot review findings require owner coordination.

### 2026-11-07 PT - p2/presenter-leases - Reserve explicit atomic presenter lease groups
- **Did:** fetched main 3770032, confirmed #89 merged and unchanged teammate contracts. Starting presenter B/U flow: B needs all robot leases, U its target; sequential claim currently risks partial ownership. User authorized next task; requested separate web ownership permission under CLAUDE.md.
- **Contract changes:** additive POST /api/leases/group/claim {robots:[...],name}, /group/heartbeat and /group/release {robots:[...]}; existing session header/state/errors. All-or-none target validation, unique 1-3 robot list. No implicit presenter grant, bypass or forced takeover; override still releases only.
- **Heads-up for others:** Yusuf: explicit claim + 5 s heartbeat + controller token on B/U; group API avoids partial fleet claims. Robot policy, maps and provider calls are outside this task.
- **Next:** implement backend/tests and publish final contract; integrate only explicitly authorized frontend scope.

### 2026-11-07 PT - p2/short-briefing - Implement concise G and audit remaining Aziz work
- **Did:** synced main 21dd05d (#85/#88), checked plan updates, all team histories, merge/PR status, backend contracts and frontend consumers. Implemented short G and bounded local fallback; added docs/AZIZ-STATUS-2026-11-07.md with the ordered queue and owner dependencies. Existing contract-only #89 gets the implementation after final checks.
- **Contract changes:** preposted existing report.text now <=3 sentences / 45 words, digits. No short/spoken field. Nonconforming model replies fall back with source local rather than discarding uncertainty; Ask keeps separate response behavior. Same tools/deadline/privacy.
- **Validation:** full backend **413 passed, 1 opt-in soak skipped** (91.33 s), including fixed DEMO guard; focused **69 passed**; unchanged merged web build **741 modules passed**. Diff check clean. Sandbox temp-file access errors resolved by running suite outside sandbox; Ruff is not installed in this venv. No real provider calls/keys, robot policy changes or frontend source edits.
- **Heads-up for others:** Yusuf: report.text is concise, your #85 playback works with it. Presenter lease UI, sensor-frame adoption, offline queue, voice and repair/order presentation still depend on your integration. Rayan: read A1/A2, preserved default-off gate; generated-map long-route fitting stays yours. Existing 7.654x paced-soak failure remains open.
- **Next:** #89 review, then agree the presenter lease flow with Yusuf. Keep deployment/device acceptance separate from git/build completion.

### 2026-11-07 PT - p2/short-briefing - Reserve concise G text before code
- **Did:** refreshed demo/profile is implemented in PR #88 (an early contract-only #86 merged before implementation push). Starting Rayan's 3-sentence G request, estimate 15-25 min; synced main 309fb9d.
- **Contract changes:** same response fields; G text at most 3 sentences / 45 words, digits, plain spoken English. Ask keeps question-specific behavior. Same six delivered-Command tools, deadline and source labels; no hidden survivor totals/unreported counts.
- **Heads-up for others:** Yusuf: keep speaking report.text, no new field or UI implementation needed. Rayan: G shortening follows your ask; real source verification remains testing-laptop work.
- **Next:** concise local fallback + bounded Gemini briefing, meaningful protocol/fallback/privacy tests, own PR; no actual provider calls.

### 2026-11-07 PT - p2/demo-refresh - Refreshed demo backend and independent mic preflight
- **Did:** rebuilt latest Yusuf frontend unchanged; replaced only our owned old tunnel/backend. Current API exposes voice audio/TTS routes, trained model live, AI Lab 5-point curve served, three robots paused, P-1 quietly saved (no safety_reject), baseline/deadzone B controls pass. Fixed-demo launch uses --no-leases --gemini with DZ_AI_LAB=1; voice/leases and unaccepted experiments off. No provider call/key inspected.
- **Contract changes:** preposted --no-leases rejects --voice combination; launcher always enables independent DZ_MIC_CHECK=1 so mic diagnostics need not enable direct controls. Default standalone gate remains off. No API/message shapes changed.
- **Validation:** final backend **404 passed, 1 skipped** (112.30 s), web build **737 modules passed**, live HTTPS HTML/assets/API/QR + screen/two-phone WSS passed. Local actual mode/reset/quiet preload/AI Lab/mic probes passed; JSON under validation/demo-refresh-*.json. New origin https://gibson-launched-quote-said.trycloudflare.com; phone/mic-check links derive from it. Existing venue mic acceptance was on old origin; physical permission/playback on this origin remains manual.
- **Heads-up for others:** Rayan/user: G/Ask enabled for your keyed check, no calls made by Aziz; mic preflight alone is not provider acceptance. Yusuf UI untouched. CLI defaults remain leased; use --no-leases for fixed main demo until presenter flow is accepted.
- **Next:** publish this refresh PR, then short G text (15-25 min) as a separate PR.

### 2026-11-07 PT - p2/demo-refresh - Reserve fixed-demo launcher profile before service refresh
- **Did:** user authorized continuing the checklist; synced d2cfbde and latest team asks. Starting stale demo deployment, estimate 10-15 min. No owner UI/policy edits.
- **Contract changes:** CLI-only --no-leases opts out of the old launcher's hardcoded lease setting for the fixed demo; incompatible with --voice. Existing CLI defaults remain. No endpoint or wire changes.
- **Heads-up for others:** refreshed Quick Tunnel gets a new URL; existing phone mic success is recorded, new-origin phone acceptance remains manual. Real provider source checks stay with Rayan; no key added/read by agent.
- **Next:** add the opt-out, rebuild current Yusuf frontend unchanged, refresh our owned demo processes and verify HTTPS/API/WSS/AI Lab/quiet preload.

### 2026-11-07 PT - p2/checklist-audit - Refresh Aziz checklist from latest plan, code and live service probes
- **Did:** read current plan/team asks, pulled d2cfbde, distinguished implemented backend from UI/device/deployment acceptance. Recorded #81/#82 merged and new Rayan asset pack. Read-only port 8020 probe exposed an old running backend (no voice audio/TTS schema; AI Lab 404); no services, keys or feature flags changed.
- **Contract changes:** none. Queued G shortening, presenter/lease flow, scenario loader/player and unfinished paced soak explicitly; no new frontend/robot policy work assigned to Aziz.
- **Heads-up for others:** Yusuf owns rendering/PTT/phone integration; asset-pack README uses web/public copy, no new server mount assumed. Rayan owns model/map/policy/provider acceptance; G-only keyed dry run does not confirm Ask/ElevenLabs. Full checklist and estimates are in Now.
- **Next:** execute the queued backend items with an estimate and contract before each; restart/deployment acceptance remains distinct from merged code.

### 2026-11-07 PT - p2/sensor-camera - Publish implementation after early contract merge; keep handoff history aligned
- **Did:** fixed PR #81's history-only merge block and preserved all work logs. Detected #78 merged before implementation 6d77051 was pushed; opened a separate implementation follow-up after integrating main 811d17c. Yusuf's merged web and survivor-clearance integration imported unchanged. Same current history on both active Aziz branches prevents a repeat history-only conflict when either PR lands.
- **Contract changes:** none beyond the preposted actual sensor-frame contract; default off. Backend stream implementation has only the minimal onboard observation hook for Rayan review; no web or further planner policy changes.
- **Validation:** final full backend **404 passed, 1 skipped** (183.36 s), latest unchanged web build **737 modules passed**, diff check clean. Artifact branch runtime equals main; #81 changes only optional patch files/README and Aziz history.
- **Heads-up for others:** #78 contains only the early contract; use the new backend implementation PR. Yusuf owns renderer adoption; Rayan owns proposed route fitting. Rayan's request for a 3-sentence G briefing is queued separately, not bundled into this merge fix.
- **Next:** review/merge the two clearly separated PRs, then the queued backend briefing change.

### 2026-11-07 PT - p2/camera-owner-handoffs - Resolve handoff history overlap with current main
- **Did:** integrated main 811d17c, retained both the owner-handoff and backend implementation histories, and refreshed Now without restoring the old frontend ownership exception. Final handoff diff is documentation/patch artifacts only; runtime matches main.
- **Contract changes:** none. Clarified that #78 merged its early contract stage, while implementation 6d77051 still needs a new PR.
- **Heads-up for others:** Yusuf's merged camera work is imported unchanged; no owner-source edits. New Rayan dry-run G shortening ask read and queued separately.
- **Next:** push PR #81 resolution and open the backend implementation follow-up.

### 2026-11-07 PT - p2/sensor-camera - Backend-only actual observations; ownership restored
- **Did:** user clarified Aziz's role. Removed all frontend and extra route-policy edits from this PR, saved optional owner patches on separate p2/camera-owner-handoffs (83a6df3). Backend now exposes actual IO/detector samples on Reality only, with honest sim fallback and geometry-change invalidation; retains only the small robot observation hook for Rayan review. No robot behavior/route policy change.
- **Contract changes:** preposted DZ_SENSOR_VIEW frame/config contract implemented, default off. Camera is optional after reset/rubble/aftershock until the next normal robot sample; empty hits clears targets. No camera data in Command/phones/Gemini/radio. Yusuf owns the renderer and must integrate the contract himself.
- **Validation:** final backend **404 passed, 1 skipped** (100.03 s), 12 sensor regressions, camera-on fixed demo guard **10 passed**; restored committed web build passes (733 modules), Ruff/diff check pass. New trained model and plan integrated from main 0c5c823. No key or provider call.
- **Heads-up for others:** optional prototype/finding handoffs: https://github.com/Rayan1092/Deadzone/tree/p2/camera-owner-handoffs/outputs/handoffs . Yusuf: Ctrl+R can also fire director R in current keyboard handler; please exclude modifiers. Rayan: extra route fitting patch/test shows 60-point thinning can cut walls; no such policy edits in this backend PR. Temporary camera preview stopped; stable phone tunnel untouched.
- **Next:** backend PR #78 review; Yusuf handles UI and Rayan robot-policy improvements. Do not merge the handoff artifact branch as a feature.

### 2026-11-07 PT - p2/sensor-camera - Reserve actual sensor-frame camera contract
- **Did:** audited current and Yusuf's unmerged camera: independent detection pan, lens/range mismatch, and metadata-based inferred classifications. User explicitly asked for robot/web fixes; ownership exception is task-scoped.
- **Contract changes:** additive Reality-only camera/config fields and `DZ_SENSOR_VIEW=1` exactly as in Now, posted before code. No new phone/Command/DTN access, no video claim or rendered-frame model input.
- **Heads-up for others:** Yusuf: dedicated sensor component will avoid touching your unmerged visual assets/models. Rayan: actual IO observations only, no truth reads in robot code; demo default remains unchanged.
- **Next:** implement/test range/FOV/occlusion/fallback/reset/privacy and visual camera alignment; review additional route safety.

### 2026-11-07 PT - p2/exploration-progress - Robots enter rooms and keep route progress
- **Did:** camera-view coverage replaces mapped-only search completion under the preposted flag; committed reachable goals, arrival sweeps, delivered-peer coverage and safe permanent waypoint lookahead reduce repeated travel. New plans/commands preempt old goals. Fixed false STUCK after intentional turns; real stalls still fault. User explicitly authorized robot-owned code. Pulled main `68dcfd2`, including Rayan generator/route cap and voice #72; no owner web/ML/map edits.
- **Contract changes:** only the reserved `DZ_EXPLORATION_V2=1`, default off. Same messages, no truth access; fixed default DEMO guard green. Operator example flag added without a key. Local preview http://127.0.0.1:8022 is paused, trained model/3 robots/valid ROOM-PREVIEW plan dispatched; existing phone tunnel untouched.
- **Validation:** final full backend **392 passed, 1 opt-in soak skipped** (145.87 s); final focused **58 passed**, including 14 new room-entry/safety/command regressions. Ruff and diff check pass. Assigned seed-7 comparison: coverage 90.6->98.3%, repeat entries 197->116, graph searches 445->58, all 3 found by 119 s (old: 2 by 240). Generated gen_1: all 3 by 253.3 vs 325.6 s, coverage 93.1->99.1%. Clinic also passes. No final comparison faults. Unassigned default-map last discovery remains later (223.9 vs 200.4); no claim every discovery is faster, no new paced 10x soak claim. Raw comparisons in validation/exploration-*.json.
- **Heads-up for others:** Rayan: please review robot policy and run opted-in dry run before enabling for presentation; legacy benchmark/DEMO stays unchanged by default. Voice #72 is merged; Rayan A1 status now resolved, A2 presenter/lease UI still applies. No real provider/key used. Scenario loader/timeline integration is separate follow-up.
- **Next:** publish PR and await Rayan/testing-laptop review; keep features default off until acceptance.

### 2026-11-07 PT - p2/exploration-progress - Reproduce doorway looping and reserve opt-in fix
- **Did:** user asked to prioritize robot logic/quality. Read planner/control/map code; nearest frontier representative can already be within arrival tolerance, periodic replanning churns goals, and lidar map coverage is mistaken for camera search coverage.
- **Contract changes:** opt-in DZ_EXPLORATION_V2=1, default DEMO untouched, no messages or truth access. User explicitly requests robot code edits for this task.
- **Heads-up for others:** Rayan: improving local-map exploration/route progress under this flag; battery/lost-link/fault behavior stays enforced. No benchmark/physics change by default.
- **Next:** measure baseline, implement/test room entry and stable safe routes, compare behavior, then PR.

### 2026-11-07 PT - p2/voice-pipeline - Recheck Rayan completed voice work against main
- **Did:** user asked to pull/check Rayan's completed voice. Fetched all refs and merged origin/main (already current). Confirmed #64 merged, 22ad945 robot code identical on main/current branch. Read latest robot/ML/frontend handoffs and open PR states. Fresh robot voice + our pipeline + leases + trained demo guard: **40 passed** in 43.36 s.
- **Contract changes:** none. Rayan robot commands/ack are complete; backend implementation remains PR #72 pending review/merge. Main currently responds 501 voice_not_ready to a valid voice holder, since #69 carried the pre-code contract stage only.
- **Heads-up for others:** Rayan/Yusuf: #72 must land for the real endpoint/STT/intent/ack/TTS bridge, then do keyed/UI acceptance. Do not treat merged robot-side #64 as end-to-end phone voice acceptance. Inspected pushed histories have no newer keyed voice dry-run result; no real keys used here. New retrain notes are unrelated to voice and remain unmerged.
- **Next:** #72 review/merge and frontend/keyed acceptance; no duplicate robot work or code changes needed from this audit.

### 2026-11-07 PT - p2/voice-pipeline - Publish PR 72 and complete requested clinic selector review
- **Did:** voice pipeline pushed as PR #72, no uncommitted runtime changes. Read newly pushed disaster/clinic-map/retrain histories at final sync. Accepted Yusuf's backend config review: exact loader block applied in memory to current backend, default/reset/privacy checks pass; clinic all three survivors and routes delivered by 161.6 sim s. Raw evidence committed, no branch/map/model edits or merge performed.
- **Contract changes:** none to voice after the preposted implementation. Yusuf's proposed DZ_FLOORPLAN remains startup-only, relative to repo ROOT; clear before fixed demo. Rayan retains map ownership/review. Actual dynamic scenario loader/event timeline contract is still upcoming, so none invented.
- **Heads-up for others:** Yusuf/Rayan: no backend blocker for clinic selector; merge its small ROOT/config hunk with current voice imports. New retrain branch was read (five curve points) but remains unmerged and unvalidated here; current main's curve is pending. Voice #72 and VOICE.md ready for PTT/lease/playback UI + keyed provider dry run. AI Lab held-out-label finding remains in Now.
- **Next:** review/merge #72 and owner clinic/model PRs, testing-laptop provider/UI acceptance, then scenario integration when Rayan posts the format. Continue team-sync before tasks and every 30 minutes while working.

### 2026-11-07 PT - p2/voice-pipeline - Full backend voice path and merged-team integration verified
- **Did:** implemented preposted STT/intent/manual/safety/lease/DTN/ack/TTS contract, default gated, no keys used. Synced again and pulled AI Lab exports and latest collapse/L/K/D UI. Full suite **354 passed, 1 skipped** (86.41 s), latest build passed (733 modules), every one of 46 AI Lab image URLs served. Phone mic success recorded as user-reported venue acceptance.
- **Contract changes:** preposted VOICE.md now implemented, including hello.voice.enabled. Actual command_ack_reported reaches phones/screens only after Command delivery; latest command_acks in delivered views, bounded caches/idempotency and strict stale-grant/reset checks. TTS accepts delivered cmd_id only; labelled browser fallback. Added explicit --voice/--gemini tunnel opt-ins; defaults off. CONTROL-LEASES/HTTPS docs updated from obsolete 501 stub.
- **Heads-up for others:** Rayan: priority and ack receiver delivered; unknown command's refused/bad_command response preserved. Live actual-network dark R2 command: 127.0 issued, 143.2 reported, 16.2 s late, no early speech. Providers mocked; keyed source verification still yours. Yusuf: see VOICE.md for PTT/lease/UI integration; fix AILab.jsx:154 Training examples label because exported images are held-out, as lab.note says. Curve remains honestly pending. No robot/ML/web source edits by Aziz.
- **Next:** push/open separate voice PR; actual keyed/provider and two-phone UI dry run after frontend integration. Scenario loader/timeline contract still awaits Rayan; no speculative event schema or planner optimization.

### 2026-11-07 PT - p2/voice-pipeline - Reserve launcher opt-ins after full regression
- **Did:** core pipeline, actual ack delivery and provider mocks pass full suite **348 passed, 1 skipped**; latest merged frontend build passes. Corrected ack validation to preserve Rayan's refused unknown-command responses while accepting only whitelisted actions as accepted/completed. No robot tests/source edited.
- **Contract changes:** before script code, reserve launcher --voice and --gemini explicit opt-ins; defaults remain off. TTS cache bounded to 32 delivered ack versions per reset epoch.
- **Heads-up for others:** Rayan's robot refusal/dedupe and dark-ack tests now pass unchanged. Yusuf can use VOICE.md; physical mic success is confirmed by user, actual provider keys/sources still testing-laptop acceptance.
- **Next:** add opt-in flags, run real loopback HTTP/WS manual-command/late-ack checks without keys, final sync/push PR.

### 2026-11-07 PT - p2/voice-pipeline - Record phone mic pass and publish complete voice contract
- **Did:** user confirms mic check works; venue HTTPS/WSS + real phone recording/playback preflight accepted. Pulled main f35f86d, read updated team-sync rule and all team histories. Rayan robot voice commands/ack and Yusuf Ask/spoken G/B/route replacement are merged. Next backend gap is the full voice pipeline.
- **Contract changes:** docs/VOICE.md posted before code: /api/voice JSON transcript; /api/voice/audio bounded raw recording; five typed manual actions; current lease grant recheck after async work; prior/Command SafetyChecker; actual DTN command and delivered-only command_ack_reported to phones/screens; /api/voice/tts from delivered ack only, ElevenLabs/browser labels. Guarded DZ_VOICE=1; G/Ask remain read-only.
- **Heads-up for others:** Yusuf can build from VOICE.md now; keep five-second heartbeats while waiting and play only delivered ack speech. Rayan: command_ack priority/receive work accepted, your payload unchanged. No Gemini/ElevenLabs key inserted or actual provider call; keyed dry run remains testing-laptop work.
- **Next:** implement/test full backend voice path (75-100 min), periodically sync, keep default demo guard green, publish separate PR.

### 2026-11-07 PT - p2/voice-leases-tunnel - Venue laptop connectivity confirmed and reprobed
- **Did:** user confirmed the laptop is already on venue Wi-Fi and a phone is available. Repeated the public HTTPS/WSS probe read-only, without claims/reset/robot commands: all checks pass. Recorded venue context and raw result in validation/venue-https-2026-11-07.json.
- **Contract changes:** none.
- **Heads-up for others:** laptop-side venue connectivity now verified; physical phone microphone permission/record/playback remains pending actual user confirmation. Current /mic-check link was provided. No audio uploaded or key used; do not infer phone/browser acceptance from this probe.
- **Next:** record the phone outcome and troubleshoot any actual venue/browser failure. PR #66 remains open; no runtime changes or regression rerun needed for this evidence update.

### 2026-11-07 PT - p2/voice-leases-tunnel - Publish PR 66 and final committed tunnel probe
- **Did:** pushed implementation as #66 stacked on #60; refreshed both branches with already-tested main without changing runtime. Final full suite 329 passed, 1 opt-in skipped in 166.82 s; focused 46 passed. Restarted final committed backend/tunnel and repeated HTTPS/WSS/exclusive-controller probe successfully. Launcher left running for physical phone preflight; state/credential ignored and removed on stop.
- **Contract changes:** none after preposted implementation. See CONTROL-LEASES.md for controller API/private bearer and free-only presenter override; HTTPS-DEMO.md for launcher/venue procedure. Phone microphone is a manual local-record diagnostic, not the full voice pipeline.
- **Heads-up for others:** Yusuf: #66 ready for picker/5-second heartbeat/token/override integration; public hello has lease state, private per-socket initial hello has token, subsequent public hello must not erase the in-memory token. Strip bearer fields from recordings. Rayan voice command/ack contract read; future voice enqueue must recheck leases after async work. Presenter credential stayed on loopback; public credential test rejected by approval review and replaced by successful local test. Venue/physical mic still unverified, no API keys used.
- **Next:** #60 then #66 review/merge and testing-laptop/UI/device dry runs. Open current /mic-check on a real venue-Wi-Fi phone and report permission/playback. Full voice pipeline is a separate follow-up.

### 2026-11-07 PT - p2/voice-leases-tunnel - Exclusive control and public HTTPS/WSS verified
- **Did:** implemented posted claim/release/heartbeat/expiry/free-only presenter override, private WS controller sessions, public lease broadcasts, REST/screen direct-command guard and protected voice boundary. Added portable SHA-verified cloudflared launcher, same-origin QR, public HTTPS/WSS probe and manual local-record mic page. New docs carry exact frontend contracts. Pulled #62 route recompute and read newly posted voice bundle/ack contract; full voice pipeline remains separate.
- **Contract changes:** implements the preposted contracts; docs/CONTROL-LEASES.md and HTTPS-DEMO.md have endpoint shapes/flags/errors and venue checklist. Voice deliberately returns 501 for holders until the full pipeline is wired; never invents a robot ack. Presenter uses local screen so bearer stays on loopback. Planning stays shared; no forced takeover/socket kick.
- **Heads-up for others:** Yusuf needs picker/5-second heartbeats/private tokens/presenter UI and replay credential redaction. 46 focused regressions pass; final full suite **329 passed, 1 skipped** in 166.82 s including updated S1 reroute beat and lease/reset race. Public HTTPS/WSS + exclusive controls passed; real expiry 15.031 s paused. Presenter override passed locally after automatic approval review rejected public bearer-token transmission. Venue Wi-Fi/physical mic still pending user/device test, not claimed complete. No API key used.
- **Next:** push implementation PR, leave current tunnel ready for the manual phone check. Rayan voice-action contract now exists; full STT/intent/safety/ack/TTS follow-up can build against it.

### 2026-11-07 PT - p2/voice-leases-tunnel - Refine microphone preflight contract before code
- **Did:** first focused lease run 44 passed, including competing claims/spoofing/expiry/direct paths. Frontend already uses same-origin API/WSS. Official Cloudflare portable release metadata provides SHA256 for verified project-local installation.
- **Contract changes:** reserved gated /mic-check manual five-second local-record/playback page and launcher/probe CLIs above; no recorded audio upload or full voice behavior implied.
- **Heads-up for others:** venue/device recording needs a person with the real phone; backend/tunnel checks cannot establish microphone permission. Voice remains off pending pipeline contract/dry run.
- **Next:** portable launcher, HTTPS/WSS probe and docs, then combined regressions and publish.

### 2026-11-07 PT - p2/voice-leases-tunnel - Publish exclusive-control and HTTPS contracts
- **Did:** synced main 5177aba and read the new Voice control section. Audited existing direct paths: resume and all-robot mode; fault/director injections and shared plans stay separate. No voice handler or robot voice action/ack contract yet.
- **Contract changes:** reserved lease endpoints/private WS token/public state above, 15-second monotonic expiry, explicit free-only presenter override, protected direct/voice boundaries, and one-origin Cloudflare launcher/probe. Contract posted before implementation for Yusuf.
- **Heads-up for others:** Yusuf: heartbeat every 5 wall seconds, show controller name/disabled claims, keep token private, reconnect requires reclaim. Presenter token must be entered only on presenter screen. Voice holder gets 501 until pipeline is implemented, never a fake robot reply. Rayan: robot voice bundle/ack shape still needed for full pipeline, demo unchanged by default.
- **Next:** build/test lease exclusivity and bypass coverage, install/start/probe portable tunnel here; record venue/device checks as pending if this is not venue Wi-Fi.

### 2026-11-07 PT - p2/ai-lab-assets - Acknowledge seeded generator and asset-bundle handoff
- **Did:** ran team-sync and inspected current Sim/director hooks. No newer main code or posted scenario loader/timeline contract at this fetch; PR #60 remains open. Existing static export folder support covers proposed AI Lab JSON/images.
- **Contract changes:** none. Clarified relay_destroyed is emitted by aftershock, not an accepted do action. Waiting for Rayan's actual loading/playback contract before implementation; no new endpoint or event shape promised prematurely.
- **Heads-up for others:** Rayan: include loader entry point/data format, seed selection, sim-time event ordering/reset semantics and handling of relays not yet created. Fixed demo remains untouched; scenario mode opt-in. Put AI Lab JSON/images under ml/results for /ai-lab/results URLs, keeping labels/metrics real; existing docs define file types/gate.
- **Next:** read Rayan's posted contract, estimate integration before building, implement/test owned backend glue in a separate PR if needed. Last runtime validation remains 314 passed, 1 opt-in skipped; this update is documentation only.

### 2026-11-07 PT - p2/ai-lab-assets - Publish PR 60 and clarify AI-eye asset contract
- **Did:** pushed implementation/report as PR #60. Final fetch found no newer main code; read Yusuf's new plan-only p3/ai-eye branch. Left verified local paused preview with quiet P-1 and optional flags off. No additional runtime changes since 314-pass suite/build/live checks.
- **Contract changes:** none; clarified existing heatmap event vs manifest heatmap_alpha fields and confirmed proposed lab.json/lab/*.png paths need no server schema change. No invented exports or curve.
- **Heads-up for others:** Yusuf: alpha is not currently an event field; use blended event heatmap or the manifest in Reality/AI Lab, preserving delivered-only Command. Rayan owns lab export values/split labels; keyed G/Ask still yours. #60 ready for review; #58 merged.
- **Next:** testing-laptop optional-feature acceptance and teammate UI/export work; backend remains ready with existing gates. Planner optimization remains deferred, 10x pace not passed.

### 2026-11-07 PT - p2/ai-lab-assets - Read-only exports and final integration report
- **Did:** implemented the preposted gated asset mounts, JSON/image allowlist and normal static path boundaries; no writes/listing. Eight focused tests passed. Final combined suite **314 passed, 1 skipped**, including trained-model DEMO guard; latest web production build passed. Live HTTP/WS integration including AI Lab passed; reusable harness and raw result updated.
- **Contract changes:** implements #59 contract, docs/AI-LAB.md has exact URLs and export responsibilities. Static training evidence never becomes live Command or Gemini input. Full report records implemented backend versus pending UI/device acceptance and honestly failed 10x pace criterion.
- **Heads-up for others:** Rayan: export curves/examples/manifest under ml/results with your schema/split labels; Yusuf: URLs available behind DZ_AI_LAB=1 for L overlay. #58 ordering code is now merged. No key/API calls or robot/ML/web source edits. Feature gates remain default off.
- **Next:** push implementation PR, leave a clean paused local preview, then testing-laptop acceptance owned above. No planner optimization or scenario physics started.

### 2026-11-07 PT - p2/ai-lab-assets - Publish read-only AI Lab contract before code
- **Did:** ordering implementation is pushed as PR #58. Accepted new PLAN AI Lab backend serving task; estimate 15-25 minutes, no robot/planner or visual-shell changes.
- **Contract changes:** reserved gated /ai-lab/results and /ai-lab/slides export paths above; only JSON/images, GET/HEAD, default 404. Rayan owns exported training evidence and schema; Yusuf owns overlay. Existing metrics/confusion matrix are already available in repo, curve/examples exports still pending.
- **Heads-up for others:** no key or Gemini calls; no model weights, dataset or environment files exposed. Existing feature gates/demo guard remain required. PR #58 contains ordering code; #55 was contract only.
- **Next:** implement serving, test feature gate/path boundaries/methods, build latest web, run full regression and finish integration report.

### 2026-11-07 PT - p2/plan-publication-order - Serialize drafts and verify live integration
- **Did:** lifetime Hub lock now orders legacy/CRDT draft writes, checks, dispatch and reset through publication. Three regressions reproduced stale phone/screen state before the fix and pass afterward. Added a reusable loopback HTTP/WS check script and raw enabled-feature evidence. Full suite 306 passed, 1 skipped; trained-model demo guard green.
- **Contract changes:** implements the preposted ordering guarantee; no wire/schema changes. CO-PLANNING.md documents publication ordering. No feature gates changed.
- **Heads-up for others:** merged main ee3057f, A-key aftershock and latest AI Lab/visual plan. #54 and contract-only #55 are merged; the actual ordering code needs a new PR. Physical phones, keyed Gemini and paced 10x remain unverified; planner speedup deferred by Rayan.
- **Next:** publish ordering implementation, then gated read-only AI Lab assets and full integration report.

### 2026-11-07 PT - p2/plan-publication-order - Reproduce stale plan race and reserve ordering fix
- **Did:** refreshed team histories/PLAN and fetched main (unchanged at 8f77d3c). Frontend production build passes. A deterministic slow-phone reproduction applied budget 90 then 120: server current 120, published plan_state sequence [120,90], leaving the phone stale.
- **Contract changes:** no wire shapes. Reserved transaction/publication ordering across plan writes, checks/dispatch and reset before implementation; same lock survives reset. Existing flags, Command-only data boundary and demo guard remain.
- **Heads-up for others:** Yusuf: this fixes server ordering without requiring a frontend workaround. Rayan: key ownership and robot route recompute stay yours. PR #54 still open; this fix will have a separate PR.
- **Next:** implement locking, prove slow-phone/reset regressions, run real HTTP/WS plus enabled-feature checks, full suite, and publish a full integration report.

### 2026-11-07 PT - p2/soak-mode-sync - Exact action/mode compatibility verified
- **Did:** REST and screen WS now normalize Rayan's `{action:"mode",mode:...}` and existing action/value messages through the same path. Both call set_mode on every robot; conflicting aliases reject before mutation. Full suite **303 passed, 1 skipped**, including the trained-model demo guard; focused mode/screen suite 45 passed. No key added/used and no toggle enabled.
- **Contract changes:** the previously posted mode alias is implemented; matching duplicate fields accepted, conflicting fields return invalid_mode. Responses/hello/reset behavior unchanged from the existing mode feature. SOAK-AND-MODE.md documents both shapes and Rayan's key ownership.
- **Heads-up for others:** Rayan owns API-key creation and keyed G/Ask verification on the testing laptop, reports source gemini himself. IO-only aftershock accepted, route recompute/resend stays robot-owned and existing newer-t receive path needs no change. Grad-CAM heatmap fields and completed review/soak already validated.
- **Next:** push review update; wait for Rayan's keyed dry-run results and Yusuf's UI/device dry runs, with the existing feature toggles retained.

### 2026-11-07 PT - p2/soak-mode-sync - Acknowledge Rayan sync and publish exact mode alias
- **Did:** ran /team-sync; no new fetched main commits beyond 8f77d3c. Read team histories and checked every forwarded ask against the implemented backend. Rayan owns the key and live source verification; no key added or used by Aziz. Aftershock/heatmap/route replacement contracts already fit; review and scripted soak have already passed locally.
- **Contract changes:** before implementation, reserved the exact action/mode control shape above alongside action/value. Reject conflicting aliases before mutation; REST and screen WS share normalization.
- **Heads-up for others:** Yusuf may use either mode field shape. Rayan: no backend work is needed for route recompute/resend; newer delivered t already replaces the route and emits rescue_route_reported. Existing feature toggles and demo guard remain required.
- **Next:** implement alias, run full suite including demo guard, push update to PR #54. Rayan performs keyed Gemini dry run on testing laptop.

### 2026-11-07 PT ? p2/soak-mode-sync ? Final push/pull verification, PR #54
- **Did:** pushed final integration code as PR #54. Pulled latest main through 8f77d3c and re-read Rayan/Yusuf updates. Last incoming change labels benchmark/Devpost numbers as simulation and updates the benchmark renderer; no server runtime changes after the 295-pass regression. Latest frontend build passes; Rayan's opt-in soak separately passes.
- **Contract changes:** none beyond the already posted mode field/action. Rayan is now building route-recompute; existing newer-t delivered route replacement already supports it, including rescue-order refresh after delivery.
- **Heads-up for others:** all shared benchmark figures must say "in simulation" (#48). Final code/evidence and full checklist are in #54 / Now. Gemini live-key/device dry runs and paced exploration throughput remain explicit limits, not claimed complete. No robot/web/ML policy edits by Aziz.
- **Next:** review/merge #54, then testing-laptop dry runs with each toggle; Rayan owns planner performance and route recompute, Yusuf owns phone/control display integration.

### 2026-11-07 PT ? p2/soak-mode-sync ? Final team integration and measured soak evidence
- **Did:** pulled current Grad-CAM and realism/dynamic-wall work, installed locked frontend dependencies and built it successfully. Live all-robot mode control implemented and 7 focused tests passed. Imported Rayan's offered soak test unchanged and ran it: 1 passed, 1200 sim s / 73 wall s, 4622 events, flat ~326 MiB RSS. Added opt-in paced Hub runner with raw metrics; that separate default-demo-plan run passed memory/stability but achieved 7.654x, not target 10x.
- **Contract changes:** previously posted action/value mode control now implemented; mode added to screen hello/control and REST control replies. Invalid value rejected before any robot changes. SOAK-AND-MODE.md and validation JSONs distinguish scripted stress throughput from paced actual rate. Bad rescue routes now warn with ID/reason (no message shape or payload disclosure).
- **Heads-up for others:** Rayan: accepted review is read; route/heatmap receive side matches, logging finding addressed, planner profile/handoff in Now. Yusuf: dynamic_walls rendering confirmed merged; latest production build passes. Keyed Gemini/phone UI/device dry runs still pending; no source edits in your areas. Final combined regression: **295 passed, 1 skipped** (soak opt-in; separately 1 passed in 73.13 s). Latest frontend production build passed.
- **Next:** finish full suite, push code/evidence and open final follow-up PR against latest main. No PR merges performed by Aziz during this work.

### 2026-11-07 PT ? p2/soak-mode-sync ? Live baseline control and paced soak contract before code
- **Did:** rescue ordering is pushed as PR #50 (283 tests and frontend build passed). Final integration follow-up accepts Rayan's newly merged live-mode request while running the outstanding soak.
- **Contract changes:** screen WS `{t:"control",data:{action:"mode",value:"baseline"|"deadzone"}}` and REST POST /api/control use the existing standard action/value shape. Calls set_mode on every robot only after validating value; screen hello/control and REST control result add mode. Initial/reset mode follows DZ_MODE; default deadzone unchanged. Explicit control/key is the opt-in, no Gemini/phone tool receives this capability. Yusuf owns the key/chip and WAITING_FOR_LINK label.
- **Heads-up for others:** Rayan: test_soak.py remains yours per accepted offer; I will add/run `scripts/soak.py` in Aziz's scripts area to exercise the real Hub loop and record process RSS/actual pace, avoiding duplicate ownership. 1200 sim seconds, target 10x, trained detector, fixed demo plan, default features, <500 decimal MB peak RSS. Output records actual duration/speed/memory; no claim of a 20-minute wall-clock run. Runner is opt-in CLI only.
- **Next:** publish this contract before implementing; run combined tests, paced soak and final sync/push.

### 2026-11-07 PT ? p2/rescue-order ? Delivered route ranking and latest team sync
- **Did:** implemented gated rescue-order endpoint from delivered survivors/routes, sampled Command occupancy and public hazard prior only; no truth/live robot fallback. Stable risk reasons/order and API docs included. Full suite **283 passed** with Rayan baseline merged, including the trained-model demo guard; focused rescue-order tests 5 passed. Current frontend production build passed.
- **Contract changes:** reserved GET /api/rescue-order contract is now implemented behind DZ_RESCUE_ORDER=1; documented in RESCUE-ORDER.md and PHONE-PLANNING.md.
- **Heads-up for others:** pulled main `1a7610a`, including baseline robot mode WAITING_FOR_LINK, mode telemetry/events, benchmark and Rayan's live-toggle request. No newer PLAN changes at this sync. I accept the backend live-toggle task and will post its exact standard control envelope before code; Yusuf owns the key/chip. Rayan's soak/review offers remain accepted; no soak test was published yet.
- **Next:** rerun combined tests with baseline, publish rescue-order PR, run measured 1,200-sim-second/10x soak, then live mode control follow-up.

### 2026-11-07 PT ? p2/rescue-order ? Finalize route-risk thresholds before code
- **Did:** rescue ordering next; no route generation or truth fallbacks.
- **Contract changes:** refined reserved GET /api/rescue-order risk thresholds in Now before implementation. High: delivered obstruction/public hazard/clearance <0.25m; medium: unknown or <0.5m clearance, source route age >60s. Sampling <=half a cell; stable reasons codes. Returns only delivered survivors with delivered routes; sorts risk, length, ID. Gated DZ_RESCUE_ORDER=1.
- **Heads-up for others:** Yusuf owns the phone list. This is route risk evidence, not medical triage or a safe-route guarantee; delivered data may be stale. No Command/live link mixing.
- **Next:** implement/test leakage and ordering, then run the 20-minute-sim/10x soak.

### 2026-11-07 PT · p2/plan-crdt · Offline field merging with explicit conflict state
- **Did:** gated seed/read/merge REST endpoints, compact per-field LWW registers, atomic polygons, tombstones, Lamport tie-break, idempotent replay and epoch protection. Invalid merged whole-plan candidates converge visibly and block checks/dispatch; valid candidates broadcast normal plan_state, planner phones receive plan_sync. Full suite **272 passed**, including trained-model demo guard; focused CRDT/phone suite 32 passed.
- **Contract changes:** refined reserved contract implemented behind DZ_CRDT=1. Typed operations, 256-op batches/1024-register bound, stale epoch/clock-reuse errors, dispatched-ID immutability and whole-plan/reset invalidation. CO-PLANNING.md documents client persistence/reconnect algorithm. No robot/control/Command truth access.
- **Heads-up for others:** Yusuf: backend is ready; browser offline storage, local merge queue, conflict UI and two-phone dry run remain yours. Invalid candidates must not be treated as safety approval. Contract-only PR #45 landed before implementation; this implementation needs its own review because the server code was not in that PR.
- **Next:** publish implementation separately against current main, then delivered-route rescue ordering and the soak run.

### 2026-11-07 PT ? p2/plan-crdt ? Resolve validation conflicts explicitly before implementation
- **Did:** refining reserved co-planning contract before code so concurrent edits cannot be silently discarded or accidentally dispatch an old draft.
- **Contract changes:** sync responses/phone plan_sync include valid/issues. Register merge is retained even if the materialized whole plan is invalid; no plan_state or safety approval is emitted, and check/dispatch returns 409 plan_conflict until resolved. Epochs protect reset/whole-plan replacement; bounded winning registers and Lamport counter requirements are in Now. This is per-field LWW-map CRDT semantics, with polygons atomic and region tombstones.
- **Heads-up for others:** Yusuf: persist epoch + winning ops + local pending ops, merge by (counter,client), show invalid candidates/issues, and GET/rebase on sync_epoch. Never PUT just to reconnect, because PUT intentionally invalidates other offline clients. No phone UI edited by Aziz.
- **Next:** implement gated endpoints and validate two offline authors reconnecting in both orders.

### 2026-11-07 PT ? p2/reed-solomon ? Actual RS bytes, repair counters and custody retry
- **Did:** actual serialized payloads (including typed numpy maps) are encoded with reedsolo RS(255,223), corrupted through a separate seeded byte-error channel, decoded and CRC32 checked before delivery. Parity/CRC consume shared bandwidth; failed decode retains custody for retry; interrupted frames are cleared. No original-payload shortcut. Full suite **257 passed**, including the trained-model demo guard; FEC/DTN focused suite 37 passed.
- **Contract changes:** reserved DZ_FEC=1 contract implemented. Reality links add per-tick corrupted_bytes/corrected_bytes/fec_failed_blocks, zero idle/disabled, with fec reflecting actual enabled weak-link coding. Counts appear on complete decode attempts; Command/phones never receive live repair stats. DTN.md documents wire/noise/stat semantics. Dependency reedsolo==1.7.0.
- **Heads-up for others:** Yusuf: repair-line animation can consume these counters. Feature remains off for the normal demo until dry run. Pure-Python 8.9 KB payload encode/decode measured ~41 ms here, so check enabled-mode frame budget on the testing laptop; no 10x performance claim yet. Strong/disabled paths retain legacy transport.
- **Next:** publish FEC separately, then CRDT offline co-planning server support and rescue ordering; Rayan's accepted soak help remains pending.

### 2026-11-07 PT · p2/aftershock · Gated collapse, permanent relay loss and rerouting
- **Did:** aftershock adds real rubble/occupancy and concrete wall/radio loss, permanently destroys a relay and its custody/partial transfers, and lets surviving custodians reroute. Atomic input validation; destroyed relays cannot move/power/reconnect into service. Existing maps/robot policy remain delivery/IO-bound. Full suite **248 passed**, including the complete trained-model demo guard; seven new collapse tests passed.
- **Contract changes:** reserved director/event/dynamic_walls contract above is implemented behind DZ_AFTERSHOCK=1. Details and error codes in AFTERSHOCK.md. Defaults and reset behavior verified; no default demo changes.
- **Heads-up for others:** Yusuf: wire A and Reality-only dynamic_walls; Command inset public walls remain clean. Rayan: normal IO sees changes, no robot state is injected; add reactions in your area if needed. Testing-laptop dry run remains pending.
- **Next:** publish own aftershock PR, then real Reed-Solomon. Rayan's accepted soak/test-review work remains separate and pending.

### 2026-11-07 PT ? p2/aftershock ? Finalize Reality-only wall contract before code
- **Did:** preparing aftershock next; briefing #39 is merged, Ask #40 open. Existing pure Command inset draws hello.floorplan.walls, so runtime collapse walls will use a separate dynamic_walls collection rather than leak into that public prior.
- **Contract changes:** reserved aftershock contract refined before implementation: new walls in screen hello.floorplan.dynamic_walls, excluded from phone prior and Command inset; wall shape and Sim hook in Now. Yusuf: A is available for this gated event, draw new walls only in Reality. App remains gated by DZ_AFTERSHOCK=1.
- **Heads-up for others:** Rayan: robot reactions must use normal lidar/collision/radio IO; destroyed relay queue is lost, other custody retained. No robot state injection. Both your review/soak offers are accepted above.
- **Next:** implement and verify destruction, atomic validation, truth-only geometry and network rerouting; keep the demo guard unchanged.

### 2026-11-07 PT · p2/gemini-ask · Phone questions through the same Command tools
- **Did:** private `POST /api/ask` validates/trims free-text questions, calls the same six read-only Gemini tools and deadline, and returns a source-labelled answer. Unavailable Gemini explicitly returns a local summary rather than pretending to answer. No screen broadcast, plan edits or commands. Full backend suite **241 passed**, including all nine newly merged demo-guard checks and trained-model radiator rejection. Focused Ask/report tests: 30 passed.
- **Contract changes:** reserved Ask contract now implemented: `{question}` (1-1000 chars, no extra fields) -> `{text,generated_at,source}`; invalid input 422, reset in flight 409 `report_reset`. Same ignored server/.env and opt-in DZ_GEMINI=1. Public docs: GEMINI.md and PHONE-PLANNING.md.
- **Heads-up for others:** Yusuf: endpoint ready for your phone box and speech; no web files edited by Aziz. Rayan: latest main #36 demo guard remains green; quiet #37 is merged. Both #28 review and soak offers remain accepted. Real keyed API/testing-laptop dry run still pending; no key committed. Aftershock/FEC/CRDT/rescue-order contracts are reserved, not yet shipped.
- **Next:** publish Ask separately on briefing PR #39; next backend feature is aftershock behind its own toggle; Gemini keyed dry run remains pending independently. Soak file remains Rayan-owned per accepted offer.

### 2026-11-07 PT ? p2/gemini-briefing ? Real read-only Gemini briefing, opt-in
- **Did:** G's existing endpoint now calls Gemini through six mandatory read-only Command tools (plus optional coverage) using gemini-3.8-flash, verified from official docs. Immutable snapshots, bounded delivered-only event/receipt journals, real function-response loop with IDs/thought signatures, one 10-second deadline, async HTTP and deterministic local fallback. server/.env loads without overriding process env; tracked .env.example has no secret. Full suite **222 passed** with the model; tests use mock HTTP, no live Gemini key.
- **Contract changes:** reserved report contract now implemented behind `DZ_GEMINI=1`; source stays `local` unless a complete Gemini reply follows the required tools. `GET /api/report` returns 409 `report_reset` if reset occurs mid-generation. Added setup/tool docs in GEMINI.md; no public Command/tick shape changes.
- **Heads-up for others:** Yusuf: existing G panel already reads source correctly; speech and phone box remain yours. Rayan: no robot policy/timing changed; Command event journal never reads Sim.events. Keyed API + testing-laptop full dry run still pending. Quiet-preload PR #37 is the parent of this PR; no merge done by Aziz.
- **Next:** publish separate briefing PR, then phone Ask endpoint in its own PR (same tools/deadline). Other Version 2 contracts remain reserved above.

### 2026-11-07 PT · p2/quiet-preload · Quiet save tested, Version 2 contracts reserved
- **Did:** opt-in quiet preload saves/broadcasts the draft without emitting safety results or accepting unsafe dispatch. Updated DEMO.md's preload command and phone API docs. Full backend suite: **202 passed**, trained model available. Initial sandbox run had temporary-directory permission errors; rerun with access passed. No web/robot files edited.
- **Contract changes:** `POST /api/plan?check=false` returns `{saved:true,plan_id,checked:false}`; default checks remain. Published the reserved Gemini/Ask, aftershock, FEC, CRDT and rescue-order contracts in Now before their implementation.
- **Heads-up for others:** Rayan: quiet query is ready; accepted your review and soak offers above. Yusuf: the opt-in wire-level quiet save works with your existing frontend filter. New tests verify no safety frames and fresh rejection on explicit submit/dispatch.
- **Next:** own PR for quiet preload; Gemini briefing next (then Ask in its own PR). Testing-laptop dry run still needed.

### 2026-11-07 PT · p2/quiet-preload · Version 2 audit and quiet-save contract before implementation
- **Did:** pulled and read PLAN v2 and teammate histories; audited backend against all seven requested Version 2 items. Existing DTN, delivered routes/plan state, detector status/crops, overload/resume and phone relays are present. Gemini, Ask, aftershock, real RS, CRDT, rescue ordering and soak are still pending. Yusuf already hides preload results in the UI (#35); explicit backend quiet-save avoids emitting them at all.
- **Contract changes:** the opt-in `POST /api/plan?check=false` contract in Now above is reserved before implementation. Default callers unchanged.
- **Heads-up for others:** Rayan: accepted both your #28 contract review and soak-test offer (file/scope in Now). Yusuf: quiet preload is additive; no web files changed. Browser replay already covers the backup recorder requirement.
- **Next:** implement/test quiet save, publish its own PR, then Gemini/Ask per priority unless the user explicitly chooses all other backend features first.

### 2026-11-07 15:26 PT · p2/detector-rescue-backend · Detection assets/status and delivered rescue route integration
- **Did:** added crop static serving, active detector metadata to both hello variants, priority-1 rescue transport/Command storage and dark-only beacon IO metadata. Pulled merged rescue/visual PRs #25/#26 and tested the real source together: full suite 198 passed with the CPU model, 198 passed with DETECTOR=sim; latest production web build passed. No robot/ML/floorplan/frontend source edits by Aziz.
- **Contract changes:** `/crops/<file>`; `hello.detector` + optional fallback reason; `command.routes` / phone routes retain one delivered record per survivor. Accepted wire names include user-agreed `survivor_id`/`beacon_id` and PR #25 `survivor`/`beacon` + clearance. **Arrival event uses `rescue_route_reported`, not the forwarded `rescue_route`, because the latter is already emitted before delivery by robot code.** It includes the canonical fields, reported_t and delay_s; view/events retain beacon/clearance aliases for published PR #25 clients. `relay_dropped` and delivered relay records gain nullable beacon_for. Full contract: `docs/BACKEND-SCOPE-HANDOFF.md`.
- **Heads-up for others:** PR #25's real S1 route has 95 sampled points, exceeding the agreed 60-point limit. Legacy adaptation removes only duplicate/collinear forward vertices (preserves every turn/reversal) before validating <=60; raw DTN byte accounting remains accurate. The initially failing real route delivery now passes. Rayan's one remaining call-site change for beacon_for is listed in Now; this backend does not infer labels or edit robot policy. Yusuf must draw Command routes from delivered routes, never the robot's Reality event.
- **Next:** publish and merge this tested backend work as the user authorized so teammates can pull/test; then later Gemini/FEC/recorder milestones.

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

### 2026-11-07 PT - p2/camera-owner-handoffs - Restore ownership boundaries
- **Did:** user clarified Aziz's role; removed all own frontend/proposed extra route-policy edits from backend working tree, preserved them only as optional owner patches. Restored committed frontend build and stopped experimental camera preview. Existing phone tunnel untouched.
- **Contract changes:** none beyond preposted backend sensor contract. No source code from this handoff branch should merge into main.
- **Heads-up for others:** Yusuf: modified browser shortcuts can trigger director R; see exact finding in outputs/handoffs/README.md. Rayan: 60-point thinning can cut walls; 4 passing route tests/proposed safe fitter in your patch. Both owner patches pass git apply --check against their stated bases; prototypes require owner integration/dry run.
- **Next:** finish backend-only #78; owner UI/policy implementation stays with Yusuf/Rayan.
