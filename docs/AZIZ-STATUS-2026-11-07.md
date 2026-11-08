# Aziz's remaining work, November 7, 2026

Audit baseline: fetched `origin/main` at `21dd05d`, then merged it into
`p2/short-briefing`. Read the plan updates, all four team histories, recent merge
history, current open PRs, backend implementation/tests and frontend consumers.
This is a code and integration audit; it does not establish physical phone,
GPU, provider or current tunnel acceptance.

## What is already delivered

Aziz's original backend scope is implemented: deterministic simulation and sensor
IO, multi-wall radio, multi-hop DTN custody, delivered-only Command knowledge,
phone planning/safety/dispatch, quiet preload, director controls, Gemini G/Ask,
aftershock, Reed-Solomon, CRDT draft APIs, rescue ordering, AI Lab/crop serving,
exclusive leases, voice endpoints and delivered acknowledgement/TTS wiring.
Features remain subject to their individual flags and acceptance checks.

Recent merges checked against code:

| PR | Result relevant to Aziz |
| --- | --- |
| #72 | Voice backend implementation is merged; the older contract-only #69 is not the implementation. |
| #77 | Optional exploration policy is merged, default off; Rayan's new A1/A2 findings remain open. |
| #81 / #82 | Owner handoff patches and actual sensor-frame backend are merged. Renderer adoption remains Yusuf's work. |
| #83 / #87 | Asset pack and training-curve asset/review are merged. Assets live in `assets-pack/`; selected frontend adoption is Yusuf's choice. |
| #86 / #88 | #86 was the launcher contract; #88 merged the actual fixed-demo refresh and independent microphone preflight. |
| #85 | Latest visual/camera work and short spoken-report consumer are merged. Added `d3-delaunay`; local dependencies refreshed and build verified. |
| #89 | Short G implementation completed and validated in this branch; review pending. |

Older PLAN sections describe the original starter and still say several shipped
features are planned. Yusuf's and the ML history's `Now` sections also retain
some merged branches as in flight. Use actual commits/code plus newest log entries
to resolve those labels; do not edit another owner's history.

## Remaining queue

| Order | Work | Evidence and next action | Owner / estimate |
| --- | --- | --- | --- |
| 1 | Short G briefing | Implemented and validated here: existing `text`, at most 3 sentences / 45 words, digits; concise local fallback preserves uncertainty. Same 6 tools and 10 s deadline. Ask keeps separate behavior. #89 review pending. | Aziz; this change |
| 2 | Presenter B/U with leases enabled | `Hub.control` requires every robot lease for `mode` and the target lease for `resume`; `web/src/net/socket.js` sends no controller token. Presenter override only frees a lease. Agree explicit claim/heartbeat/release UI with Yusuf; never add an implicit bypass or forced takeover. | Aziz + Yusuf; 30–45 min backend/contract work plus UI/device acceptance |
| 3 | Optional exploration review fixes | Rayan A1: V2 `_follow` shortcuts use `_trav()` while planning uses `_drive_trav()`, so a shortcut can cross survivor clearance. A2: exhausted reachable viewpoints can return home without completing active `explore_zone`. Keep `DZ_EXPLORATION_V2=0`; changes are in Rayan's area and need his ownership coordination. | Rayan-owned code; Aziz follow-up from #77; estimate after agreement |
| 4 | Startup floorplan and generated timeline | `Hub.__init__` constructs default `Sim` without `DZ_FLOORPLAN`; live loop has no timeline playback. Generator and headless player already exist in `data/floorplans/generate.py`. Review clinic selection separately from a gated timeline; reset must select/replay consistently, keep hidden events off phone/prior, keep fixed preload/demo unchanged. | Aziz integration + Rayan map/player review; 45–60 min plus dry run |
| 5 | Paced 10× soak acceptance | Existing paced artifact is `ok:false`: 1,201 simulated s in 156.92 wall s = 7.654×. No exception and memory growth 9.62 MB pass, but pace does not. Scripted stress is a separate pass. Rayan has deferred planner optimization; do not relabel the paced result as complete. | Aziz measurement; Rayan planner changes if authorized; 15–25 min including analysis |
| 6 | Joint keyed/device checks | Verify Ask `source:gemini`, ElevenLabs STT/TTS sources or labelled fallback, two-phone exclusive leases, offline browser merge, delivered rescue-order display, FEC repair display, and actual sensor-frame renderer. G's earlier Gemini pass and microphone preflight do not prove these. | Aziz contracts, Yusuf UI, Rayan/user keys and test laptop |
| 7 | Release rehearsal | Recheck the active origin/process version after restart, run fixed seed-7 beats, confirm graphics on test GPU, record backup and rehearse the final script. Do not infer active deployment from a successful git merge/build. | Team; optional features stay off until accepted |

## Frontend dependencies found in source

- Phone draft handling still sends `plan_edit` and is held in memory; it does not
  consume `/api/plan-sync` or persist an offline operation queue.
- Phone/screen consumers have no lease picker/heartbeat or push-to-talk flow.
- No consumer of `hello.sensor_view` / `robot.camera` was found. The current
  `RobotEye` reconstructs boxes from Reality/crop metadata; adopting actual
  onboard observations remains separate work.
- Rescue ordering and FEC repair counters have backend contracts; their intended
  phone/link presentation is still pending.
- Yusuf's merged report panel speaks `short`, then `spoken`, then 3 sentences of
  `text`. This backend supplies concise `text`, so no new field is needed.

These are Yusuf's source areas, not missing Aziz endpoints. Rayan retains robot
policy, ML, generated maps and the long-route fitting handoff.

## Verification

Full backend suite: **413 passed, 1 opt-in soak skipped** in 91.33 s, including
the fixed-demo guard. Short-briefing focused suite: 69 passed. Merged frontend
production build: passed, 741 modules; existing large-chunk warning remains.
Pytest temporary-directory fixtures needed execution outside the sandbox; the
successful full run includes them. Diff check passed; Ruff is absent from this
venv. No live provider call, active deployment refresh or device acceptance is
claimed by this audit.
