# AI Lab export serving

Opt in with `DZ_AI_LAB=1` and restart the backend. Default is off. This serves
versioned ML evidence for Yusuf's L-key overlay; it does not change the simulation,
Command data, Gemini tools or robot controls.

| URL | Repository export |
| --- | --- |
| `/ai-lab/results/metrics.json` | `ml/results/metrics.json` |
| `/ai-lab/results/confusion_matrix.png` | `ml/results/confusion_matrix.png` |
| `/ai-lab/slides/pipeline.png` | `docs/assets/pipeline.png` |
| `/ai-lab/slides/crops_grid.png` | `docs/assets/crops_grid.png` |
| `/ai-lab/slides/stats_card.png` | `docs/assets/stats_card.png` |
| `/ai-lab/slides/benchmark.json` | `docs/assets/benchmark.json` |

Rayan can export additional images/JSON under `ml/results/`; their paths become
`/ai-lab/results/<relative path>`. Rayan owns the contents and any manifest schema.
Per-epoch training curves and training examples are not fabricated by the server.
Label examples by the split in Rayan's export; `crops_grid.png` alone does not
establish that they are training examples. Benchmark numbers retain their
simulation labels. Live survivor crops/Grad-CAM keep the existing `/crops` contract
and delivered-only Command boundary.

Both roots allow GET/HEAD of PNG, JPEG, WebP, SVG and JSON files, with normal media
types and cache revalidation. No directory listing is provided. Disabled, missing,
hidden, unsupported and escaping paths return 404. Enabled mutation requests
return 405. Model weights, datasets and environment files are outside this API.
Frontend overlay, live robot-eye object boxes, and physical-device dry runs remain
their respective owners' work. Keep the feature off until the testing laptop has
passed its dry run.
