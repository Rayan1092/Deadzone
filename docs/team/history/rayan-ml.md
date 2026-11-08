# Rayan Diya: ML survivor detector (testing laptop session)

Owns `ml/` and `server/deadzone/robot/perception.py`. Only Rayan's ML session on the testing laptop edits this file. Rayan's robot session writes `history/rayan.md`.

## Now
- **Working on:** `rayan-ml/judge-test` (PR open, merging after tests): judge pool export for Aziz's J overlay. Next: `rayan-ml/benchmark-v2` (radio sensitivity sweep, results ready).
- **Works on main:** trained survivor detector + `perception.filter_hits()` with sim fallback (PR #14), runtime crops, robot hookup and decoys (PR #17), Grad-CAM heatmaps (PR #49), AI Lab export (PR #68), logged retrain (PR #71), real-scene crops + detector fine-tuned on indoor thermal people, FLIR 96.7% / indoor 99.6% (PR #95).
- **In flight (not merged):** `rayan-ml/judge-test`: `ml/results/judge_pool/` (40 held-out images + manifest).
- **Blocked on / need from others:** nothing.
- **Promises to others:**
  - `filter_hits(hits)` keeps the `io.thermal()` hit shape `{id,pos,crop,conf}`. Kept hits get `conf` = model P(person) and `detector:"model"`; rejected hits are dropped.
  - It falls back to passthrough (sim sensor) when `DETECTOR=sim` is set, when no model file exists, or when torch is missing.
  - Runtime crop names: `pos_0001..0003.png` are survivors S1..S3, `neg_0001..0003.png` are decoys D1..D3 (192 px; the model resizes to 96).
  - `/crops/manifest.json` entries carry `pose` (survivors), `shows`, `caption`, `source`; `lab.json` keeps 12 + 12 `examples` (with `pose`, `shows`, `caption`) and `metrics_indoor`.
  - Judge pool manifest format below (judge-test entry), readable by Aziz's `readJudgePool`.

## Log

### 2026-11-08 13:05 · rayan-ml/judge-test · Judge pool export for the J overlay
- **Did:** `py ml/make_judge_pool.py` writes `ml/results/judge_pool/`: 40 held-out FLIR ADAS v2 val images (20 person, 20 not person, 288 px), scored by the shipped model (the PR #95 detector). Never trained on; none of them, and no crop from their frames, are in the AI Lab examples or the sim's crops (exclusions from `ml/real_crops.json`). Crops from one video are at least 150 frames apart (no near-duplicates). Not-person images are centred on labelled objects (cars, signs), never random background that could hold an unlabelled person. 2 + 2 model mistakes kept on purpose: the model is right on **36 of 40** here (96.7% on all 1,200 held-out images; the manifest's `note` says so). Poses set by eye in `ml/judge_pool_poses.json`. Validated with Aziz's own `readJudgePool` (web/src/panels/judgePool.js on main): 40 items accepted, URLs, labels and scores correct. Overlay not built here (Aziz's #90 has it).
- **Contract changes:** new files `ml/results/judge_pool/{pos,neg}_NN.png` + `manifest.json`, served by Aziz's existing route at `/ai-lab/results/judge_pool/` (DZ_AI_LAB=1). Manifest:
  ```
  { "caption": "Real thermal camera image, Teledyne FLIR dataset",
    "held_out": true, "split": "val",
    "model": {"name": "MobileNetV3-Small", "file": "...", "threshold": 0.6}, "threshold": 0.6,
    "source", "truth_source", "confidence", "pose", "note", "paths": text fields,
    "model_right": 36, "n": 40,
    "items": [ { "file": "pos_01.png",          // relative to judge_pool/
                 "truth": "person" | "not person", "verdict": "person" | "not person",
                 "confidence": 0.999,             // model P(person), 0..1, never rounded up
                 "pose": "standing" | "walking" | "sitting" | "crouching" | "bent" | "lying" | "partly hidden" | null,
                 "caption": "...",
                 "label", "predicted", "conf": same values under the names readJudgePool reads } ] }
  ```
- **Heads-up for others:** **Aziz:** the pool is live at `/ai-lab/results/judge_pool/manifest.json`; your J overlay should now load it (the PLAN caption text you show is longer than the manifest's `caption`; either is true). **Yusuf:** nothing.
- **Next:** benchmark v2 PR.

### 2026-11-08 12:40 · rayan-ml/real-crops · Real-scene crops, detector fine-tuned on indoor thermal people (PROMOTED)
- **Did:** Rayan: the runtime crops and AI Lab examples were street scenes. `ml/real_crops.py` cuts candidates under strict rules (exactly one person, tight, no vehicle / road in frame, trapped-looking pose; decoys = a warm object filling the frame) and the picks, checked by eye from contact sheets, live in `ml/real_crops.json`. FLIR ADAS is driving footage: only 1 of 28 FLIR people who passed the rules was not a walker, so the people come from **SDT** (Zenodo 4124309, real indoor FLIR Lepton 3.5 frames of people lying / sitting / standing plus empty rooms, CC BY 4.0, no login), only from the 20% held out of training (`ml/prep_sdt.py`, last 20% of every 2,000-frame block). Survivors: S1 crouching, S2 kneeling bent over, S3 slumped in a chair (all 1.000). Decoys: hot slatted panel (radiator stand-in) 0.002, truck machinery (engine) 0.038, panel with dials (coffee machine) 0.009. Fine-tune: same recipe, FLIR train + SDT train crops (`train.py --crops ml/data/crops_mix`). The old model missed 30% of indoor people (SDT held-out 83.9%, most lying people near 0). New model: **FLIR held-out 96.7% (was 96.2%), SDT indoor held-out 99.6%**; `promote_if_better.py` PROMOTED (demo props right). Regenerated eval, Grad-CAM, lab.json (24 examples, 23 right, one lying-person miss kept on purpose), training curve, slide images (`crops_grid` uses the curated examples, accuracy read from metrics.json). Full suite 415 passed, demo guard green.
- **Contract changes:** runtime crops are 192 px (same names; model resizes to 96). `/crops/manifest.json` entries gain `pose` (survivors: crouching / bent / sitting), `shows` (what the real image is; `object` stays the decoy's role in the building), `caption` ("Real FLIR thermal frame, same input as the AI"), `source`; top-level `caption`. `lab.json`: `examples` gain `pose`, `shows`, `caption`; new `metrics_indoor` {accuracy, precision, recall, n_test, confusion, data}; `model.trained_on` updated. `metrics.json` numbers changed (96.7%).
- **Heads-up for others:** **Yusuf:** new survivor/decoy images and Grad-CAM; show `caption` under every AI image and `pose` on survivor cards if you like; `metrics_indoor` is a second accuracy line for key L ("99.6% on indoor people lying or sitting"). Slides: 96.2% is now **96.7%** (PLAN.md ML slide row, DEMO.md judge answer say 96%, still true). **Aziz:** nothing to serve differently.
- **Next:** judge pool export (`rayan-ml/judge-test`), benchmark v2 PR.

### 2026-11-08 06:40 · rayan/retrain-logged · Logged retrain from the AI Lab entry (PROMOTED on a tie)
- **Did:** ran the rayan.md AI Lab retrain exactly as written on main `4b210ab`. `train.py --epochs 5 --seed 0` on the RTX 3060: holdout acc 0.815, 0.918, 0.945, 0.965, 0.968 per epoch, logged to `ml/results/train_history.json`. `promote_if_better.py`: held-out FLIR val shipped 0.9617 vs candidate 0.9617, so it **PROMOTED** (the rule is equal or better, plus all 6 demo props right). Regenerated eval (metrics.json and confusion matrix unchanged: TN 578, FP 22, FN 24, TP 576), Grad-CAM (only `neg_0002` heatmap changed), slide assets, and `lab.json` (24/24 examples right, 5 curve points). Runtime scores: pos 1.000 / 0.889 / 0.999, neg 0.000 / 0.000 / 0.003, identical to the shipped model. Tests: demo guard + gradcam + ai_lab 23 passed; full suite 341 passed, 1 skipped. `detector_logged.pt` and `detector_prev.pt` are not committed.
- **Contract changes:** none (`lab.json` keeps Rayan's format; `curve` is now filled).
- **Heads-up for others:** Yusuf: the key L training curve now has 5 points. The retrained model scores all 6 demo crops exactly like the shipped one (S2 is 0.889 in both), so the sim behaves the same.
- **Next:** test-station refresh and DEMO.md dry run.

### 2026-11-07 17:05 · rayan/detector · Trained survivor detector + perception hook (covers ba654b6)
- **Did:**
  - `ml/prep_crops.py` cuts 96x96 crops from FLIR v2 thermal: 3000/class for train, 600/class from FLIR val as the held-out test split.
  - `ml/train.py` fine-tunes MobileNetV3-Small on the RTX 3060 (5 epochs, about 2 min).
  - `ml/eval.py` writes `ml/results/metrics.json` and `confusion_matrix.png`: acc 0.962, prec 0.963, rec 0.960, F1 0.962 (TN 578, FP 22, FN 24, TP 576).
  - `ml/pick_runtime.py` picks close-up held-out crops for the sim: 3 people, plus 3 decoys (2 cars and a warm boxy object) drawn only from object-centered negatives.
  - `server/deadzone/robot/perception.py`: `filter_hits(io.thermal())` scores each hit's crop on the CPU with a per-crop cache, so it stays deterministic, and drops anything below 0.6.
  - Torch stays optional: server `requirements.txt` is unchanged and `ml/requirements.txt` has the CUDA install line.
- **Contract changes:** none. `io.thermal()` hit shape unchanged. Kept hits gain an optional `detector:"model"` key, robot-internal only.
- **Heads-up for others:**
  - **Rayan's robot session:** `robot.py` doesn't call the detector yet. Hookup:
    ```python
    from .perception import filter_hits          # top of robot.py
    for s in filter_hits(io.thermal()):          # in _perceive, replaces: for s in io.thermal():
    ```
    The first call loads the model (about 1 s, once). Without torch or the model it's a passthrough.
  - **Aziz:** please add 3 decoy hot spots once the hookup above is on main, not before, because the plain sim sensor would report them as survivors:
    - In `collapse_01.json`, add `"decoys": [{"id":"D1","pos":[x,y],"thermal":"neg_0001.png","label":"radiator"}, {"id":"D2",...,"neg_0002.png","label":"engine"}, {"id":"D3",...,"neg_0003.png","label":"coffee machine"}]`.
    - Make `RobotIO.thermal()` in `sim.py` return decoys in the same hit shape as survivors (same range/FOV/LOS check). The detector rejects them.
    - Floorplans are Rayan's files, so either of us can add the JSON; ask first.
  - `DETECTOR=sim` env var forces the sim sensor.
- **Next:** merge after Rayan's OK, then help wire the decoys and put metrics plus the confusion matrix on the slide and Devpost.
