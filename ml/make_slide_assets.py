"""Build ML slide assets into docs/assets/.

  py ml/make_slide_assets.py                      (all sections; crops needs the FLIR dataset in
                                                   ml/data/flir and ml/models/detector.pt)
  py ml/make_slide_assets.py --only curve stats   (just these sections)

- confusion_matrix.png : copied unchanged from ml/results                              [confusion]
- crops_grid.png       : 4 person crops + 4 rejected warm-object crops from the HELD-OUT FLIR val
                         split, cut like ml/prep_crops.py and scored by ml/models/detector.pt [crops]
- pipeline.png         : thermal camera -> 96x96 crop -> MobileNetV3-Small (6 MB, onboard) -> verdict
                         (uses one crop from the grid, so it belongs to the crops section)  [crops]
- stats_card.png       : numbers from ml/results/metrics.json                            [stats]
- training_curve.png   : loss and accuracy per epoch from ml/results/train_history.json
                         (written by ml/train.py --history); skipped while the curve is empty [curve]
- calibration.png      : reliability diagram replotted from ml/results/calibration.json
                         (ml/calibration.py scores the sets)                                  [calibration]
- benchmark_v2.png, benchmark_published.png : replotted from their saved JSON
                         (ml/benchmark_v2.py --replot, ml/benchmark_published.py --replot)     [benchmark]
- gradcam_strip.png    : the six demo crops (S1-S3, D1-D3) with their Grad-CAM, verdict and score
                         from ml/crops/runtime/manifest.json (ml/gradcam.py)                   [gradcam]
"""
import argparse
import json
import random
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from PIL import Image  # noqa: E402

SECTIONS = ("confusion", "crops", "stats", "curve", "calibration", "benchmark", "gradcam")
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("repo", nargs="?", help="repo root (default: this file's parent's parent)")
parser.add_argument("--only", nargs="+", choices=SECTIONS, default=list(SECTIONS), metavar="SECTION",
                    help="build only these sections: " + ", ".join(SECTIONS))
args = parser.parse_args()

REPO = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[1]
ML = REPO / "ml"
OUT = REPO / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ML))

BG, FG, MUTED = "#0f1216", "#e6edf3", "#8b98a5"
WARM, COLD, GREEN, RED = "#ff9f43", "#5dade2", "#2ecc71", "#ff6b6b"
TRAIN, VAL = "#2f86c4", "#d4771c"          # curve series: darker steps of COLD / WARM that pass the
GRID = "#2a313a"                           # dark-surface lightness and colour-blind checks
WARM_OBJECTS = {"car", "motor", "bus", "truck", "bike", "other vehicle"}


# ---------------------------------------------------------------- confusion matrix
def confusion():
    shutil.copy(ML / "results" / "confusion_matrix.png", OUT / "confusion_matrix.png")


# ---------------------------------------------------------------- crops grid + pipeline diagram
def crops_and_pipeline():
    import common
    import prep_crops

    split = ML / "data" / "flir" / "images_thermal_val"
    coco = json.loads((split / "coco.json").read_text())
    cat_name = {c["id"]: c["name"] for c in coco["categories"]}
    images, per_img, person_ids = prep_crops.load_split(split)
    pos, neg = [], []
    for iid, anns in per_img.items():
        im = images[iid]
        w, h = im["width"], im["height"]
        pboxes = [prep_crops.box_square(a["bbox"], w, h) for a in anns if a["category_id"] in person_ids]
        oboxes = [prep_crops.box_square(a["bbox"], w, h) for a in anns if a["category_id"] not in person_ids]
        for a in anns:
            sq = prep_crops.box_square(a["bbox"], w, h)
            if sq[2] - sq[0] < 64:                 # close-ups only, like the runtime props
                continue
            path = split / im["file_name"]
            if a["category_id"] in person_ids:
                bw, bh = a["bbox"][2], a["bbox"][3]
                # a clear standing person: tall box, big in the crop, no vehicle sharing the crop
                if bh >= 1.8 * bw and bh >= 0.6 * (sq[3] - sq[1]) and all(prep_crops.iou(sq, o) < 0.05 for o in oboxes):
                    pos.append((path, sq, "person"))
            elif cat_name[a["category_id"]] in WARM_OBJECTS and all(prep_crops.iou(sq, p) < 0.05 for p in pboxes):
                neg.append((path, sq, cat_name[a["category_id"]]))
    rng = random.Random(7)
    rng.shuffle(pos)
    rng.shuffle(neg)

    model, ckpt = common.load_checkpoint(ML / "models" / "detector.pt", "cpu")
    thr = float(ckpt.get("threshold", common.THRESHOLD))
    tf = common.eval_transform()

    def crop(path, sq):
        return Image.open(path).convert("L").crop(sq).resize((prep_crops.SIZE, prep_crops.SIZE), Image.BILINEAR)

    def pick(cands, want_person, k=4):
        """First k candidates in seeded order, one per source image and (for objects) per label.
        Candidates the model gets wrong are skipped and counted, so the caption can say so."""
        picked, skipped, seen_imgs, seen_labels = [], 0, set(), set()
        for path, sq, label in cands:
            if len(picked) == k:
                break
            if path in seen_imgs or (not want_person and label in seen_labels and len(seen_labels) < 3):
                continue                           # variety: one crop per image, mixed object types
            img = crop(path, sq)
            p = float(common.predict_pos_prob(model, tf(img).unsqueeze(0))[0])
            if (p >= thr) != want_person:
                skipped += 1
                continue
            seen_imgs.add(path)
            seen_labels.add(label)
            picked.append((img, label, p))
        return picked, skipped

    sel_path = ML / "real_crops.json"
    if sel_path.is_file():
        # the curated AI Lab examples (ml/real_crops.py): same images as key L
        import real_crops
        sel = json.loads(sel_path.read_text(encoding="utf-8"))

        def scored(entries, field, want_person):
            """First 4 curated examples the model gets right (the slide's rows say found / rejected)."""
            out, skipped = [], 0
            for e in entries:
                if len(out) == 4:
                    break
                img = real_crops.crop(e["key"], prep_crops.SIZE)
                p = float(common.predict_pos_prob(model, tf(img).unsqueeze(0))[0])
                if (p >= thr) != want_person:
                    skipped += 1
                    continue
                out.append((img, e.get(field) or "", p))
            return out, skipped
        (people, skip_p), (objects, skip_n) = scored(sel["lab_pos"], "pose", True), scored(sel["lab_neg"], "shows", False)
        print(f"crops_grid: curated examples from ml/real_crops.json, skipped {skip_p} person / {skip_n} object the model got wrong")
    else:
        people, skip_p = pick(pos, True)
        objects, skip_n = pick(neg, False)
        print(f"person candidates {len(pos)}, picked 4, skipped {skip_p} the model got wrong")
        print(f"warm-object candidates {len(neg)}, picked 4, skipped {skip_n} the model got wrong")

    fig, axes = plt.subplots(2, 4, figsize=(8.8, 5.2), facecolor=BG)
    for ax, (img, label, p) in zip(axes[0], people):
        ax.imshow(img, cmap="inferno")
        ax.set_title(f"Person  {p * 100:.0f}%", color=GREEN, fontsize=12, fontweight="bold")
        if label and label != "person":
            ax.set_xlabel(label, color=MUTED, fontsize=9)
    for ax, (img, label, p) in zip(axes[1], objects):
        ax.imshow(img, cmap="inferno")
        short = " ".join(label.split(",")[0].split()[-2:]).capitalize() if label else "Not a person"
        ax.set_title(f"{short}  {p * 100:.1f}%", color=RED, fontsize=10.5, fontweight="bold")
    for ax in axes.flat:
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(GRID)
    fig.text(0.02, 0.73, "found", color=GREEN, rotation=90, fontsize=13, va="center", fontweight="bold")
    fig.text(0.02, 0.29, "rejected", color=RED, rotation=90, fontsize=13, va="center", fontweight="bold")
    fig.suptitle("What the onboard model sees: real held-out FLIR thermal frames, P(person)", color=FG, fontsize=13)
    met = json.loads((ML / "results" / "metrics.json").read_text())
    fig.text(0.5, 0.015, f"Threshold {thr:g}  ·  images the model never trained on  ·  overall "
             f"{100 * met['accuracy']:.1f}% on {met['n']:,} held-out FLIR images",
             color=MUTED, fontsize=9, ha="center")
    fig.subplots_adjust(left=0.06, right=0.99, top=0.86, bottom=0.07, wspace=0.08, hspace=0.25)
    fig.savefig(OUT / "crops_grid.png", dpi=200, facecolor=BG)
    plt.close(fig)

    # pipeline diagram
    fig, ax = plt.subplots(figsize=(13, 4.2), facecolor=BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 4.2)
    ax.axis("off")
    sample = people[0][0]
    BW = 2.9                                       # box width
    boxes = [
        (0.2, "Thermal camera", "on the robot\n5 m range, 120° view", COLD),
        (3.4, "Hot spot crop", "96 × 96 px", WARM),
        (6.6, "MobileNetV3-Small", "6 MB, runs onboard\nno signal needed", "#a78bfa"),
        (9.8, "Person or not?", "P(person) ≥ 0.6", GREEN),
    ]
    for x, title, sub, col in boxes:
        ax.add_patch(FancyBboxPatch((x, 1.2), BW, 2.0, boxstyle="round,pad=0.02,rounding_size=0.18",
                                    facecolor="#161b22", edgecolor=col, linewidth=2.2))
        ax.text(x + BW / 2, 2.75, title, color=FG, fontsize=13, ha="center", va="center", fontweight="bold")
        if title == "Hot spot crop":
            ax.text(x + 0.95, 1.9, sub, color=MUTED, fontsize=11, ha="center", va="center")
            ax.imshow(sample, cmap="inferno", extent=(x + 1.75, x + 2.55, 1.45, 2.25), zorder=5)
        else:
            ax.text(x + BW / 2, 1.85, sub, color=MUTED, fontsize=11, ha="center", va="center")
    for x in (3.1, 6.3, 9.5):
        ax.add_patch(FancyArrowPatch((x, 2.2), (x + 0.3, 2.2), arrowstyle="-|>", mutation_scale=22,
                                     color=MUTED, linewidth=2))
    ax.text(9.8 + BW / 2, 0.85, "yes → survivor report, priority 0", color=GREEN, fontsize=10.5, ha="center")
    ax.text(9.8 + BW / 2, 0.45, "no → rejected, no false alarm", color=RED, fontsize=10.5, ha="center")
    ax.text(6.5, 3.75, "Survivor detection runs on the robot, even in a radio dead zone",
            color=FG, fontsize=14, ha="center", fontweight="bold")
    fig.savefig(OUT / "pipeline.png", dpi=200, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- stats card
def stats_card():
    m = json.loads((ML / "results" / "metrics.json").read_text())
    fig, ax = plt.subplots(figsize=(8, 3.4), facecolor=BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 3.4)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.15, 0.15), 7.7, 3.1, boxstyle="round,pad=0.02,rounding_size=0.25",
                                facecolor="#161b22", edgecolor=GRID, linewidth=1.5))
    for x, val, lab in ((1.45, m["accuracy"], "accuracy"), (4.0, m["precision"], "precision"),
                        (6.55, m["recall"], "recall")):
        ax.text(x, 2.05, f"{val * 100:.1f}%", color=FG, fontsize=34, ha="center", va="center", fontweight="bold")
        ax.text(x, 1.35, lab, color=MUTED, fontsize=14, ha="center", va="center")
    ax.text(4.0, 0.78, f"{m['n']:,} held-out FLIR thermal images   ·   MobileNetV3-Small   ·   6 MB",
            color=WARM, fontsize=12, ha="center", va="center")
    lab_path = ML / "results" / "lab.json"
    indoor = json.loads(lab_path.read_text()).get("metrics_indoor") if lab_path.is_file() else None
    if indoor:
        # before = the FLIR-only model on the same held-out indoor frames (see rayan-ml.md, PR #95)
        ax.text(4.0, 0.4, f"Indoor people lying or sitting: 83.9% → {indoor['accuracy'] * 100:.1f}% "
                f"({indoor['n_test']:,} held-out frames)", color=MUTED, fontsize=11, ha="center", va="center")
    fig.savefig(OUT / "stats_card.png", dpi=200, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- training curve
def training_curve():
    """Two panels (loss, accuracy) over epochs, train and held-out series. Loss and accuracy have
    different scales, so they never share an axis. Skipped while train_history.json has no curve."""
    path = ML / "results" / "train_history.json"
    hist = json.loads(path.read_text()) if path.exists() else {}
    curve = hist.get("curve") or []
    if not curve:
        print("training_curve.png skipped: no logged epochs in ml/results/train_history.json yet")
        return
    epochs = [e["epoch"] for e in curve]
    series = [("train", TRAIN, "o"), ("val", VAL, "s")]
    fig, (ax_loss, ax_acc) = plt.subplots(1, 2, figsize=(11, 4.3), facecolor=BG)
    for ax in (ax_loss, ax_acc):
        ax.set_facecolor(BG)
        ax.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=MUTED, labelsize=10)
        ax.set_xticks(epochs)
        ax.set_xlabel("epoch", color=MUTED, fontsize=11)
        ax.margins(x=0.08)
    for key, color, marker in series:
        label = "training crops" if key == "train" else f"held-out crops ({hist.get('holdout', '?'):,})"
        ax_loss.plot(epochs, [e[f"{key}_loss"] for e in curve], color=color, linewidth=2, marker=marker,
                     markersize=7, label=label)
        ax_acc.plot(epochs, [100 * e[f"{key}_acc"] for e in curve], color=color, linewidth=2, marker=marker,
                    markersize=7, label=label)
    ax_loss.set_title("Loss (lower is better)", color=FG, fontsize=12, loc="left")
    ax_acc.set_title("Accuracy", color=FG, fontsize=12, loc="left")
    ax_loss.set_ylim(0, max(max(e["train_loss"], e["val_loss"]) for e in curve) * 1.15)
    lo = min(min(e["train_acc"], e["val_acc"]) for e in curve) * 100
    ax_acc.set_ylim(max(0, (lo // 5) * 5 - 5), 100)
    ax_acc.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    # direct labels on the last point, in text colour (the marker carries the series colour)
    last = curve[-1]
    ax_acc.annotate(f"{100 * last['val_acc']:.1f}% held-out", (epochs[-1], 100 * last["val_acc"]),
                    xytext=(-8, -16), textcoords="offset points", ha="right", color=FG, fontsize=10)
    ax_loss.annotate(f"{last['val_loss']:.3f}", (epochs[-1], last["val_loss"]),
                     xytext=(-8, 8), textcoords="offset points", ha="right", color=FG, fontsize=10)
    leg = ax_loss.legend(loc="upper right", frameon=False, fontsize=10)
    for text in leg.get_texts():
        text.set_color(FG)
    arch = {"mobilenet_v3_small": "MobileNetV3-Small"}.get(hist.get("arch"), hist.get("arch", ""))
    fig.suptitle(f"Training the onboard detector: {arch}, {len(curve)} epochs", color=FG, fontsize=14,
                 fontweight="bold", x=0.02, ha="left")
    secs = sum(e.get("seconds", 0) for e in curve)
    device = {"cuda": "GPU", "cpu": "CPU"}.get(hist.get("device"), hist.get("device", ""))
    line1 = [f"{hist.get('train', '?'):,} training / {hist.get('holdout', '?'):,} held-out crops from the FLIR train split"]
    if secs:
        where = f"the testing laptop's {device}" if device else "the testing laptop"
        line1.append(f"{secs / 60:.1f} min total on {where}")
    line2 = []
    if hist.get("test_n") and hist.get("candidate_acc") is not None:
        line2.append(f"this model: {100 * hist['candidate_acc']:.1f}% on the separate {hist['test_n']:,}-image FLIR val set")
        if hist.get("shipped_acc") is not None:
            line2.append(("promoted, " if hist.get("promoted") else "not promoted, ")
                         + (f"equal to the previous model" if hist["shipped_acc"] == hist["candidate_acc"]
                            else f"previous model {100 * hist['shipped_acc']:.1f}%"))
    fig.text(0.02, 0.05, "  ·  ".join(line1), color=MUTED, fontsize=9, ha="left")
    if line2:
        fig.text(0.02, 0.012, "  ·  ".join(line2), color=MUTED, fontsize=9, ha="left")
    fig.subplots_adjust(left=0.07, right=0.985, top=0.82, bottom=0.23, wspace=0.22)
    fig.savefig(OUT / "training_curve.png", dpi=200, facecolor=BG)
    plt.close(fig)


# ---------------------------------------------------------------- calibration (replot from JSON)
def calibration():
    import calibration as cal
    path = ML / "results" / "calibration.json"
    if not path.exists():
        print("calibration.png skipped: run py ml/calibration.py first")
        return
    cal.chart(json.loads(path.read_text(encoding="utf-8")), OUT / "calibration.png")


# ---------------------------------------------------------------- benchmark charts (replot from JSON)
def benchmarks():
    import subprocess
    for script, data in (("benchmark_v2.py", "benchmark_v2.json"), ("benchmark_published.py", "benchmark_published.json")):
        if not (OUT / data).exists():
            print(f"{data} missing: run py ml/{script} first")
            continue
        subprocess.run([sys.executable, str(ML / script), "--replot", "--out", str(OUT)], check=True)


# ---------------------------------------------------------------- Grad-CAM strip of the six demo crops
def gradcam_strip():
    """Top row: the real thermal crop the robot judges; bottom row: the same crop with the model's
    Grad-CAM (where it looked). One column per demo survivor and decoy, verdict and score as the
    model gives them."""
    runtime = ML / "crops" / "runtime"
    m = json.loads((runtime / "manifest.json").read_text(encoding="utf-8"))
    crops = [c for c in m["crops"] if c.get("id")]
    crops.sort(key=lambda c: (c["id"][0] != "S", c["id"]))
    fig, axes = plt.subplots(2, len(crops), figsize=(2.2 * len(crops), 5.4), facecolor=BG)
    for col, c in enumerate(crops):
        person = c["label"] == "person"
        top, bottom = axes[0][col], axes[1][col]
        top.imshow(Image.open(runtime / c["file"]).convert("L"), cmap="inferno")
        bottom.imshow(Image.open(runtime / c["heatmap"]).convert("RGB"))
        verdict = "person" if c["predicted"] == "person" else "not a person"
        top.set_title(f"{c['id']}  {verdict}  {c['conf'] * 100:.1f}%" if not person else f"{c['id']}  {verdict}  {c['conf'] * 100:.0f}%",
                      color=GREEN if c["predicted"] == "person" else RED, fontsize=10.5, fontweight="bold")
        shows = c.get("shows") or c.get("object") or ""
        if shows:
            import textwrap
            bottom.set_xlabel("
".join(textwrap.wrap(str(shows), 26)[:2]), color=MUTED, fontsize=8.5)
    for ax in axes.flat:
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color(GRID)
    fig.text(0.012, 0.72, "thermal crop", color=FG, rotation=90, fontsize=11, va="center")
    fig.text(0.012, 0.30, "where the AI looked", color=FG, rotation=90, fontsize=11, va="center")
    fig.suptitle("The six demo hot spots as the onboard model sees them", color=FG, fontsize=13, x=0.02, ha="left")
    fig.text(0.02, 0.012, "Real thermal camera images, Teledyne FLIR dataset (held out)  ·  Grad-CAM on the person class  ·  "
             f"threshold {m.get('threshold', 0.6)}", color=MUTED, fontsize=9, ha="left")
    fig.subplots_adjust(left=0.05, right=0.99, top=0.88, bottom=0.13, wspace=0.08, hspace=0.22)
    fig.savefig(OUT / "gradcam_strip.png", dpi=150, facecolor=BG)
    plt.close(fig)


BUILD = {"confusion": confusion, "crops": crops_and_pipeline, "stats": stats_card, "curve": training_curve,
         "calibration": calibration, "benchmark": benchmarks, "gradcam": gradcam_strip}
for name in SECTIONS:
    if name in args.only:
        BUILD[name]()
print("assets ->", OUT, sorted(p.name for p in OUT.iterdir()))
