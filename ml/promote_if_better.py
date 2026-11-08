"""Swap in a retrained detector only if it is at least as good as the shipped one.

    py ml/promote_if_better.py --candidate ml/models/detector_logged.pt

Both models are scored on the same held-out FLIR val crops (ml/data/crops/val) at the deployed
threshold. The candidate replaces ml/models/detector.pt only if
  - its accuracy is equal or better, and
  - it still gets the 6 demo props right (survivor crops >= threshold, decoy crops below),
so the demo cannot change behind our back. The old model is kept as detector_prev.pt.
The decision is written into the training history JSON (if given), so the AI Lab can say
whether the curve belongs to the shipped model.
Exit code 0 either way; read the printed decision.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))
import common  # noqa: E402


def accuracy(model, thr, crops):
    ds = ImageFolder(crops, transform=common.eval_transform())
    assert ds.classes == common.CLASSES, ds.classes
    correct = n = 0
    for x, y in DataLoader(ds, batch_size=256):
        p = common.predict_pos_prob(model, x)
        correct += int(((p >= thr).long() == y).sum())
        n += y.numel()
    return correct / max(n, 1), n


def props_ok(model, thr, runtime):
    tf = common.eval_transform()
    bad = []
    for f in sorted(Path(runtime).glob("*.png")):
        p = float(common.predict_pos_prob(model, tf(Image.open(f)).unsqueeze(0))[0])
        if (p >= thr) != f.stem.startswith("pos"):
            bad.append(f"{f.name} {p:.3f}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--shipped", default=str(ML_DIR / "models" / "detector.pt"))
    ap.add_argument("--crops", default=str(ML_DIR / "data" / "crops" / "val"))
    ap.add_argument("--runtime", default=str(ML_DIR / "crops" / "runtime"))
    ap.add_argument("--history", default=str(ML_DIR / "results" / "train_history.json"))
    args = ap.parse_args()

    torch.set_num_threads(4)
    old, old_ck = common.load_checkpoint(args.shipped, "cpu")
    new, new_ck = common.load_checkpoint(args.candidate, "cpu")
    thr = float(old_ck.get("threshold", common.THRESHOLD))
    acc_old, n = accuracy(old, thr, args.crops)
    acc_new, _ = accuracy(new, thr, args.crops)
    bad = props_ok(new, thr, args.runtime)
    promote = acc_new >= acc_old and not bad
    print(f"held-out FLIR val (n={n}): shipped {acc_old:.4f}, candidate {acc_new:.4f}")
    if bad:
        print("candidate gets demo props wrong:", ", ".join(bad))
    if promote:
        shutil.copy2(args.shipped, Path(args.shipped).with_name("detector_prev.pt"))
        shutil.copy2(args.candidate, args.shipped)
        print(f"PROMOTED: {args.candidate} -> {args.shipped} (old one kept as detector_prev.pt)")
    else:
        print(f"KEPT the shipped model {args.shipped}")
    h = Path(args.history)
    if h.is_file():
        d = json.loads(h.read_text())
        d.update(promoted=promote, shipped_acc=round(acc_old, 4), candidate_acc=round(acc_new, 4),
                 test_n=n)
        h.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
