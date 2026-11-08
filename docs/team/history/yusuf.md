# Yusuf Nusrat: web frontend (Person 3)

Owns `web/`. Only Yusuf's sessions edit this file.

## Now
- **Working on:** `p3/collapse-geometry`: Rayan's "real collapse" list. Step 1 broken walls done; steps 2-4 (ceiling, debris, night atmosphere) being built in parallel worktrees and integrated next; then 5 cinematic camera, 6 robot glTF loader. Before/after shots in `docs/visuals/`.
- **Works on main:** M1–M8, replay, UI Steps 0–1 calm pass (#10, #16, #18, #20, #23, #24, #26, #27, #31, #35).
- **In flight (not merged):** `p3/ai-scope`:
  - AI detection cards (frosted glass): Reality on `survivor_found` ("Person · 100%", "no link, holding the report") and `hotspot_rejected` (faded "Not a person · 0% · rejected"); Command on `survivor_reported` with the delivered record's `crop`. Image `/crops/<crop>`, thermal placeholder until the backend serves it.
  - Detector chip in the top bar from `hello.detector` (hidden until the server sends it).
  - Keys O (`do:"overload"`) and U (`do:"resume"`), plus a "Send resume command" button on a robot card in SAFE_STOP. Key list moved to the sidebar.
  - Phone robot cards: "Following P-1 · zone Z1 (last report)" from delivered `cmd_view.robots[].plan_id/zone` (PR #22).
- **Blocked on / need from others:** nothing.
- **Promises to others:**
  - Rayan's asks (19:50 entry): 1 bigger/brighter robots: yes, 3 AM. 2 robot's-eye view: **Yusuf keeps it** (`web/src/three/RobotEye.jsx`), built last, cut first. 3 phone tap-a-robot with `cmd_view.survivors[].crop`: yes, 3 AM. 4 liquid glass: yes, started on the detection cards, full pass by 3 AM. 5 rescue route on Command: yes, as soon as the contract is posted.
  - Truth survivors and decoys show only on the Reality pane (T). Never on Command. The UI renders actual robot state and never assumes a dispatch, fault or resume made a robot act.

## Log

### 2026-11-08 10:25 · p3/collapse-geometry · Step 4 scene module integrated (atmosphere), scout camera at night
- **Did:**
  - `web/src/three/Atmosphere.jsx` (built by a parallel agent; usage limit killed its two reviewers, so I reviewed it: one useFrame per subsystem, no per-frame allocations, 4 lights, Reality-only, placements derived from `fp`): a lit dust haze (one instanced mesh of camera-facing quads whose shader sums the scene lights, so headlights, the truck flood, strobes and fire light the air), a broken pipe with a water jet and a growing puddle in the break room, a fire with embers and smoke in the hazard room, two flickering emergency fixtures (red beacon near the entry with a sweeping spot, amber at the far end of the largest room). About 22 extra draw calls baked. `perf` and the robot camera copy get the light version.
  - The scout camera at night is dark with the robot's own headlight riding on the camera.
  - Shots: `docs/visuals/after-4-*.jpg` (night + atmosphere at the pinned angles) and `after-5-e-default.jpg` (the new default view).
- **Contract changes:** none.
- **Heads-up for others:** the workflow that builds the ceiling and litter modules (steps 2 and 3) was cut off by the usage limit and is running again now.
- **Next:** integrate ceiling and litter; PR for steps 2-5.

### 2026-11-08 09:55 · p3/collapse-geometry · Step 5 camera, night by default, rover glTF loader, short spoken briefing
- **Did:**
  - **Step 5, camera:** the default overview is a low perspective from the south-west (about 34 degrees up) with a 42 degree lens instead of the 50 degree plan view; manual follow and the auto-director's close shot sit lower (eye-level cinematic). `0` returns to it.
  - **Step 4, my part:** night is the scene now (K switches to day for the dry run): night sky photo (CC0 Dikhololo Night) for light and reflections, exposure 1.6, exponential dust-haze fog, drained color (saturation -0.28), a little contrast, film grain, deeper vignette. Light cones draw their outside only, so a camera inside the flood beam is not washed out. The lot runs to the fog (no visible slab edge).
  - **Step 6, plumbing:** `RoverModel.jsx` (built by a parallel agent, reviewed) loads `/assets/models/robot/robot.glb` when present (HEAD probe, Suspense, per-robot material clones, node names `lidar`, `led*`, `paint*/body*`, `headlight*`, `antenna_tip`), else the procedural rover. Spec in `web/public/assets/models/robot/README.md`. Rayan's pack `robot.glb` is, by his own note, low-poly boxes, so the procedural rover stays the default and the file is not copied in.
  - **Rayan's ask:** G now speaks only the short briefing: `report.short`, else `report.spoken`, else the first three sentences.
- **Contract changes:** none. Reads optional `short` / `spoken` on the report if Aziz adds them.
- **Heads-up for others:** Rayan: thanks for the pack. KTX2 needs a loader swap I don't have time for tonight; if you can regenerate `cracked_concrete_wall`, `cracked_concrete_floor`, `damaged_plaster` as plain 2K JPG (color, normal, roughness) and the decals as PNG with alpha, they drop straight into `web/public/assets/textures/<set>/{diff,nor_gl,rough}.jpg`. The person GLB is more stylised than the sculpted survivors, so those stay too.
- **Next:** integrate the ceiling, litter and atmosphere modules (steps 2-4), screenshots per step, PR.

### 2026-11-08 09:40 · p3/collapse-geometry · Step 1 of Rayan's collapse list: every wall broken (fractured meshes)
- **Did:** `web/src/three/Fracture.jsx`. Every masonry wall is drawn as a fractured slab while standing exactly on the floorplan segment (robots, radio and the demo guard see the same wall):
  - The wall face is split into convex Voronoi cells (`d3-delaunay`, new npm dep): big panels where the wall is intact, small pieces along the break line, around breaches and window edges.
  - Cells above a jagged break line (coherent noise plus bites; outer walls keep ~85 %, brick interiors ~68 %, drywall ~55 %; the last 0.45 m at each end stands so door jambs and corners hold), inside breaches and windows, and spalled corners are removed. Cells along the tear shift and tilt a little.
  - Each cell is a prism with two material groups: the wall face (brick / concrete / plaster photo texture) and the cut faces (fresh broken material, lighter), so torn edges show what the wall is made of.
  - Bent rebar (instanced tube) sticks out of torn edges and breach rims.
  - A plaster skin (coarser cells) sits on interior faces and has spalled off in patches, more near the break and at the floor line, exposing brick or concrete underneath. Exterior faces are bare.
  - About 30 % of long interior walls have a 1.2-2 m section leaning over above a 0.5 m hinge.
  - Removed pieces lie flat at the foot of the wall (within 0.5 m of the wall line, never within 0.7 m of a segment end, so door openings stay clear).
  - Everything merges into one mesh per material: about 10 draw calls for all walls. 38 fps in this browser at a close angle (27 before).
  - Command pane, thermal and blueprint keep intact walls (Command's knowledge is the pre-collapse plan).
  - `?cam=px,py,pz,tx,ty,tz,fov` pins the camera (three.js coords) for before/after shots and video takes.
- **Before/after:** `docs/visuals/` (`before-*.jpg` from main at 11:29 PM, `after-1-*.jpg` from this step), same pinned angles; see `docs/visuals/README.md`.
- **Contract changes:** none. New npm dependency `d3-delaunay` (run `npm install` in `web/`).
- **Heads-up for others:** Rayan: this is step 1 of your list. Steps 2-4 are in progress in parallel; estimates in my 11:17 PM message to Yusuf: ceiling ~1:20, debris ~2:05, night ~2:45, PRs by ~3:10 AM.
- **Next:** integrate ceiling, litter and atmosphere modules; step 5 camera; step 6 robot glTF loader.

### 2026-11-08 08:55 · p3/hyperreal · Rayan's Y1: AI Lab shows `curve_note`; merged main
- **Did:** AI Lab shows `lab.curve_note` under the training curves, and as the empty state ("Training curve pending: …") when there is no curve, so it's clear the curve comes from the logged retrain (Rayan's review item Y1).
  - Merged main. Resolved `robot.py` with Aziz's opt-in explorer: his explorer also gets the survivor-clear map (`_drive_trav`).
  - Full suite 392 passed, demo guard green.
- **Contract changes:** none.
- **Heads-up for others:** Aziz: `_plan_frontier`'s explorer branch now receives `_drive_trav()` (traversable minus a 0.5 m disk around confirmed survivors) instead of `_trav()`.
- **Next:** multi-story shell.

### 2026-11-08 08:45 · p3/plan-v4 · PLAN.md: hyper-realism, honest scout camera, judge-first UI
- **Did:** added "Hyper-realism, honest scout camera and judge-first UI (9:50 PM update)" to `docs/PLAN.md`: what shipped, the merge order of my stacked branches (#70 → `p3/disaster` → `p3/hyperreal`, plus `p3/clinic-map`), the rule that only warm objects get classifier scores (never invented numbers for cold ones), and asks for Rayan and Aziz.
- **Contract changes:** none (docs only).
- **Heads-up for others:** **Rayan, Aziz: read the new section; your asks are at the end.**
- **Next:** multi-story shell.

### 2026-11-08 08:35 · p3/hyperreal · Photo-scanned world, honest scout-camera AI, true-scale people, rugged relays, explainer
- **Did (Yusuf's ask: hyper-realistic, scout camera must match the robot, classify every object, realistic people, no run-overs, realistic beacons, judge-friendly UI):**
  - **Photo-scanned surfaces:** 7 CC0 Poly Haven sets at 1K (color, normal, roughness): damaged concrete floor, concrete wall, red brick, cracked concrete (debris, slabs, ruins), asphalt, rusty metal, painted plaster. Plus a CC0 HDRI sky (industrial sunset) for light and reflections. 14 MB in `web/public/assets/` with `CREDITS.md`. Each texture starts procedural and swaps to the photo when it loads; the HDRI falls back to the light panels. A missing file never breaks the view.
  - **Scout camera:**
    - It is a chassis camera now: it always looks where the robot is heading. Before, it swung to the survivor even when the robot faced away.
    - Every warm object in view (survivors and decoys) gets a box. Within the 5 m thermal range it shows the classifier's score for that object's real FLIR crop (`/crops/manifest.json`, the same crops and model output the robot uses): "PERSON 99.9% onboard AI" or "NOT A PERSON 0.3% rejected". Farther away: "WARM · 6 m · come closer to classify". Hidden behind walls or rubble: no box.
    - Cold objects (walls, furniture, debris) are never scored: they never reach the classifier, and inventing scores for them would be fake.
  - **Survivors:** sculpted at true scale (1.72 m): lathe torso (hips, waist, chest, shoulders), shaped head with nose, ears and hair, tapered limbs with joints, hands, shoes, dusty woven clothes, one arm up and one knee bent, pinned under a slab.
    - The "run over" look was drawing scale: people were 1.35× (legs and glow reached under robots passing 2 m away). Robots also keep 0.5 m off confirmed survivors (previous entry).
    - Thermal view still shows the real FLIR crop.
  - **Relays and beacons:** a yellow hard case with ribs, latches and handle, an antenna mast with two whips and a blinking green LED. The phone relay is a phone in a rubber case on a stand. Destroyed relays are the same case, crushed.
  - **First glance:**
    - A "How to read this screen" card opens once per session (three lines: robots search where radio can't reach; amber = command hasn't heard it yet; onboard AI checks warm things and reports hop relay to relay). It closes itself after 14 s and is linked from the `?` overlay.
    - Plain pane titles: "Inside the building", "What's really happening", "What the command post knows". Top bar reads "Survivors: 1 found · 1 at command".
    - The scheduler opens only near overload (≥97%) or on a miss.
- **Contract changes:** none. Static assets under `/assets/` (served from `web/public`).
- **Heads-up for others:** Rayan: no CC0 photo-scanned human exists that we can download without an account. If your asset pack can include one (CC0/CC-BY GLB, lying pose), it drops into `Human.jsx`. Your `lab.json` is on main, so L now shows curves and examples.
- **Perf:** the robot camera renders a lite copy (indoors only: no outside ruins, smoke or dust). Measured in this browser with the camera open: 18 → about 27 fps; overview without it about 27 fps (gap view plus inset). P mode is the fallback on the testing laptop.
- **Next:** multi-story shell, more scanned props.

### 2026-11-08 08:20 · p3/hyperreal · Robots keep 0.5 m off confirmed survivors (Rayan's robot code, please review)
- **Did:** with Yusuf's OK, a small change in **Rayan's `server/deadzone/robot/robot.py`**: a new `_drive_trav()` used for frontier, go-to and path-blocked planning removes a 0.5 m disk around every survivor the robot has confirmed, so a motion plan never crosses a person. Rescue routes keep `_trav()` (they have to reach the survivor), and the robot's own cell stays open.
  - Measured on seed 7: robots never came closer than 1.96 m to a survivor before or after the change. The run-over Yusuf saw was drawing scale (people drawn 1.35×; now true size, see the next entry).
  - 0.9 m moved demo beats, so the clearance is 0.5 m. The demo guard and the full suite pass (341 passed).
- **Contract changes:** none.
- **Heads-up for others:** **Rayan**: please review or adjust `SURVIVOR_CLEAR_M`. It only matters on maps where a path would really cross a person (generator buildings, the clinic).
- **Next:** frontend hyper-realism commit.

### 2026-11-08 07:40 · p3/disaster · Disaster site, one rover model everywhere, scheduler redesign
- **Did (Yusuf's ask: "an actual disaster site", "fix the scheduler", "robots hyper realistic and the same from above and in the scout camera"):**
  - **Disaster site** (`Disaster.jsx`, Reality only, visual only):
    - Every floor is littered with broken concrete, ceiling-tile fragments and dust, low enough to drive over. Debris is heaped against the walls with fallen ceiling boards leaning on them.
    - The no-go hazard room holds a real collapse mound under its missing roof.
    - Outside, the neighbouring buildings came down (jagged wall stubs, a rubble mound, pancaked slabs, beams) north and east of the building. The lot is cracked and heaved, with debris thrown across it, three crushed cars and a downed utility pole.
    - Smoke rises from the ruins and one is on fire (flickering light, embers; off in P mode).
    - Survivors lie pinned under a slab and chunks.
    - Instanced, so thousands of pieces cost a few draw calls.
  - **Rover** (`Rover.jsx`): one detailed model used by the 3D map, Command's ghosts and the robot camera.
    - Extruded track pods with tread, sprocket and road wheels, and a gunmetal hull with a sloped glacis.
    - The robot's color on the deck and flanks, its id painted on both sides, and a hazard-striped bumper with headlights.
    - A pan-tilt camera with a light bar, a lidar with a glowing ring, a battery pack and roll bar, and a link-colored whip tip.
    - The robot camera sits at the camera head and draws the other robots with the same model and scale (it used to draw boxes). Its own robot is left out so its mast never fills the frame.
  - **Scheduler** (plan Step 4): collapsed to one line by default, with a stacked CPU bar per robot and "All deadlines met" or "R2 missed a perception deadline".
    - It opens by itself for the followed robot, a missed deadline or an overload (≥85%), or when pinned by a click.
    - Open rows are taller, with labelled slices, 10 ms grid, axis and an on-time / missed status.
    - Task colors are categorical slots 1–6, which passed the palette validator on the dark surface. A missed deadline is hatched red, never color alone.
  - **Any building:** camera framing, sun target, truck placement (parallel to the wall, away from the building), decoy objects (from `fp.decoys` by label) and lot-debris exclusion now come from the floorplan. Hand-placed furniture only loads for `collapse_01`.
- **Contract changes:** none.
- **Heads-up for others:** Rayan: buildings from your generator get the disaster dressing, decoy objects and framing automatically.
- **Next:** clinic map PR, then the 9 multi-story shell.

### 2026-11-08 06:50 · p3/collapse · Items 7 + 8: night operations lighting (K), auto-director camera (D)
- **Did:**
  - **K, night operations** (off by default until a dry run, remembered per browser, "Night ops" chip):
    - Sun, sky and environment drop to a weak cold moon. The truck mast gets a flood light aimed through the entrance, with a visible beam.
    - Amber strobes on tripods stand against walls (by the truck, the corridor, the warehouse).
    - Robot headlights become the main light, with soft beams. Lit fluorescent fittings flicker and cast light with a downward shaft.
    - Light film grain and a deeper vignette. Light shafts are additive fading cones, so the airborne dust reads as lit.
  - **D, auto-director** (off by default; caption "Auto camera · …" at the bottom):
    - `link_lost`, `survivor_found` and `fault` cut to a close follow shot of that robot for 9 s. `survivor_reported` (the reveal), `aftershock` and a rerouted `rescue_route_reported` cut to the wide shot.
    - No cut sooner than 4 s unless the news is bigger. After 12 s quiet, a slow orbit.
    - Dragging a view, the wheel or a 0–9 key hands the camera back to the presenter for 20 s.
  - **Tested live at 4x:** the director cut to the wide shot on "S3 reached the command post", then to a close follow on "Scout 1 lost its link, still searching". Night mode checked from the overview: robots and labels stay readable. About 37 fps day or night with the robot camera open.
- **Contract changes:** none. New keys K and D.
- **Heads-up for others:** Rayan: try K and D in the dry run. D is a hands-free option for the demo video. Item 6 (asset pack) is still waiting on your pack; until then the built-in models and textures stay (as in the cut order).
- **Next:** 9 multi-story shell, 10 scheduler strip.

### 2026-11-08 06:10 · p3/collapse · Item 5: AI Lab overlay (key L)
- **Did:** glass overlay on **L** (Esc closes).
  - **Live panel:** the crop a robot just judged (latest `survivor_found` / `hotspot_rejected`), the verdict with the real `conf`, robot and time, and a toggle for the Grad-CAM overlay (manifest `heatmap_alpha`, else the event's `heatmap`).
  - **Held-out test panel:** accuracy, precision, recall and F1 tiles, plus a 2x2 confusion matrix with counts ("correct / missed / false alarm"), from `/ai-lab/results/metrics.json`.
  - **Training curves:** loss and accuracy (train vs val, one measure per chart, legend plus direct labels, hover crosshair) appear only when `/ai-lab/results/lab.json` has `curve`. The colors (`#0d9488` / `#d97706`) passed the palette validator on the dark surface.
  - **Examples:** a training-examples grid from `lab.json.examples` once exported. Until then it shows "Thermal crops in this building" from `/crops/manifest.json` (model verdict and conf per crop).
  - **No data served:** the panel says "start the server with DZ_AI_LAB=1" and invents nothing. Vite proxies `/ai-lab` in dev.
  - New state labels for Rayan's voice commands: `GOING_TO_POINT` "Going to point", `HOLDING` "Holding".
  - **Tested** against Aziz's `p2/ai-lab-assets` branch with `DZ_AI_LAB=1`: real metrics (96.2 / 96.3 / 96.0 / 96.2, confusion 576 / 24 / 22 / 578), Live showed S3 by R3, then D2 rejected by R2, with Grad-CAM. The curve charts were checked with a throwaway file in a scratch worktree (deleted, never committed).
- **Contract changes:** none. Reads Aziz's reserved `/ai-lab/results/*`; `lab.json` schema as in my plan entry.
- **Heads-up for others:** Aziz: needs your AI Lab PR merged and `DZ_AI_LAB=1` on the demo server. Rayan: when you export `ml/results/lab.json` (`curve`, `examples` with files under `ml/results/`), the curves and the examples grid light up with no frontend change.
- **Next:** item 6 asset pack (if Rayan's pack is in), 7 lighting, 8 auto-director.

### 2026-11-08 05:30 · p3/collapse · Item 4: collapse look
- **Did:** the Reality world now reads as a collapse (Rayan's item 3). All of it is derived from the floorplan, so generated buildings get it too, and all of it is visual only (truth grid, radio and robots unchanged; nothing blocks a path).
  - **Outer walls:** windows every 3.6 m, three quarters blown out with shards left in the frames, and on long walls one in four becomes a ragged breach. Some interior walls longer than 6 m get a jagged breach above floor level, with broken blocks piled against both faces.
  - **Cracks:** decals on walls and floors.
  - **Roof:** a surviving piece of roof over each hazard zone (no-go, so it hides nothing robots do), with a broken edge and rebar hanging off it.
  - **Beams:** a steel beam across every other room, about half of them sagging, with a fluorescent fitting swinging on its cable (some flicker, some dead).
  - **Fallen ceiling slab:** one per rubble pile (runtime falls included), leaning on the pile.
  - **Furniture and dust:** a bookshelf toppled face down, a filing cabinet on its side, and 700 dust motes drifting in the air (off in P mode).
  - **Command pane:** keeps the intact building, because damage is truth.
  - **Route flash:** a replaced rescue route flashes and its tag says "rerouted" for 2.5 s (Rayan's suggestion for the S1 reroute at 2:08 and 185 s).
  - 60 fps measured in this browser at full quality (static damage merged per material).
- **Contract changes:** none.
- **Heads-up for others:** Rayan: windows, breaches and the hazard roof follow your generator's walls, hazards and rooms automatically.
- **Next:** item 5 AI Lab.

### 2026-11-08 04:40 · p3/ai-eye · Plan items 1–3: route replace, key B, AI recognition in the robot camera, Ask Gemini, spoken briefing
- **Did:**
  - **Route replace (Rayan's ask):** one route per survivor everywhere: Reality, Command pane, Command inset and phone map. A newer `t` replaces the old route. The gap view's "not reported yet" waits for Command to hold that version. The feed says "R1 replanned the route to S1" and "Updated route to S1 reached the command post".
  - **Key B:** sends `{action:"mode", value}`. A red "Baseline · without Deadzone" chip shows from hello/control `mode`. `WAITING_FOR_LINK` reads "No link, waiting". The three per-robot `mode_changed` events fold into one headline.
  - **AI recognition (Rayan's item 1):** on `survivor_found` (first sighting) or the first `hotspot_rejected` of each decoy:
    - That robot's camera opens, grows to 560×400 and turns to the hot spot for 12 s. A showcase in progress isn't interrupted.
    - A red box shows "PERSON 100% onboard AI" with the real `conf`. Decoys get a grey dashed box, "NOT A PERSON 0% rejected".
    - Steps tick only on real events: detected, location marked, rescue route planned (`rescue_route`), "No signal: beacon RLx dropped" (`relay_dropped.beacon_for`), report reached command (`survivor_reported`).
    - Caption: "Box marks the hot spot the onboard classifier judged from its thermal crop". The box is the object's known extent projected through the robot camera, so we never claim the model localized it.
  - **Phone "Ask Gemini" card (both roles):** `POST /api/ask` with suggestion chips and a pending state. Each answer is labelled "Gemini" or "Local summary · Gemini unavailable" from `source`, with a 15 s client timeout.
  - **G briefing read aloud:** browser speech, with a "Voice on/off" toggle remembered per browser.
  - **Tested live at 4x:** S3 detection opened Scout 3's camera with the box and all four steps ticked. D2 was rejected by R2 with the grey box. The phone Ask returned the local fallback labelled correctly (no key on this laptop). B showed the chip and one feed line, and B again turned it off.
- **Contract changes:** none. New key B.
- **Heads-up for others:** Rayan: the box and steps use your `conf`, `rescue_route`, `beacon_for` and `survivor_reported`. The route replace is ready for your recompute PR. With your key, check the phone Ask shows "Gemini". The robot camera now opens by itself on detections; press × or V to close it.
- **Update after merging main (Rayan's route recompute):** `rescue_route_blocked` now shows as "R1: route to S1 blocked, no safe path right now". Replans use the route-replace path above. Not forced live: an aftershock on the S3 route would block the entrance.
- **Next:** item 4 collapse look.

### 2026-11-08 03:30 · p3/ai-eye · Plan for Rayan's realistic visuals + AI showcase (answer to his ask)
- **Plan, in order, with estimates (from about 8:45 PM; freeze 7:30 AM):**
  1. Updated routes replace old ones (a newer `t` for the same survivor); key B sends `{action:"mode",value:"baseline"|"deadzone"}` with a "Baseline" chip from the hello/control `mode`; `WAITING_FOR_LINK` shows "No link, waiting". 45 min.
  2. AI recognition in the robot's-eye view. 1h15.
     - On `survivor_found` the camera opens on that robot and faces the person.
     - Red box with "PERSON 97% · onboard AI", using the real `conf`.
     - Action steps only from real events: detected → marking location → planning rescue route (`rescue_route`) → dropping beacon (`relay_dropped` with `beacon_for`, only if it happens).
     - Decoys get "NOT A PERSON 0.3% · rejected" from `hotspot_rejected`.
     - Wording: a classifier judged the boxed object. The box is placed from the object's known position, not drawn by the model.
  3. Phone "Ask Gemini" box (`POST /api/ask`, shows `source`) and the spoken G briefing on the big screen. Never cut. 1h.
  4. Collapse look, built in code: angled ceiling slabs, partly missing roof, sagging beams, jagged wall holes, broken windows, dangling rebar and cables, cracks, debris against walls, overturned furniture, airborne dust. 1h30.
  5. AI Lab overlay on key L. Needs Rayan's export by about 1 AM. 1h.
  6. Asset pack swap: robot GLB, person GLB under debris, photo-scanned textures and decals, HDRI. Behind a toggle until a dry run passes. Needs Rayan's pack by about 2 AM. 1h30.
  7. Lighting: dark interior lit mainly by headlights, flicker and emergency lights, light shafts through dust, light grain and depth of field. 1h.
  8. Auto-director and close cinematic shots (robot going dark, S1 discovery, the reveal). 1h.
  9. Multi-story shell with an x-ray cutaway (visual only; sim stays on the ground floor). 1h.
  10. Scheduler strip. 30 min.
- **Cut order (first to go):** 10 scheduler strip, 9 multi-story shell, grain/depth of field/light shafts, photo-scanned texture swap (procedural textures stay), 8 auto-director (manual follow stays), robot and person GLBs (improved procedural models stay). **Never cut:** 1, 2, 3, 4, 5.
- **Contract changes:** none yet. Asks for Rayan's exports below.
- **Rayan, AI Lab export:** uses Aziz's reserved `/ai-lab/results/<file>` (from `ml/results/`, `DZ_AI_LAB=1`). Please add `ml/results/lab.json`:
  `{"model":{"name","input_px","params","onboard_ms"},"metrics":{"accuracy","precision","recall","f1","n_test"},"confusion":{"labels":["person","not person"],"matrix":[[tp,fn],[fp,tn]]},"curve":[{"epoch","train_loss","val_loss","train_acc","val_acc"}],"examples":[{"file":"lab/pos_01.png","label","predicted","conf"}]}`.
  - 12 person and 12 not-a-person example crops, PNG at 192 px, under `ml/results/lab/`.
  - Real numbers only. If there's no per-epoch log, leave `curve` out and the overlay hides that chart.
  - The live panel uses the event fields that already exist (`crop`, `heatmap_alpha`, `conf`).
- **Rayan, asset pack (accepting your offer):**
  - GLB, meshopt or Draco compressed. 1 unit = 1 m, Y up, origin at floor center.
  - Robot: faces +X, under 50k triangles, named nodes `lidar`, `track_L`, `track_R`, `led_*`, `headlight`.
  - Person: lying or partly buried pose, under 30k triangles, no debris attached.
  - Texture sets (color, normal, roughness), 1k JPG, 2k only for floor and walls: cracked concrete, damaged plaster, brick, dusty tiles, rusted metal. Plus crack and stain decals with alpha.
  - HDRI: 1k `.hdr`, overcast or dusk.
  - Total under 40 MB, CC0 or CC-BY only. Commit to `web/public/assets/` (you're OK to write there) with `CREDITS.md` (source, author, licence per file).
- **Next:** items 1–3.

### 2026-11-08 03:05 · p3/aftershock · Key A: aftershock on the big screen
- **Did:** wired Aziz's ask from `docs/AFTERSHOCK.md`.
  - **A** sends `{do:"aftershock"}` and the server picks the spot: the first powered relay, which gets crushed, otherwise the corridor.
  - The headline and the feed show "Aftershock: ceiling collapsed, relay RL2 crushed" and "Relay RL2 destroyed, N bundles lost". The crushed relay is drawn knocked flat with a snapped antenna and the label "RL2 destroyed".
  - Reality panes shake for 1.4 s and a dust cloud billows out of the collapse.
  - Without `DZ_AFTERSHOCK=1` the server's 409 shows as a toast: "Aftershock is off: start the server with DZ_AFTERSHOCK=1". Any refused director control now shows its message instead of failing silently.
  - Honesty fix: rubble that falls during the run (R key, aftershock) is drawn only on Reality panes. The Command pane keeps the static rubble and learns about new rubble through delivered maps.
  - A destroyed relay no longer also logs "switched off".
  - Tested live with `DZ_AFTERSHOCK=1` at 4x. The first A crushed RL2 and R2 went dark. A second A crushed RL3 in the warehouse and all three robots lost their link. Command showed no new rubble.
- **Contract changes:** none. New key A. The screen now reads the `error` envelope as a toast.
- **Heads-up for others:** Aziz: wired as you specified (Reality-only walls and rubble, phones untouched). Rayan: A is a strong demo beat if the dry run passes. Without the env flag it only shows the toast.
- **Next:** Step 4 collapsed scheduler strip, Step 5 auto-director camera.

### 2026-11-08 02:10 · p3/realism · High-fidelity 3D world
- **Did:** rebuilt the 3D world on Yusuf's ask ("real 3D walls and objects"):
  - Walls are full height (2.2 m; fog of war at 2.35 m, the antenna mast at 4.2 m). Textures are procedural PBR with normal maps (no downloads): formwork concrete, brick, a chain-link cage for metal walls, polished slab floor, carpet in the offices, vinyl in the break room and corridor, and an asphalt lot.
  - Doors from `floorplan.doors`: frames and lintels, open doors flat against the wall, broken doors lying flat in the doorway, and a roll-up shutter at the entrance.
  - Debris on every rubble footprint, including runtime rubble falls: instanced concrete chunks in a mound, slabs with rebar, dust stains, and an I-beam on tall piles.
  - Furniture hugs walls or sits in the gas no-go boiler room, so it never overlaps robot paths: desks, chairs, shelving, pallet racks, a forklift, boilers and pipes, signs. The decoys are their real objects at their truth positions (radiator, engine, coffee cart), Reality only.
  - Command post: a response truck with a flashing light bar and a telescoping mast. Gas leak: floor tape plus drifting haze.
  - Tracked rover model: treads, camera head, spinning lidar, and a radio whip whose tip is green when the link is up and red when dark. Survivors are capsule-limb people in clothes.
  - Lighting: IBL from Lightformers, south-west sun, N8AO ambient occlusion, AgX tone mapping, vignette, SMAA. The Command pane gets the same look without props.
  - Fog no longer paints black slabs over walls or (Reality only) rubble piles. Reality panes drop the teal scan tint; Command keeps it.
  - Performance: static props merged per material (`Baked.jsx`), and the shadow map renders only while the scene settles. Measured in this browser: about 25 fps full quality, 28 in P mode, against a 30 fps cap.
- **Contract changes:** none (frontend only; the DEMO.md beats are unaffected).
- **Heads-up for others:** the overview camera is pulled back slightly to fit the truck west of the wall. Press P on a weak laptop. Aziz: merged main; aftershock `floorplan.dynamic_walls` now draw on Reality panes only (not Command, not the inset). Key A comes next.
- **Next:** Step 4 collapsed scheduler strip, Step 5 auto-director camera.

### 2026-11-08 00:50 · p3/realism · Step 3: 3D realism pass
- **Did:** procedural concrete (generated in code, no downloads) on the floor with 4 m saw-cut joints and on the walls, metal walls metallic, light wall caps so the floorplan reads from across the room, dark ground outside; warm key light from the entrance with a shadow frustum covering the whole building (the old light only shaded ±5 m around the origin) plus a cool sky fill; bloom (`@react-three/postprocessing` 2.19.1) on the Reality / one-view canvas only, off in performance mode, so only robot LED strips, survivor figures and the antenna glow (they are not tone mapped); LED strips on each robot in its color; frontier glow on free cells at the edge of real unknown space (5x5 window, ignores lidar speckle); scanned-floor tint made subtler so materials show. Robot camera thermal mode now shows the exact FLIR crops (`floorplan.survivors[].thermal`, `decoys[].thermal` from `/crops`) as billboards, the same images as the AI card (Version 2 "AI visible in the world"); a shape stands in if a crop fails to load. Tested on main at 4x in split and one view; all six crops load (200).
- **Contract changes:** none. New npm dependency `@react-three/postprocessing` (run `npm install` in `web/` after pulling).
- **Heads-up for others:** demo laptop: press P if the big screen drops frames (bloom and shadows are the expensive parts). Rayan: in-world crops use the floorplan's `thermal` names today; a crop manifest is only needed if you add more images.
- **Next:** Step 4 collapsed scheduler strip, Step 5 auto-director camera.

### 2026-11-08 00:15 · p3/one-view · Step 2: one-view "gap" mode (Version 2 plan), key M
- **Did:** the Version 2 "one main 3D view" as a toggle: **M** (or the top-bar layout button) switches between today's split and one full-width Reality view with Command's gap drawn on it. Dark robots get a ghost at Command's last fix with an amber dashed tether to the real robot ("R2 · last report 13s ago"); found-but-unreported survivors pulse amber "S1 · not reported yet" and flip to "S1 · reported to command" with the shockwave; ground the robots mapped but Command hasn't is hazed amber and fades out as map patches arrive (the reveal); rescue routes are faint "not reported yet" until delivered. A blueprint Command inset (public floorplan without truth rubble, delivered map/robots/survivors/routes/relays) and both AI cards sit in a reserved right column; the camera frames the building in the remaining space (projection view offset), follow mode included. Split stays the default until a dry run passes (Rayan's guardrail); the choice is remembered per browser. Also: zones count as dispatched when a robot reports following the plan (no stale "draft" after a reload); the camera refits once a new canvas has a size. Tested with DEMO.md's fixed plan P-2 at 4x: R2 dark with ghost + haze at 2:08, "S1 · not reported yet" + held route at 2:22, reveal at 2:39 (14.1 s, matches DEMO.md).
- **Contract changes:** none. New key M.
- **Heads-up for others:** Rayan: for the pitch, M gives the one-view story; DEMO.md beats are unchanged (frontend only). Try it in the next dry run and tell me if it should become the default. Version 1 backup: record it with the split view before more visuals land.
- **Next:** Step 3 3D realism pass.

### 2026-11-07 23:30 · p3/ui-calm · Preload spoiler fix (Rayan's ask) + calm declutter pass
- **Did:** Step 0, Rayan's quiet-preload ask, done in the frontend: phones only show a safety result for a check they ran themselves, and the big screen hides a `safety_reject` that arrives within 1 s of a fresh `plan_state` (the signature of `POST /api/plan`, which saves and checks in one request). The phone no longer re-saves an unchanged draft before checking. Tested: preload → phone shows "Ready to check P-1", big screen silent; judge taps Run safety check → phone "Safety check failed" + big-screen headline and feed line. Step 1 declutter: one headline at a time (ranked, survivor news never bumped), one AI card per pane, links faint except each robot's path home in its color (server routing rules), relays unlabeled and pulsing only while carrying data, lidar as one soft fan per robot, robot tags name only (dBm moved to signal bars), survivor labels/pulses for 10 s then calm, shockwave only when Command learns a survivor, antenna pulse only for survivor/route/fault deliveries, compact robot cards (followed card expands), QR card → "Join on phone" button, key list → `?` overlay, network stats in the Command pane title, feed 10 lines.
- **Contract changes:** none. New key `?` (also H) for the key list.
- **Heads-up for others:** Rayan: the P-1 preload in DEMO.md can stay as is (no `?check=false` needed); the judges' own check is now the first rejection anyone sees. The sidebar no longer has the QR card: press Q or click "Join on phone".
- **Next:** Step 2 (Command pane as a blueprint), Step 3 (bloom + materials).

### 2026-11-07 22:40 · p3/replay · Browser record/replay backup, key list fix
- **Did:** demo backup #3 without a server. Open the big screen with `?record`: a REC chip shows time and size, **S** saves the WebSocket stream as a gzipped JSON file. Open `/?replay` and drop the file in (or `/?replay=<url>`): it plays through the same store with the original timing; Space pauses, Backspace restarts, +/- change playback speed; the QR card and live pill are hidden. Tested: 34 s live recording 27.4 MB raw → 1.8 MB gzipped, round-trips through the loader (2,396 frames, starts with `hello`); a 40 s recording replays with routes, cards and toasts. The loader sniffs gzip magic bytes because the dev server sends `.gz` with `Content-Encoding: gzip`. Also added P and S to the sidebar key list (P was silently missing since M8) and dropped the static robot count so the top bar fits in record/replay.
- **Contract changes:** none. New URL params `?record`, `?replay[=url]`; new key S.
- **Heads-up for others:** Aziz: browser replay covers the backup demo, so recorder/replay can come off your list unless you want a server-side one. Crop images in a replay need the server running (they load from `/crops`); without it the cards show the thermal placeholder. Before the demo: record one clean run with `?record`, press S, keep the file next to the backup video.
- **Next:** rehearsal fixes.

### 2026-11-07 21:45 · p3/rescue-route · M8 rescue routes on all views, performance mode
- **Did:** Reality draws each robot's `rescue_route` event as a bright yellow dashed line from the entrance to the survivor with "Route to S1 · 49.6 m" and a pulsing "RL5 beacon" ring on the beacon relay; toast/feed "R1 planned a safe route to S1". Command draws only delivered `command.routes[]` and the phone map only `cmd_view.routes[]` (same style, beacon ring), both empty until the backend sends them. P toggles performance mode (no shadows, dpr 1, half the lidar rays, no headlights; remembered per browser, top-bar chip); default dpr capped at 1.5. Top bar stays one line. Tested on main (PR #25): S3 14.2 m at 0:18, S2 38.2 m, S1 49.6 m with beacon RL5 in the cage; Command shows none.
- **Contract changes:** none new. Consumes Rayan's `rescue_route` event and the agreed `command.routes` / `cmd_view.routes` / `rescue_route_reported`. New key P.
- **Heads-up for others:** Aziz: route drawing on Command and phones lights up as soon as `routes` appear in the Command view; please keep Rayan's field names (`survivor, by, path, length_m, clearance_m, beacon, reported_t`). Demo laptop: press P if the big screen stutters. Rayan: DEMO.md can add V (robot camera) and P.
- **Next:** rehearsal fixes.

### 2026-11-07 21:20 · p3/visual-pass · M7 part 2: robot's-eye view
- **Did:** V (or a robot card's Camera button) opens a small picture-in-picture on the Reality pane from that robot's forward camera (Reality telemetry pose, smoothed). Thermal toggle: walls cold blue, survivors glow white-hot and decoys glow amber, so judges see why the detector has to decide. It is a third small WebGL canvas (dpr 1, low-power) that only exists while open.
- **Contract changes:** none. New key V.
- **Heads-up for others:** Rayan: robot's-eye view done in `web/src/three/RobotEye.jsx` as agreed; DEMO.md can add V. Closing the camera logs "THREE.WebGLRenderer: Context Lost" in the console; that is the PiP disposing its own context, not a crash.
- **Next:** rescue route drawing (waiting on the `rescue_route` contract), rehearsal fixes.

### 2026-11-07 21:00 · p3/visual-pass · M7 part 1: survivor figures, bigger robots, phone last crop, liquid glass
- **Did:** survivors are low-poly people lying down in thermal colors (head hottest) with a warm floor glow, pulsing ring and arrival shockwave kept. Robots draw 1.8× with stronger emissive and a colored glow pool (ghosts stay dim). Phone: tap a robot card to see the last thermal crop and verdict it reported (delivered `cmd_view.survivors[]` with `by` = that robot). Liquid glass: frosted overlays on the panes, translucent top bar / sidebar / scheduler, phone cards frosted over a soft color wash.
- **Contract changes:** none.
- **Heads-up for others:** robots now look ~0.9 m wide on screen (the physics body is unchanged). Branch is stacked on PR #24 (M6), which still needs merging.
- **Next:** robot's-eye view (`web/src/three/RobotEye.jsx`), rescue route drawing.

### 2026-11-07 20:30 · p3/ai-scope · M6 AI detection cards, detector chip, O / resume, phone plan status
- **Did:** judges now see what the onboard model judged: a card with the crop and verdict when a robot finds a person or rejects a hot spot (Reality), and again when the report reaches Command. O overloads the followed robot's perception, U or a card button sends resume. Tested on main with PR #22 and the CPU model loaded: "Person · 100%" (S3), "Not a person · 0% · hot spot D1 · R2 · rejected", S2 at 88.9%; O → R1 row "perception missed" while safety runs at 0/50 ms; F×3 → SAFE_STOP → resume button → "R2 resumed after safe stop".
- **Contract changes:** none new. Consumes `survivor_found.crop/conf`, `hotspot_rejected`, Command `survivors[].crop`, director `overload` / `resume`, delivered `plan_id` / `zone`, and (when added) `hello.detector` + `/crops/<file>`. Vite dev proxy now forwards `/crops` to the backend.
- **Heads-up for others:** Rayan: answers to your 19:50 asks are in `## Now` (I keep the robot's-eye view). DEMO.md: O is live once this merges; resume is key U or the "Send resume command" button on the robot's card. Aziz: the cards and chip are ready for `/crops` and `hello.detector`.
- **Next:** survivor figures, bigger robots, phone tap-a-robot, liquid glass, rescue route, robot's-eye view.

### 2026-11-07 19:00 · p3/phone-relay · M5 relay phone mode, relay power toasts, feed fix
- **Did:** a phone that scans the relay QR becomes a relay: one big button turns it on/off, it shows what it carries and who it can hear, and it can be moved by tapping the map. The big screen toasts each switch. Tested on main: RL1 created at the entry with 4 neighbors, off/on/off toasts on the big screen, move into the Break Room, rubble tap rejected, reload with the same label keeps RL1 off at its new spot.
- **Contract changes:** none. Uses `relay_state`, `relay_power`, `relay_place`, `hello.relay_id`, `invalid_relay_position` from PR #12.
- **Heads-up for others:** while the sim is paused the big screen gets no ticks, so relay changes show there only after Space (phones update immediately). A relay phone that sleeps or closes the tab switches its relay off (server rule), so keep phones awake during the demo. Each phone needs its own label (automatic per browser).
- **Next:** M6 polish, M7 replay file for the backup demo.

### 2026-11-07 18:40 · p3/timeline-camera · M4 scheduler strip, follow camera, F/G keys, decoys
- **Did:** the big screen shows each robot's scheduler frame live (safety preempting, busy %, missed deadlines in red), follows a robot with keys 1-3 / 0, injects overcurrent with F on the followed robot (the robot's own fault toast follows), opens a typed Command briefing with G, and the T overlay marks decoys. Tested on main at 4x: follow R1/R2, F → "R1 fault: Wheel overcurrent" + replan, G → local briefing incl. the reported fault.
- **Contract changes:** none new. Uses telemetry `tasks`, director `do:"overcurrent"` / `do:"rubble"`, `GET /api/report` + `report` message, floorplan `decoys`.
- **Heads-up for others:** keyboard map for the demo: 1-3 follow, 0 overview, R rubble, F fault, G briefing, T truth, Q join, Space, Backspace, +/-. The strip's red miss styling is untested live until the O key / overload director value exists. Rayan: the Command camera follows the last reported pose by design.
- **Next:** M5 relay phone mode.

### 2026-11-07 18:05 · p3/phone-plan · M3 plan editor, safety card, plans on the big screen
- **Did:** phones draw zones and no-go areas, assign robots, run the safety check, fix a dead-zone rejection in one tap and dispatch. The big screen shows the shared plan (draft dashed, dispatched solid) and which zone each robot follows. Tested end to end on main (reject → allow dark → pass → dispatch → "R2 is following P-1 (Z1)") and against PR #12 merged with main locally (plan before Space at T+0.1, screen zones, plan_dispatched).
- **Contract changes:** none new. Uses `plan_edit`, `plan_submit`, `safety`, `plan_state`, `error`, `POST /api/dispatch`, PR #12's screen `plan_state` / `plan_dispatched` / `cmd_view.faults`, and Rayan's `plan_applied` / `resumed` / telemetry `plan_id` + `zone`.
- **Heads-up for others:** Aziz: PR #12 merges cleanly with current main (checked locally); its relay_dropped `owner` is a phone client label, the UI now words that as "Phone X joined as relay RLn". Rayan: the demo plan works as you suggested (R2 east wing zone, dark OK).
- **Next:** M4 timeline + follow camera + director keys.

### 2026-11-07 17:15 · p3/relays-links · M2 network visuals, toasts, truth toggle
- **Did:** the big screen now shows relays and the real link mesh, pulses the antenna on deliveries, bursts survivors onto Command, toasts key events, shows wheel current / relays left / fault pills, and a found-vs-reported counter. T toggles truth survivors (Reality only). Camera fits the building. Tested on a live 3-robot sim at 8x.
- **Contract changes:** none. Reads existing `tick.reality.relays/links`, `command.relays`, `stats.delivered`, telemetry `wheel_a` / `relays_left` / `fault`, and the documented event kinds.
- **Heads-up for others:** new keyboard shortcut T (truth overlay). `survivors_found` has one record per robot that saw a survivor; the UI dedupes by id. Aziz: when F/O director controls land I'll wire the keys.
- **Next:** M3 plan editor + safety card on `p3/phone-plan`.

### 2026-11-07 17:00 · p3/phone-shell · M1 phone shell + QR join (PR open)
- **Did:** judges scan a QR on the big screen and get `/phone`: live Command view map, robot cards, reported survivors, auto reconnect. Tested against a live 3-robot sim: relays, survivors (incl. S1 in the cage), reset and server restart all reach the phone.
- **Contract changes:** none. Uses only existing `/ws/phone` (`hello`, `cmd_view`, `error`) and `GET /api/join`. Phones never receive Reality data.
- **Heads-up for others:** in dev the phone link is `http://<laptop-ip>:5173/phone`; after `npm run build` the server serves it on :8000. New npm dep: run `npm install` in `web/` after pulling.
- **Next:** M2 on `p3/relays-links`.

### 2026-11-07 · p3/team-context · Team context system (this file)
- **Did:** added `docs/team/` (protocol + per-person history), the `.claude/` hooks (`team_sync`, `history_guard`), and the `/team-sync` and `/log-work` commands.
- **Contract changes:** none (tooling only)
- **Heads-up for others:** after pulling, every Claude session reads these files automatically. Commits made through Claude must stage your own history file (the hook enforces it).
- **Next:** finish and PR the phone shell.
