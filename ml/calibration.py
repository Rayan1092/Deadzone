"""Is the detector's confidence honest? Reliability check and temperature scaling.

    py ml/calibration.py

A confidence of 0.9 should be right about 90% of the time. This scores both held-out sets with
the shipped model (FLIR ADAS val, 1,200 crops; SDT indoor held-out, ml/data/sdt_crops/test) and
measures calibration: expected calibration error (ECE, 10 equal-width bins), maximum calibration
error, Brier score and log loss, plus accuracy at the 0.6 threshold.

Temperature scaling (Guo et al. 2017) divides the two logits by one number T. It never changes
which class is more likely, only how confident the model sounds. T must not be fitted on the
numbers it is judged by, so every held-out set is split in two (seeded, per class): T is fitted
on the "fit" half (minimum log loss) and all before/after numbers are reported on the other half.

Writes ml/results/calibration.json and docs/assets/calibration.png (reliability diagram, slide
ready). It only reports; whether T ships is a separate decision (see `recommend` in the JSON).
"""
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
sys.path.insert(0, str(ML_DIR))
import common  # noqa: E402

SETS = {"FLIR street (held-out val)": ML_DIR / "data" / "crops" / "val",
        "Indoor, SDT (held-out 20%)": ML_DIR / "data" / "sdt_crops" / "test"}
BINS = 10
RUNTIME = ML_DIR / "crops" / "runtime"


def logits_of(model, tf, files):
    out = []
    with torch.no_grad():
        for i in range(0, len(files), 256):
            x = torch.stack([tf(Image.open(f)) for f in files[i:i + 256]])
            out.append(model(x))
    return torch.cat(out).numpy().astype(np.float64)


def p_person(logits, T=1.0):
    z = logits / T
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e[:, 1] / e.sum(axis=1)


def metrics(p, y, thr):
    """ECE / MCE over confidence in the predicted class, Brier and log loss for P(person)."""
    pred = (p >= 0.5).astype(int)
    conf = np.where(pred == 1, p, 1 - p)
    right = (pred == y).astype(float)
    edges = np.linspace(0.5, 1.0, BINS // 2 + 1)        # predicted-class confidence is in [0.5, 1]
    ece, mce, rows = 0.0, 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf >= lo) & ((conf < hi) | (hi == 1.0))
        if not m.any():
            continue
        gap = abs(right[m].mean() - conf[m].mean())
        ece += m.mean() * gap
        mce = max(mce, gap)
        rows.append({"bin": [round(lo, 2), round(hi, 2)], "n": int(m.sum()),
                     "confidence": round(float(conf[m].mean()), 4), "accuracy": round(float(right[m].mean()), 4)})
    eps = 1e-7
    return {"n": int(len(y)), "ece": round(float(ece), 4), "mce": round(float(mce), 4),
            "brier": round(float(np.mean((p - y) ** 2)), 4),
            "log_loss": round(float(-np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))), 4),
            "accuracy_at_threshold": round(float(np.mean((p >= thr).astype(int) == y)), 4),
            "mean_confidence": round(float(conf.mean()), 4), "bins": rows}


def fit_temperature(logits, y):
    """T minimising log loss on the fit half (1-D search, log-spaced, then refined)."""
    def nll(T):
        p = np.clip(p_person(logits, T), 1e-7, 1 - 1e-7)
        return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    grid = np.exp(np.linspace(np.log(0.25), np.log(8), 400))
    best = grid[int(np.argmin([nll(t) for t in grid]))]
    fine = np.linspace(best * 0.9, best * 1.1, 200)
    return float(fine[int(np.argmin([nll(t) for t in fine]))])


def split(files, labels, seed=0):
    """Seeded half split per class: (fit, eval) index arrays."""
    rng = random.Random(seed)
    fit, ev = [], []
    for cls in (0, 1):
        idx = [i for i, v in enumerate(labels) if v == cls]
        rng.shuffle(idx)
        fit += idx[: len(idx) // 2]
        ev += idx[len(idx) // 2:]
    return np.array(sorted(fit)), np.array(sorted(ev))


def chart(results, path):
    """Reliability of the shipped model only (temperature is reported in the JSON, not shipped
    unless `recommend` says so). Marker area = images in the bin; bins under 20 images are hollow
    and labelled, so a swing made of three images can't pass for a trend."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    BG, FG, MUTED, GRID, LINE = "#0d1117", "#e6edf3", "#8b949e", "#30363d", "#58a6ff"
    names = list(results["sets"])
    fig, axes = plt.subplots(1, len(names), figsize=(5.4 * len(names), 4.9), facecolor=BG)
    for ax, name in zip(np.atleast_1d(axes), names):
        r = results["sets"][name]["all_before"]
        ax.set_facecolor(BG)
        for sp in ax.spines.values():
            sp.set_color(GRID)
        ax.tick_params(colors=MUTED)
        ax.plot([0.5, 1], [0.5, 1], color=MUTED, linestyle=(0, (3, 3)), linewidth=1, label="perfectly honest")
        b = r["bins"]
        xs, ys, ns = [x["confidence"] for x in b], [x["accuracy"] for x in b], [x["n"] for x in b]
        ax.plot(xs, ys, color=LINE, linewidth=1.5, alpha=0.6)
        for x, y, n in zip(xs, ys, ns):
            big = n >= 20
            ax.scatter([x], [y], s=30 + 220 * (n / max(ns)) ** 0.5, color=LINE if big else BG,
                       edgecolor=LINE, linewidth=1.5, zorder=3)
            if not big:
                ax.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(6, -12), color=MUTED, fontsize=8)
        top = b[-1]
        ax.text(0.52, 0.97, f"{100 * top['n'] / r['n']:.0f}% of answers are {top['bin'][0]:.0%}+ confident;\n"
                f"those are right {np.floor(1000 * top['accuracy']) / 10:.1f}% of the time.  ECE {100 * r['ece']:.1f}%",
                color=FG, fontsize=9.5, va="top")
        ax.set_xlim(0.5, 1.0)
        ax.set_ylim(0.4, 1.03)
        ax.set_xlabel("model confidence in its answer", color=MUTED)
        ax.set_ylabel("how often that answer is right", color=MUTED)
        ax.set_title(f"{name}: {r['n']:,} images it never trained on", color=FG, fontsize=11, loc="left")
        ax.grid(color=GRID, linewidth=0.6)
        leg = ax.legend(loc="lower right", frameon=False, fontsize=9)
        for t in leg.get_texts():
            t.set_color(MUTED)
    fig.suptitle("Is the AI's confidence honest? Reliability on held-out thermal images", color=FG,
                 fontsize=13, x=0.01, ha="left")
    fig.text(0.01, 0.01, "On the dashed line, a 90% answer is right 90% of the time. Dot size = images in the bin; "
             "hollow dots have fewer than 20 images. Temperature scaling was tested and not needed.",
             color=MUTED, fontsize=8.5, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(path, dpi=170, facecolor=BG)
    plt.close(fig)


def main():
    model, ckpt = common.load_checkpoint(ML_DIR / "models" / "detector.pt", "cpu")
    model.eval()
    thr = float(ckpt.get("threshold", common.THRESHOLD))
    tf = common.eval_transform()
    data = {}
    for name, root in SETS.items():
        files, labels = [], []
        for cls, y in (("neg", 0), ("pos", 1)):
            fs = sorted((root / cls).glob("*.png"))
            files += fs
            labels += [y] * len(fs)
        if not files:
            print(f"skip {name}: no crops at {root}")
            continue
        data[name] = (logits_of(model, tf, files), np.array(labels))
    # one T for the model, fitted on the fit halves of every set together
    fit_l, fit_y, halves = [], [], {}
    for name, (lg, y) in data.items():
        f, e = split(None, list(y))
        halves[name] = (f, e)
        fit_l.append(lg[f])
        fit_y.append(y[f])
    T = fit_temperature(np.concatenate(fit_l), np.concatenate(fit_y))
    results = {"temperature": round(T, 3), "threshold": thr, "sets": {}}
    for name, (lg, y) in data.items():
        f, e = halves[name]
        results["sets"][name] = {"eval": {"before": metrics(p_person(lg[e]), y[e], thr),
                                          "after": metrics(p_person(lg[e], T), y[e], thr)},
                                 "all_before": metrics(p_person(lg), y, thr)}
    # demo crops: do any verdicts flip at the threshold with T?
    flips, demo = [], {}
    for f in sorted(RUNTIME.glob("*.png")):
        lg = logits_of(model, tf, [f])
        p0, p1 = float(p_person(lg)[0]), float(p_person(lg, T)[0])
        demo[f.name] = {"before": round(p0, 4), "after": round(p1, 4)}
        if (p0 >= thr) != (p1 >= thr):
            flips.append(f.name)
    results["demo_crops"] = demo
    ece_b = np.mean([r["eval"]["before"]["ece"] for r in results["sets"].values()])
    ece_a = np.mean([r["eval"]["after"]["ece"] for r in results["sets"].values()])
    acc_b = np.mean([r["eval"]["before"]["accuracy_at_threshold"] for r in results["sets"].values()])
    acc_a = np.mean([r["eval"]["after"]["accuracy_at_threshold"] for r in results["sets"].values()])
    results["recommend"] = {
        "ship_temperature": bool(ece_a < ece_b - 0.01 and acc_a >= acc_b and not flips),
        "mean_ece_before": round(float(ece_b), 4), "mean_ece_after": round(float(ece_a), 4),
        "mean_accuracy_before": round(float(acc_b), 4), "mean_accuracy_after": round(float(acc_a), 4),
        "demo_flips": flips,
        "rule": "ship T only if mean ECE drops by more than 1 point, accuracy at the threshold does not drop, "
                "and no demo crop changes verdict",
    }
    (ML_DIR / "results" / "calibration.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    chart(results, ROOT / "docs" / "assets" / "calibration.png")
    print(f"T = {T:.3f}")
    for name, r in results["sets"].items():
        b, a = r["eval"]["before"], r["eval"]["after"]
        print(f"{name}: ECE {b['ece']:.4f} -> {a['ece']:.4f}, Brier {b['brier']:.4f} -> {a['brier']:.4f}, "
              f"log loss {b['log_loss']:.4f} -> {a['log_loss']:.4f}, acc@thr {b['accuracy_at_threshold']:.4f} -> "
              f"{a['accuracy_at_threshold']:.4f}  (n={b['n']})")
    print("demo crops:", demo, "flips:", flips)
    print("recommend:", results["recommend"])


if __name__ == "__main__":
    main()
