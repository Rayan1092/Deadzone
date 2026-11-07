"""Pick the held-out crops the sim floor plan points at (ml/crops/runtime/).

  py ml/pick_runtime.py --crops ml/data/crops/val --model ml/models/detector.pt

Survivors -> pos_0001..0003.png, decoys (radiator, engine, coffee machine stand-ins) -> neg_0001..0003.png.
Candidates are close-up crops only (robots see within 5 m): source box >= --min-side px.
Decoys come only from object-centered negatives (cars etc.), never random background,
which can hold unlabeled people. Candidates are walked in a seeded order; with a model,
ones it gets wrong are skipped (and counted) so the demo props behave as the slide says.
The real performance number is the held-out eval in ml/results/metrics.json, not these 6.
"""
import argparse
import json
import random
import sys
from pathlib import Path

from PIL import Image

ML_DIR = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", default=str(ML_DIR / "data" / "crops" / "val"))
    ap.add_argument("--model", default=str(ML_DIR / "models" / "detector.pt"))
    ap.add_argument("--out", default=str(ML_DIR / "crops" / "runtime"))
    ap.add_argument("--min-side", type=int, default=64)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    crops = Path(args.crops)
    manifest = json.loads((crops / "manifest.json").read_text())

    score = None
    if Path(args.model).is_file():
        sys.path.insert(0, str(ML_DIR))
        import common
        model, ckpt = common.load_checkpoint(args.model, "cpu")
        thr = ckpt.get("threshold", common.THRESHOLD)
        tf = common.eval_transform()

        def score(path):
            return float(common.predict_pos_prob(model, tf(Image.open(path)).unsqueeze(0))[0])
    else:
        print(f"no model at {args.model}: picking without verification")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    for cls in ("pos", "neg"):
        cands = [m for m in manifest[cls]
                 if m["box"][2] - m["box"][0] >= args.min_side and (cls == "pos" or m.get("object"))]
        cands = [m for m in cands if (crops / cls / f"{m['i']:05d}.png").is_file()]
        rng.shuffle(cands)
        picked, skipped = 0, 0
        for m in cands:
            if picked == args.k:
                break
            f = crops / cls / f"{m['i']:05d}.png"
            s = score(f) if score else None
            if s is not None and (s >= thr) != (cls == "pos"):
                skipped += 1
                continue
            picked += 1
            Image.open(f).save(out / f"{cls}_{picked:04d}.png")
            print(f"  {cls}_{picked:04d}.png <- {Path(m['src']).name} box {m['box']}"
                  + (f"  p(person)={s:.3f}" if s is not None else ""))
        print(f"{cls}: {len(cands)} candidates, picked {picked}, skipped {skipped} misclassified")
    print(f"runtime crops -> {out}")


if __name__ == "__main__":
    main()
