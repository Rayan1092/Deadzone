"""Evaluate the detector on the held-out FLIR val crops.

  py ml/eval.py --crops ml/data/crops/val --model ml/models/detector.pt

Writes ml/results/metrics.json and ml/results/confusion_matrix.png.
"""
import argparse
import json
import sys
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

ML_DIR = Path(__file__).resolve().parent


def plot_confusion(cm, metrics, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["Background", "Person"]
    fig, ax = plt.subplots(figsize=(4.6, 4.2), dpi=150)
    vmax = max(max(r) for r in cm)
    ax.imshow(cm, cmap="Blues", vmin=0, vmax=vmax)
    for i in range(2):
        for j in range(2):
            v = cm[i][j]
            ax.text(j, i, f"{v}", ha="center", va="center", fontsize=14,
                    color="white" if v > vmax * 0.55 else "#1a1a1a")
    ax.set_xticks([0, 1], labels)
    ax.set_yticks([0, 1], labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(f"Survivor detector, FLIR val (n={metrics['n']})\n"
                 f"acc {metrics['accuracy']:.3f}  prec {metrics['precision']:.3f}  rec {metrics['recall']:.3f}",
                 fontsize=10)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", default=str(ML_DIR / "data" / "crops" / "val"))
    ap.add_argument("--model", default=str(ML_DIR / "models" / "detector.pt"))
    ap.add_argument("--out", default=str(ML_DIR / "results"))
    ap.add_argument("--runtime", default=str(ML_DIR / "crops" / "runtime"))
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, ckpt = common.load_checkpoint(args.model, device)
    thr = ckpt.get("threshold", common.THRESHOLD)
    tf = common.eval_transform()
    ds = ImageFolder(args.crops, transform=tf)
    assert ds.classes == common.CLASSES, ds.classes
    dl = DataLoader(ds, batch_size=256)

    probs, ys = [], []
    for x, y in dl:
        probs.append(common.predict_pos_prob(model, x.to(device)).cpu())
        ys.append(y)
    p = torch.cat(probs)
    y = torch.cat(ys)
    pred = (p >= thr).long()
    tp = int(((pred == 1) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    n = tp + tn + fp + fn
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    metrics = {
        "n": n, "threshold": thr,
        "accuracy": (tp + tn) / max(n, 1), "precision": prec, "recall": rec,
        "f1": 2 * prec * rec / max(prec + rec, 1e-9),
        "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "arch": ckpt.get("arch"), "epoch": ckpt.get("epoch"),
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    plot_confusion([[tn, fp], [fn, tp]], metrics, out / "confusion_matrix.png")
    print(json.dumps(metrics, indent=2))
    print(f"wrote {out / 'metrics.json'} and {out / 'confusion_matrix.png'}")

    rt = Path(args.runtime)
    if rt.is_dir():
        print("runtime crops (want pos >= thr, neg < thr):")
        for f in sorted(rt.glob("*.png")):
            x = tf(Image.open(f)).unsqueeze(0).to(device)
            s = float(common.predict_pos_prob(model, x)[0])
            ok = (s >= thr) == f.name.startswith("pos")
            print(f"  {f.name}: {s:.3f} {'ok' if ok else 'WRONG'}")


if __name__ == "__main__":
    main()
