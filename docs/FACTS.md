# Facts for the stage

Every number we say on stage, with the file in this repo it comes from. If it cannot be reproduced from a file here it is marked **do not say**. All simulation numbers are **in simulation**; say so.

## The onboard detector

| Say | Number | Source |
|---|---|---|
| Model | MobileNetV3-Small, 96 px thermal crops, 1.52 M parameters, 6.2 MB, runs on the robot (CPU, 4.8 ms per crop) | `ml/results/lab.json` (`model`), `server/deadzone/robot/perception.py` |
| Street accuracy | **96.7%** accuracy, **97.3%** precision, **96.0%** recall on **1,200 held-out FLIR ADAS v2 val crops** (threshold 0.6; 576 / 24 / 16 / 584 tp / fn / fp / tn) | `ml/results/metrics.json`, `docs/assets/confusion_matrix.png` |
| Indoor accuracy | **99.6%** accuracy, **100%** precision, **99.2%** recall on **2,273 held-out SDT indoor frames** (people lying, sitting, standing, empty floor; 10 misses, 0 false alarms) | `ml/results/lab.json` (`metrics_indoor`) |
| Calibration | Expected calibration error **0.6%** street, **0.2%** indoor. A **90%+ confident answer is right 98.9%** of the time on street and **100%** (2,246 of 2,246) indoor. Temperature scaling (T = 1.16) tested, not shipped | `ml/results/calibration.json`, `docs/assets/calibration.png`, `py ml/calibration.py` |
| Judge test pool | **36 of 40** held-out FLIR val images right (20 people, 20 not), never trained on | `ml/results/judge_pool/manifest.json` (verdict vs truth at threshold 0.6) |
| Training | **5 epochs, 13.5 min** on the testing laptop's GPU; 13,266 training crops (FLIR train 3,000 person + 3,000 not, SDT indoor 4,800 person + 3,939 empty floor), 1,473 held out; final holdout accuracy 98.6%; promoted over the previous model (96.67% vs 96.17% on FLIR val) | `ml/results/train_history.json`, `docs/assets/training_curve.png`, `py ml/train.py --history` |
| Where it looked | Grad-CAM per runtime crop, fused layers, heat on the body | `ml/crops/runtime/heatmaps/`, `py ml/gradcam.py` |
| Unsure, moving closer | A hot spot scored 0.35 to 0.75 from a distance is judged again from 2 m on a close-up crop; the shipped pairs score **0.58 → 1.00** (person) and **0.44 → 0.00** (car) | `ml/crops/runtime/unsure_sources.json`, `server/tests/test_look_closer.py` |

## Benchmarks (in simulation)

| Say | Number | Source |
|---|---|---|
| Deadzone vs "stop when the signal dies" | collapse_01, default radio, 30 seeds: Deadzone reported **88 of 90** survivors (98%), the baseline **38 of 90** (42%); Command map **89% vs 43%**; Deadzone averages 3.6 relays per run | `docs/assets/benchmark_v2.md` / `.json`, `py ml/benchmark_v2.py` |
| Radio sensitivity sweep | 9 radio settings on collapse_01 (30 seeds each) and 3 generated buildings (10 seeds each): **Deadzone ahead in all 15**, fewer survivors than the baseline in **0 of 330 paired runs** | same |
| At published 2.4 GHz values | NIST wall losses (Stone 1997, NISTIR 6055: drywall 2, brick 6, concrete 29 dB) and the ITU-R P.1238 office exponent 3.0: Deadzone ahead in **9 of 9** settings, fewer in **0 of 150** paired runs | `docs/assets/benchmark_published.md` / `.json`, `py ml/benchmark_published.py` |
| Belief-guided search (Phase 2, off by default) | seed 7, 3 robots, P-1, `DZ_SEARCH_BAYES=1` with the building prior: last survivor found at **157 s instead of 246 s**; map coverage **89.2% vs 84.8%** at 180 s; the dark find moves 28 s later (why the flag is off for the demo). Flat prior: S3 never found, coverage stalls at 87.2% | `py ml/bayes_compare.py` (writes the table), `docs/team/history/rayan.md` 16:20, `server/tests/test_search_bayes.py` |
| Wall-clock speed-ups ("6x real time") | laptop-dependent | **do not say** |

## The radio model (our choices, in simulation)

| Say | Number | Source |
|---|---|---|
| Path loss | L0 = **40 dB at 1 m**, exponent **n = 2.6**, tx 20 dBm, noise floor −95 dBm | `server/deadzone/network/propagation.py` |
| Link hysteresis | up above **−82 dBm**, down below **−88 dBm** | same |
| Wall losses | drywall **4**, brick **10**, concrete **16**, metal **22**, rubble **8** dB per crossing | `data/floorplans/collapse_01.json` (`materials`) |
| Furniture | **1 dB per piece crossed** (`DZ_OBSTACLES=1`); Rappaport, *Wireless Communications: Principles and Practice*, 2nd ed., Table 4.3, light partitions 1–4 dB at 1.3 GHz, low end because the footprints are open shelving and desks | `server/deadzone/floorplan.py` (`FURNITURE_LOSS_DB`) |
| ZW's margin | the demo plan's ZW zone has **1.6 dB** of command-post link margin by design (−86.4 dBm against −88), so it is the first zone to go marginal when anything sits on that line; ZB has 3.9 dB; ZNE is dead on purpose (−135 dBm) | `server/tests/test_obstacles.py`, rayan.md 17:40 |
| Published comparison | our walls vs NIST / ITU-R values side by side | `docs/assets/benchmark_published.md` |

## Robots

| Say | Number | Source |
|---|---|---|
| Scheduler | rate-monotonic, 6 tasks, utilization **0.377**, Liu & Layland bound **0.735**; the safety task never misses, perception overload (O key) shows misses | `server/deadzone/robot/scheduler.py` (`utilization()`, `liu_layland_bound()`), `server/tests/test_demo_guard.py` |
| Lost-link budget | **60 s** in the demo plan P-1; robot default 45 s | `server/tests/test_demo_guard.py` (`demo_plan`), `server/deadzone/robot/robot.py` |
| Relay drop rule | 2 relays per robot; drop while still linked when the upstream link falls below **−76 dBm** (floor −81), at least **4 m** from the last relay, never in a no-go area; a beacon relay is left next to a survivor found in the dark | `server/deadzone/robot/robot.py` (`RELAY_*`) |
| Survivor clearance | motion plans keep **0.5 m** off confirmed survivors; measured closest approach in the demo run 1.96 m | `server/deadzone/robot/robot.py` (`SURVIVOR_CLEAR_M`), rayan.md 10:00 |
| Demo beats (sim seconds, seed 7, `DZ_OBSTACLES=1`) | S3 found 14.1, D1 rejected 57.9, RL1 dropped 67.5, R2 dark 91.3, **S1 found dark 102.7, reported 118.5** (15.8 s late), R key 162.5 → S1 rerouted 162.8 (52.1 m), F 177.5, O 187.5, S2 found 219.4; clock at 1.5x = Space + sim / 1.5 | `server/tests/test_demo_guard.py` (`BEATS`, `DIRECTOR`), `docs/DEMO.md` |
| Generated buildings | any seed; `showcase_01` is 80 x 60 m, 36 rooms, two steel dead zones, 159 furniture footprints, a three-area earthquake at 184 / 194 / 246 s | `data/floorplans/generate.py`, `data/floorplans/showcase_01.json` |

## Datasets and sources

| Say | Detail | Source |
|---|---|---|
| Teledyne FLIR ADAS v2 | street thermal frames with person boxes: training crops, the 1,200-image held-out test, the judge pool, decoys. License: Teledyne's free dataset terms (not reproduced in this repo): say "Teledyne FLIR ADAS v2", **do not quote license terms** | `ml/prep_crops.py`, `ml/make_judge_pool.py`, `README.md` |
| SDT, Synthetic Depth & Thermal | real indoor split only (FLIR Lepton 3.5 frames), **CC BY 4.0** (the record also says non-commercial research use), Zenodo 4124309 | `ml/prep_sdt.py`, `README.md` |
| Rappaport | *Wireless Communications: Principles and Practice*, 2nd ed., Table 4.3 (partition losses) | `server/deadzone/floorplan.py` |
| NIST | Stone, W. C. (1997), *Electromagnetic Signal Attenuation in Construction Materials*, NISTIR 6055 | `docs/assets/benchmark_published.md` |
| ITU-R | Recommendation P.1238, indoor path-loss exponents at 2.4 GHz | `docs/assets/benchmark_published.md` |
| Asset pack | Poly Haven and Poly Pizza, all CC0 | `assets-pack/CREDITS.md` |

## Slide assets

All in `docs/assets/`, rebuilt with `py ml/make_slide_assets.py` (`--only <section>` to pick):

| Image | Shows | Section / source data |
|---|---|---|
| `training_curve.png` | loss and accuracy per epoch, training vs held-out | `curve`, `ml/results/train_history.json` |
| `calibration.png` | reliability diagram, street and indoor | `calibration`, replot of `ml/results/calibration.json` (`py ml/calibration.py` scores) |
| `confusion_matrix.png` | 1,200 held-out FLIR crops at threshold 0.6 | `confusion`, copied from `ml/results/` (`py ml/eval.py`) |
| `benchmark_v2.png` | Deadzone vs baseline across the radio sweep | `benchmark`, `py ml/benchmark_v2.py --replot` |
| `benchmark_published.png` | the same at NIST / ITU-R values | `benchmark`, `py ml/benchmark_published.py --replot` |
| `gradcam_strip.png` | the six demo hot spots: crop, Grad-CAM, verdict and score | `gradcam`, `ml/crops/runtime/manifest.json` (`py ml/gradcam.py`) |
| `stats_card.png` | accuracy / precision / recall card | `stats`, `ml/results/metrics.json` |
| `crops_grid.png`, `pipeline.png` | held-out examples and the pipeline diagram | `crops`; needs the FLIR val split and the SDT frames, so it is rebuilt on the testing laptop |
| `benchmark.png` | the first (v1) benchmark | `py ml/benchmark.py`, kept for the record; say v2 numbers |
