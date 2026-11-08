# Rayan Diya: ML survivor detector (testing laptop session)

Owns `ml/` and `server/deadzone/robot/perception.py`. Only Rayan's ML session on the testing laptop edits this file. Rayan's robot session writes `history/rayan.md`.

## Now
- **Working on:** `rayan/retrain-logged`: PR open, waiting for Rayan's OK (the logged retrain was PROMOTED, on a tie).
- **Works on main:** trained survivor detector + `perception.filter_hits()` with sim fallback (PR #14), runtime crops, robot hookup and decoys (PR #17), Grad-CAM heatmaps (PR #49), AI Lab export (PR #68).
- **In flight (not merged):** `rayan/retrain-logged`: retrained `ml/models/detector.pt` (same held-out accuracy 96.2%), `ml/results/train_history.json` (per-epoch curve), regenerated `lab.json`, lab crops, a heatmap and slide images.
- **Blocked on / need from others:** nothing.
- **Promises to others:**
  - `filter_hits(hits)` keeps the `io.thermal()` hit shape `{id,pos,crop,conf}`. Kept hits get `conf` = model P(person) and `detector:"model"`; rejected hits are dropped.
  - It falls back to passthrough (sim sensor) when `DETECTOR=sim` is set, when no model file exists, or when torch is missing.
  - Runtime crop names: `pos_0001..0003.png` are survivors, `neg_0001..0003.png` are decoys.

## Log

### 2026-11-08 06:40 · rayan/retrain-logged · Logged retrain from the AI Lab entry (PROMOTED on a tie)
- **Did:** ran the rayan.md AI Lab retrain exactly as written on main `4b210ab`. `train.py --epochs 5 --seed 0` on the RTX 3060: holdout acc 0.815, 0.918, 0.945, 0.965, 0.968 per epoch, logged to `ml/results/train_history.json`. `promote_if_better.py`: held-out FLIR val shipped 0.9617 vs candidate 0.9617, so it **PROMOTED** (the rule is equal or better, plus all 6 demo props right). Regenerated eval (metrics.json and confusion matrix unchanged: TN 578, FP 22, FN 24, TP 576), Grad-CAM (only `neg_0002` heatmap changed), slide assets, and `lab.json` (24/24 examples right, 5 curve points). Runtime scores: pos 1.000 / 0.889 / 0.999, neg 0.000 / 0.000 / 0.003. Tests: demo guard + gradcam + ai_lab 23 passed; full suite 341 passed, 1 skipped. `detector_logged.pt` and `detector_prev.pt` are not committed.
- **Contract changes:** none (`lab.json` keeps Rayan's format; `curve` is now filled).
- **Heads-up for others:** Yusuf: the key L training curve now has 5 points. `pos_0002` (S2) now scores 0.889 instead of near 1.0; still above 0.6.
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
