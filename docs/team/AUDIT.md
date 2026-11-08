# Deployment audit: user-facing text and states

Walked on the testing laptop on main `292fdb7` (2026-11-09): the big screen at 1920 x 1080 in Operator view and Engineering view (E), one view and split view (M), every panel and popup (help ?, intro card, Join Q, Model Lab L, Model test J, Under the hood I, briefing G), the B and A toasts and banners, the phone landing page, the same screens after the server was stopped, and every error message the server can send to a screen or phone (`PlanError` / `HTTPException` texts). Server flags: the DEMO.md required set plus `DZ_AI_LAB DZ_AFTERSHOCK DZ_SENSOR_VIEW DZ_CONTROL_LEASES`. Headless Chrome, screenshots on the testing laptop.

Owners: `web/src/three/` = Yusuf, `web/src/panels/` = rayan-ml (testing laptop), `web/src/phone/` = Aziz, server = Aziz, docs = Rayan. Shared web files outside those folders (`format.js`) are listed under Yusuf. **Status** column: open until the owner fixes it.

## Internal names shown to users

| # | Where | Problem | Owner | Status |
|---|---|---|---|---|
| 1 | `web/src/panels/Panels.jsx:21` | Help list: "aftershock at a random spot (server needs DZ_AFTERSHOCK=1)": flag name | rayan-ml | fixed (rayan-ml/audit-panels) |
| 2 | `web/src/panels/Panels.jsx:21` | Help list: "new random building (Q&A)": "Q&A" is our script word | rayan-ml | fixed (rayan-ml/audit-panels) |
| 3 | `web/src/panels/Panels.jsx:23` | Help list: "Model test: a held-out sample (Q&A)" and "under the hood (Q&A)": "Q&A" | rayan-ml | fixed (rayan-ml/audit-panels) |
| 4 | `web/src/panels/Panels.jsx:21` | Help list: B "(with control leases on: Unlock first)": "control leases" is the server's term; the screen calls it the Operator lock | rayan-ml | fixed (rayan-ml/audit-panels) |
| 5 | `web/src/panels/Panels.jsx:22` | Help list: S "save the mission recording (open with ?record)": URL parameter | rayan-ml | fixed (rayan-ml/audit-panels) |
| 6 | `web/src/panels/Panels.jsx:23` | Help list: "?replay" listed as if it were a key, "no server" | rayan-ml | fixed (rayan-ml/audit-panels) |
| 7 | `web/src/panels/Panels.jsx:78` | Unlock tooltip "(B and U need it)": key letters as the reason | rayan-ml | fixed (rayan-ml/audit-panels) |
| 8 | `web/src/panels/Panels.jsx:104` | Detector chip "sim fallback": internal mode name | rayan-ml | fixed (rayan-ml/audit-panels) |
| 9 | `web/src/panels/Panels.jsx:311` | Toast "New scenario needs the latest server (GET /api/scenarios)": API path | rayan-ml | fixed (rayan-ml/audit-panels) |
| 10 | `web/src/panels/JudgeTest.jsx:27` | "Enable the Model Lab and wait for the held-out export.": setup step for us, not the viewer | rayan-ml | fixed (rayan-ml/audit-panels) |
| 11 | `web/src/panels/JudgeTest.jsx:78` | Footnote "MobileNetV3-Small · val split · recorded model results from the export. This panel does not run new inference.": "val split", "export", "inference" | rayan-ml | fixed (rayan-ml/audit-panels) |
| 12 | `web/src/panels/UnderHood.jsx:32` | Footnote "Missing detector/deadline counters stay marked as awaiting their export.": developer note | rayan-ml | fixed (rayan-ml/audit-panels) |
| 13 | `web/src/format.js:80` | Event line "Aftershock is off: start the server with DZ_AFTERSHOCK=1": flag name | Yusuf | open |
| 14 | `web/src/phone/RobotControl.jsx:96` | Phone: "Hold, Return home and Explore need DZ_VOICE=1.": flag name | Aziz | fixed (#186 phone; p2/public-server-text) |
| 15 | `web/src/phone/AskCard.jsx:13-14` | Phone: "Gemini needs an API key configured on the server", "The server's Gemini model setting needs fixing.": setup detail for a judge's phone; "Ask is not available right now" reads better, keep the detail for the operator | Aziz | fixed (#186 phone; p2/public-server-text) |
| 16 | `server/deadzone/app.py:161,224,523,604,821,916` | Error texts "Enable DZ_CONTROL_LEASES=1 ...", "Enable DZ_VOICE=1 ...", "Enable DZ_SCENARIO_TIMELINE=1 ...", "Enable DZ_AFTERSHOCK=1 for an aftershock dry run", "Enable DZ_CRDT=1 ...", "Enable DZ_RESCUE_ORDER=1 ...": these reach screens and phones verbatim (e.g. the A key toast); flag names and "dry run" | Aziz | fixed (p2/public-server-text) |
| 17 | `server/deadzone/scenarios.py:100` | "Enable DZ_AFTERSHOCK=1 for this disaster timeline": flag name | Aziz | fixed (p2/public-server-text) |
| 18 | `server/deadzone/app.py:885,888` | "Set DZ_PUBLIC_URL to ...": shown when the join link fails (Join overlay, `panels/JoinPanel.jsx:16` displays `detail` as is) | Aziz | fixed (p2/public-server-text) |
| 19 | `server/deadzone/app.py:200` | "Presenter credential required": "presenter" (the screen says Operator lock / console) | Aziz | fixed (p2/public-server-text) |
| 20 | `server/deadzone/command/leases.py:90,126` | "{robot} is controlled by {name}": `name` is the raw client label (e.g. "judge-phone", "Presenter"); the screen maps labels to "Field unit N" / "Console", this message does not | Aziz | fixed (p2/public-server-text) |
| 41 | `web/src/panels/AILab.jsx:243` | Model Lab without results: "Test results not served: start the server with DZ_AI_LAB=1.": flag name (missed in the first pass) | rayan-ml | fixed (rayan-ml/audit-panels) |

## Wording, grammar, consistency

| # | Where | Problem | Owner | Status |
|---|---|---|---|---|
| 21 | `web/src/panels/Panels.jsx:19-25` | Help list mixes lowercase entries ("start / pause", "overview") with capitalised ones ("Model Lab: ...", "Operator view / Engineering view ..."); pick one (sentence case) | rayan-ml | fixed (rayan-ml/audit-panels) |
| 22 | `web/src/panels/Panels.jsx:19` (now `keys.js`) | "1–3 follow robot": the handler follows robots 1-9 (generated buildings can have more) | rayan-ml | fixed (rayan-ml/audit-panels) |
| 23 | `web/src/panels/Panels.jsx:22` | "Q phone join QR" vs the top-bar button "Join on phone" and the overlay title "Join on phone": same thing, two names | rayan-ml | fixed (rayan-ml/audit-panels) |
| 24 | `web/src/panels/Panels.jsx:126` / `UnderHood.jsx:24` | Top-bar button "I · Counters" opens a panel titled "Under the hood"; help says "under the hood" | rayan-ml | fixed (rayan-ml/audit-panels) |
| 25 | `web/src/panels/Panels.jsx:127` | Connection chip "live" / "offline" in lowercase, every other chip is sentence case ("Night ops", "Detector: AI model") | rayan-ml | fixed (rayan-ml/audit-panels) |
| 26 | `web/src/panels/Panels.jsx:116,118` | Speed buttons are a hyphen "-" and "+" with no tooltip; the help list uses a real minus "−" | rayan-ml | fixed (rayan-ml/audit-panels) |
| 27 | `web/src/panels/JudgeTest.jsx:58` | Before the first guess the tally reads "Model 0 of 0 · You 0 of 0" | rayan-ml | fixed (rayan-ml/audit-panels) |
| 28 | `web/src/panels/JudgeTest.jsx:68,76` | "This crop could not load", "Next random crop": "crop" is ML jargon (the panel itself says "thermal image") | rayan-ml | fixed (rayan-ml/audit-panels) |
| 29 | `web/src/panels/AILab.jsx:195,223` | "Thermal crops in this building", "classifies thermal crops": jargon | rayan-ml | fixed (rayan-ml/audit-panels) |
| 30 | `web/src/panels/AILab.jsx:200` | Crop caption "model: person 100%" starts lowercase, the rest of the panel is sentence case | rayan-ml | fixed (rayan-ml/audit-panels) |
| 31 | `web/src/panels/JudgeTest.jsx:66` vs `AILab.jsx` | Two captions for the same kind of image: "Real thermal camera image, Teledyne FLIR dataset: the same input ..." (Model test) and "Real FLIR thermal frame, same input as the AI" (Model Lab) | rayan-ml | fixed (rayan-ml/audit-panels) |
| 32 | `web/src/panels/UnderHood.jsx:9` | "FEC blocks that failed": abbreviation; "Error-correction blocks that failed" | rayan-ml | fixed (rayan-ml/audit-panels) |
| 33 | `server/deadzone/app.py:472,944,500,557,599` | "Expected an envelope with object data", "Unsupported phone message: {kind}", "mode and value must agree" (lowercase), "Director value must use do, not type": protocol wording if it ever reaches a screen | Aziz | fixed (p2/public-server-text) |
| 34 | `server/deadzone/command/frames.py:61` | "Expected a valid base64 JPEG no larger than 320x180 / 128 KiB": protocol wording on the phone camera upload | Aziz | fixed (p2/public-server-text) |
| 35 | `web/src/phone/zones.js:22` | Fallback "the server did not accept this plan": fine, but lowercase after a colon while other phone errors are sentences | Aziz | fixed (p2/public-server-text) |

## Missing or confusing states

| # | Where | Problem | Owner | Status |
|---|---|---|---|---|
| 36 | `web/src/panels/Panels.jsx:104-127` | **Server down:** the big screen keeps every control enabled (Start, speed, Reset, Unlock) and the detector chip still says "AI model"; the only sign is the small "offline" chip. Clicking does nothing, silently. Needs a clear "Server disconnected, reconnecting…" state and disabled controls | rayan-ml | fixed (rayan-ml/audit-panels) |
| 37 | `web/src/phone/PhoneApp.jsx` (landing) | **Server down:** the phone landing page ("Join the rescue", two buttons) shows no offline state; the Live / Offline chip (`PhoneApp.jsx:187`) only appears after a role is picked | Aziz | fixed (#186 phone; p2/public-server-text) |
| 38 | `web/src/panels/UnderHood.jsx:29` + `server/deadzone/sim.py:497` | "Detector calls" and "Deadlines met" always read "Awaiting counter": `sim.py` sums them from each robot's telemetry `counters`, but `robot.py:276-280` keeps the counters off telemetry, so the totals never exist | Aziz (sim aggregation) / Rayan (robot telemetry) | aggregation verified (detector_calls, detector_rejections, scheduler_deadlines_met); awaiting Rayan telemetry |
| 39 | `web/src/panels/Timeline.jsx:126` | Scheduler status line is an empty string when no robots are reporting yet (no "Waiting for robots") | rayan-ml | fixed (rayan-ml/audit-panels) |
| 40 | `web/src/panels/JudgeTest.jsx:58` | Tally shows "0 of 0" instead of a prompt before the first round (see #27) | rayan-ml | fixed (rayan-ml/audit-panels) |

## Checked, no problem found

Intro card text and "Got it" button; Rescue Status strip labels and zero state; robot cards (state words, link quality, out of contact line); event feed empty state ("Nothing in these groups yet"); Operator lock refusal toast for B ("Operator lock is on: press Unlock in the top bar to take the robots first"); AFTERSHOCK banner ("Part of the building came down · robots rerouting"); briefing panel ("Command briefing · Generating…", local summary label); Join overlay (both roles, URL, "Same Wi-Fi as this laptop · Q or Esc to close"); phone landing text; phone lease and command messages ("Take control of R2 before sending a command"). No truncated text or misalignment seen at 1920 x 1080 and 390 x 844 in these screens; the robot-card name truncation fixed in #149 stays fixed.
