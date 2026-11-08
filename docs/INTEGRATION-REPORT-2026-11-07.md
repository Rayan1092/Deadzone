# Integration report - November 7, 2026

Aziz backend checkout synced through main `ae3762b` (includes the ordering fix and
AI Lab contract). No API key was added or used. Backend feature gates remain off
by default. This report separates implemented backend behavior from frontend and
testing-laptop acceptance.

## Backend delivery

| Item | Implemented behavior | Acceptance still needed |
| --- | --- | --- |
| Gemini briefing on G | Real Gemini function calling; frozen Command snapshot; robots, survivors, routes, network, faults, events and coverage tools; total 10 s deadline; honest local fallback | Rayan creates key and verifies `source: "gemini"` on testing laptop |
| Phone Ask Gemini | `POST /api/ask` with free-text question; same read-only tools, deadline and source fields | Yusuf phone box/speech; Rayan keyed Ask dry run |
| Aftershock | Gated collapse adds real rubble/walls, permanently destroys relay/custody and permits ordinary network rerouting; no direct Command update | Yusuf A-key UI merged; Rayan robot route recompute in flight; combined dry run |
| Reed-Solomon | Real RS(255,223) and CRC over serialized payloads on weak links; parity consumes bandwidth; failed decode retains custody; per-link repair counts | Yusuf repair animation; enabled-mode testing-laptop timing |
| Offline co-planning | Gated per-field LWW CRDT, epochs, tombstones, deterministic merging, visible invalid candidates and dispatch protection | Yusuf persistent browser queue/conflict UI and two physical phones offline/reconnect |
| Rescue order | Gated list joins delivered survivors/routes only, with route length and documented risk heuristic | Yusuf phone list; device dry run |
| Quiet preload | `/api/plan?check=false` saves/broadcasts without safety rejection; judge's explicit check still rejects unsafe P-1 | Final demo rehearsal |
| Baseline toggle | REST and screen WS accept both action/value and action/mode; all robots switch through set_mode; conflicting aliases reject atomically | Yusuf key/chip and WAITING_FOR_LINK label |
| Plan publication ordering | One Hub lifetime lock orders draft writes, CRDT, checks, dispatch and reset through publication; reset cannot resurrect old drafts | PR #58 merged |
| AI Lab assets | New gated read-only `/ai-lab/results/*` and `/ai-lab/slides/*`; JSON/images only; exports served byte-for-byte | Implementation PR; Rayan training curve/examples/manifest exports; Yusuf L overlay |

Feature flags: `DZ_GEMINI`, `DZ_AFTERSHOCK`, `DZ_FEC`, `DZ_CRDT`,
`DZ_RESCUE_ORDER`, `DZ_AI_LAB`, each enabled only by value `1`. Baseline control is
an explicit operator action. Nothing enables these features automatically.

## Teammate work integrated

- Rayan: trained thermal detector/decoy rejection, Grad-CAM assets and event paths,
  baseline robot mode, delivered rescue routes/beacons, DEMO guard, soak test and
  PR #28 contract review. All 61 routes in his review parsed/delivered. His low
  finding about silent route rejection is addressed with ID/reason warning logs.
- Yusuf: one-view Command knowledge-gap overlay on M, high-fidelity 3D world,
  robot-eye view, replay recording, calm UI and A-key aftershock/destroyed relays.
  Runtime rubble/walls remain Reality-only until normal delivered observations.
- Latest PLAN: ground-floor simulation remains unchanged; a multi-story shell is
  visual only. AI Lab and judge-picked scenario generation are newly planned.
  Rayan owns generator validation and route recompute. Planner optimization is
  explicitly deferred by Rayan. No robot/ML/web source was edited by Aziz.

Some history `Now` sections still describe already-merged work as in flight; the
status above follows commits, actual code and checks rather than those old labels.

## Validation

- Ordering fix: **306 passed, 1 skipped** in the full backend suite; **50 passed**
  in the focused ordering/CRDT/phone/mode suite. Three regression cases failed
  before the fix. Reproduction: server budget 120 but slow phone publication
  sequence `[120,90]`; phone finished with stale budget 90.
- AI Lab focused tests: **8 passed**, covering actual export bytes/media types,
  GET/HEAD, default-off and cache revalidation, missing/hidden/unsupported paths,
  traversal and rejected writes. Final combined suite: **314 passed, 1 skipped**
  in 114.00 seconds, including the trained-model DEMO guard. The skip is the
  explicitly opt-in soak; one existing Starlette test-client deprecation warning.
- Latest merged frontend production build: **passed**, 728 modules. Vite warns
  about a large 3D chunk; build success does not establish GPU frame rate.
- Real uvicorn HTTP/WebSocket integration: **passed** with trained detector,
  two logical phone clients, queued concurrent edits/reconnect, quiet preload,
  explicit safety rejection/fix/dispatch, delivered S3/crop/Grad-CAM, mode aliases,
  relay placement/destruction, collapse geometry, Command-only prior, honest local
  G/Ask fallback, delivered rescue ordering, reset/epoch rejection, and AI Lab
  export bytes/HEAD/write rejection. Observed 20 simulated seconds. Reusable
  runner: `scripts/check_live.py --allow-reset --ai-lab` against a disposable
  loopback server with the corresponding flags. [Raw result](validation/live-integration-2026-11-07.json).
- Separate FEC-enabled 90-sim-second run: **510 delivered bundles**, **77 corrupted
  bytes / 77 corrected**, zero failed blocks, S3 delivered. This is a correctness
  check, not a demo timing or performance pass. [Raw result](validation/fec-enabled-sim-2026-11-07.json).

Earlier long-run evidence, not rerun for static asset serving:

- Rayan's opt-in scripted soak: **passed**, 1,200 simulated seconds in 73 wall
  seconds, 4,622 events, memory settled around 326 MiB. Normal suite skips this
  explicitly opt-in test. [Evidence](validation/scripted-soak-2026-11-07.json).
- Paced real Hub/default-plan run: no exceptions, all three survivors delivered,
  peak 353.58 decimal MB and 9.62 MB growth after warmup. **Pace criterion failed:**
  1,201 simulated seconds / 156.92 wall seconds = **7.654x**, with speed set to 10.
  This was 20 minutes of simulated time, not 20 wall-clock minutes. Planner profile
  was handed to Rayan; optimization is deferred. [Evidence](validation/soak-paced-summary-2026-11-07.json).

## Remaining release checks

1. Rayan adds his key only to ignored `server/.env`, enables `DZ_GEMINI=1`, restarts
   and reports both G and Ask returning `source: "gemini"`. A key alone does not
   enable the feature. Timeout/quota/missing-key responses stay honestly local.
2. Yusuf completes pending phone integrations and L overlay against the published
   contracts. Two API clients are not evidence of offline browser persistence or
   physical phones on venue Wi-Fi.
3. Testing laptop dry-runs each optional feature before enabling it for the demo;
   verify route replacement after Rayan's recompute lands, GPU readability/frame
   rate and the two-phone LAN flow. No visual/GPU acceptance was performed here.
4. Record a new complete backup after final changes and rehearse the full fixed
   demo. A fresh backup recording and the 10x pace target are not claimed complete.

Contracts and details: [AI Lab](AI-LAB.md), [co-planning](CO-PLANNING.md),
[aftershock](AFTERSHOCK.md), [network/FEC](DTN.md), [rescue order](RESCUE-ORDER.md),
[mode/soak](SOAK-AND-MODE.md), and [team handoff](team/history/aziz.md).
