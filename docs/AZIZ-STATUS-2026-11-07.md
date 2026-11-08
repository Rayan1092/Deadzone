# Aziz's remaining work, November 7, 2026

Current final-stretch status (supersedes the older audit queue below): synced
main 34cc4c5; all 6 backend items are implemented/verified in #90, and J/I are
implemented under PLAN.md's explicit Yusuf handoff. #89 is already merged.
Validation: 454 backend tests passed / 1 opt-in soak skipped, 6 frontend tests
passed, production build 745 modules passed. Preview: http://127.0.0.1:8030.
Exact implementation/acceptance: [FINAL-STRETCH-BACKEND.md](FINAL-STRETCH-BACKEND.md).
Actual judge pool and optional detector/met-deadline counters await Rayan's export;
presenter lease UI and joint device/GPU rehearsal remain distinct acceptance work.

Audit baseline: fetched `origin/main` at `21dd05d`, then merged it into
`p2/short-briefing`. Read the plan updates, all four team histories, recent merge
history, current open PRs, backend implementation/tests and frontend consumers.
This is a code and integration audit; it does not establish physical phone,
GPU, provider or current tunnel acceptance.

Presenter follow-up: branch `p2/presenter-leases` starts from main `3770032`,
including merged #89. User selected backend-only work; explicit group-lease
operations and [Yusuf's integration handoff](PRESENTER-LEASE-HANDOFF.md) are
implemented here. Current big-screen UI/device acceptance remains pending.

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
| #89 | Short G implementation merged into main (`3770032`); keyed/playback acceptance stays separate. |

Older PLAN sections describe the original starter and still say several shipped
features are planned. Yusuf's and the ML history's `Now` sections also retain
some merged branches as in flight. Use actual commits/code plus newest log entries
to resolve those labels; do not edit another owner's history.

## Remaining queue

| Order | Work | Evidence and next action | Owner / estimate |
| --- | --- | --- | --- |
| 1 | Short G briefing | Merged in #89: existing `text`, at most 3 sentences / 45 words, digits; concise local fallback preserves uncertainty. Same 6 tools and 10 s deadline. Ask keeps separate behavior. | Aziz backend done; keyed/playback acceptance separate |
| 2 | Presenter B/U with leases enabled | Backend group claim/heartbeat/release implemented on this branch, with all-or-none preflight and same token/expiry. Existing B/U are tested through screen WS. User chose backend only; Yusuf still needs explicit Take/Release, heartbeat, controller token and recording redaction per the handoff. Override still only releases. | Aziz backend ready; Yusuf UI + joint acceptance pending |
| 3 | Optional exploration review | A1 fixed by Rayan in merged #91. A2 exhausted-viewpoint command completion is deferred owner coordination outside the final-stretch list; V2 stays off for the fixed demo. | Rayan-owned policy; no new policy edits here |
| 4 | Startup floorplan and generated timeline | Implemented and validated in #90: registered IDs, startup selection, atomic paused reset, gated event playback, failure reporting and reset/privacy protection. | Aziz implementation done; generated-map/rehearsal acceptance remains |
| 4a | Strong earthquake / stats / judge pool / J/I | Implemented in #90. Strong has 2 areas now + 1 at 10 sim s, up to 2 actual relay losses; measured screen counters; pool serving; closed-by-default J/I under Yusuf's recorded OK. J does not substitute fake/runtime examples while its pool is absent. | Aziz implementation done; actual pool/counter exports remain Rayan's |
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

Presenter backend follow-up: **427 passed, 1 opt-in soak skipped** in 119.22 s,
including 14 new group-lease regressions and the fixed-demo guard. No `web/`
source changed; the presenter UI/dry run stays with Yusuf under the user's
backend-only instruction.
