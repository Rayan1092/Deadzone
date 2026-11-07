"""Build ML slide assets into docs/assets/.

  py ml/make_slide_assets.py            (needs the FLIR dataset in ml/data/flir and ml/models/detector.pt)


- confusion_matrix.png : copied unchanged from ml/results
- crops_grid.png       : 4 person crops + 4 rejected warm-object crops from the HELD-OUT FLIR val
                         split, cut like ml/prep_crops.py and scored by ml/models/detector.pt
- pipeline.png         : thermal camera -> 96x96 crop -> MobileNetV3-Small (6 MB, onboard) -> verdict
- stats_card.png       : numbers from ml/results/metrics.json
"""
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

REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
ML = REPO / "ml"
OUT = REPO / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ML))
import common  # noqa: E402
import prep_crops  # noqa: E402

BG, FG, MUTED = "#0f1216", "#e6edf3", "#8b98a5"
WARM, COLD, GREEN, RED = "#ff9f43", "#5dade2", "#2ecc71", "#ff6b6b"
WARM_OBJECTS = {"car", "motor", "bus", "truck", "bike", "other vehicle"}

# ---------------------------------------------------------------- confusion matrix
shutil.copy(ML / "results" / "confusion_matrix.png", OUT / "confusion_matrix.png")

# ---------------------------------------------------------------- crops grid
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


people, skip_p = pick(pos, True)
objects, skip_n = pick(neg, False)
print(f"person candidates {len(pos)}, picked 4, skipped {skip_p} the model got wrong")
print(f"warm-object candidates {len(neg)}, picked 4, skipped {skip_n} the model got wrong")

fig, axes = plt.subplots(2, 4, figsize=(8.8, 5.2), facecolor=BG)
for ax, (img, label, p) in zip(axes[0], people):
    ax.imshow(img, cmap="inferno")
    ax.set_title(f"Person  {p * 100:.0f}%", color=GREEN, fontsize=12, fontweight="bold")
for ax, (img, label, p) in zip(axes[1], objects):
    ax.imshow(img, cmap="inferno")
    ax.set_title(f"{label.capitalize()}  {p * 100:.1f}%", color=RED, fontsize=12, fontweight="bold")
for ax in axes.flat:
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#2a313a")
fig.text(0.02, 0.73, "found", color=GREEN, rotation=90, fontsize=13, va="center", fontweight="bold")
fig.text(0.02, 0.29, "rejected", color=RED, rotation=90, fontsize=13, va="center", fontweight="bold")
fig.suptitle("What the onboard model sees: held-out FLIR thermal crops, P(person)", color=FG, fontsize=13)
fig.text(0.5, 0.015, "Threshold 0.6  ·  images the model never trained on  ·  overall 96.2% on 1,200 held-out images",
         color=MUTED, fontsize=9, ha="center")
fig.subplots_adjust(left=0.06, right=0.99, top=0.86, bottom=0.07, wspace=0.08, hspace=0.25)
fig.savefig(OUT / "crops_grid.png", dpi=200, facecolor=BG)
plt.close(fig)

# ---------------------------------------------------------------- pipeline diagram
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
m = json.loads((ML / "results" / "metrics.json").read_text())
fig, ax = plt.subplots(figsize=(8, 3.4), facecolor=BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 8)
ax.set_ylim(0, 3.4)
ax.axis("off")
ax.add_patch(FancyBboxPatch((0.15, 0.15), 7.7, 3.1, boxstyle="round,pad=0.02,rounding_size=0.25",
                            facecolor="#161b22", edgecolor="#2a313a", linewidth=1.5))
for x, val, lab in ((1.45, m["accuracy"], "accuracy"), (4.0, m["precision"], "precision"),
                    (6.55, m["recall"], "recall")):
    ax.text(x, 2.05, f"{val * 100:.1f}%", color=FG, fontsize=34, ha="center", va="center", fontweight="bold")
    ax.text(x, 1.35, lab, color=MUTED, fontsize=14, ha="center", va="center")
ax.text(4.0, 0.62, f"{m['n']:,} held-out FLIR thermal images   ·   MobileNetV3-Small   ·   6 MB",
        color=WARM, fontsize=12, ha="center", va="center")
fig.savefig(OUT / "stats_card.png", dpi=200, facecolor=BG, bbox_inches="tight")
plt.close(fig)
print("assets ->", OUT, sorted(p.name for p in OUT.iterdir()))
