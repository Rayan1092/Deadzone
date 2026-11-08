# Aziz: backend + network (Person 2)

Owns `server/deadzone/sim.py`, `app.py`, `floorplan.py`, `network/`, `command/`. Only Aziz's sessions edit this file.

## Now
- **Working on:** p2/exploration-progress. User explicitly requests robot routing/exploration fixes: fewer repeated doorway visits, actually enter/sweep rooms. This authorizes changes in robot planner code for this task; no frontend/ML/map edits. Estimate 30-45 minutes. Synced main 4b210ab; voice integration remains PR #72 separately.
- **Contract before code:** DZ_EXPLORATION_V2=1 opts into progress-aware local-map exploration and camera sweep coverage; default legacy policy and fixed DEMO timings remain unchanged. No wire/schema changes, no truth/room/survivor location access in robot policy. Keep obstacle/fault/battery/lost-link protections. Measure coverage, repeated goals/backtracking, detection and planner cost before/after; meaningful regression tests and DEMO guard required.
- **Focus:** code/behavior and measurable route quality; only this required short handoff plus raw validation results, per user's request for less documentation. Prior voice code is already pushed/tested; this is a separate PR.

## Log

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
