"""Cut 96x96 thermal crops from FLIR v2 COCO labels.

  py ml/prep_crops.py --flir ml/data/flir --out ml/data/crops --n 3000

Positives: person boxes (>= --min-h px tall), squared with a margin.
Negatives: same-size squares that do not overlap any person box. Half are random
background, half are centered on non-person objects (cars, etc.: hot but not human).
FLIR train -> crops/train, FLIR val -> crops/val (held-out test split).
Also writes 3 positive + 3 negative held-out val crops to ml/crops/runtime/ for the sim.
"""
import argparse
import json
import random
from pathlib import Path

from PIL import Image

ML_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = ML_DIR / "crops" / "runtime"
SIZE = 96
MARGIN = 0.15


def iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    iw = max(0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    if inter == 0:
        return 0.0
    return inter / ((ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter)


def square_around(cx, cy, side, w, h):
    side = int(min(side, w, h))
    x0 = int(round(cx - side / 2))
    y0 = int(round(cy - side / 2))
    x0 = max(0, min(x0, w - side))
    y0 = max(0, min(y0, h - side))
    return (x0, y0, x0 + side, y0 + side)


def box_square(bbox, w, h):
    x, y, bw, bh = bbox
    side = max(bw, bh) * (1 + 2 * MARGIN)
    return square_around(x + bw / 2, y + bh / 2, side, w, h)


def load_split(split_dir):
    coco = json.loads((split_dir / "coco.json").read_text())
    person_ids = {c["id"] for c in coco["categories"] if c["name"] == "person"}
    if not person_ids:
        raise SystemExit(f"no 'person' category in {split_dir}/coco.json")
    images = {im["id"]: im for im in coco["images"]}
    per_img = {}
    for a in coco["annotations"]:
        per_img.setdefault(a["image_id"], []).append(a)
    return images, per_img, person_ids


def collect(split_dir, n, min_h, rng):
    """Return (pos_jobs, neg_jobs); each job = (image_path, crop_box)."""
    images, per_img, person_ids = load_split(split_dir)
    pos, neg_obj, sides = [], [], []
    person_boxes = {}
    for iid, anns in per_img.items():
        im = images[iid]
        w, h = im["width"], im["height"]
        pb = [box_square(a["bbox"], w, h) for a in anns if a["category_id"] in person_ids]
        person_boxes[iid] = pb
        for a in anns:
            sq = box_square(a["bbox"], w, h)
            if a["category_id"] in person_ids:
                if a["bbox"][3] >= min_h:
                    pos.append((iid, sq))
                    sides.append(sq[2] - sq[0])
            elif a["bbox"][3] >= min_h and all(iou(sq, p) < 0.05 for p in pb):
                neg_obj.append((iid, sq))
    rng.shuffle(pos)
    pos = pos[:n]
    rng.shuffle(neg_obj)
    neg = neg_obj[: n // 2]

    # random background squares with the positive size distribution
    img_ids = sorted(images)
    tries = 0
    while len(neg) < n and tries < n * 50 and sides:
        tries += 1
        iid = rng.choice(img_ids)
        im = images[iid]
        w, h = im["width"], im["height"]
        side = rng.choice(sides)
        if side >= min(w, h):
            continue
        cx = rng.uniform(side / 2, w - side / 2)
        cy = rng.uniform(side / 2, h - side / 2)
        sq = square_around(cx, cy, side, w, h)
        if all(iou(sq, p) < 0.05 for p in person_boxes.get(iid, [])):
            neg.append((iid, sq))

    def to_path(jobs):
        return [(split_dir / images[iid]["file_name"], sq) for iid, sq in jobs]
    return to_path(pos), to_path(neg)


def write_crops(jobs, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    by_img = {}
    for i, (p, sq) in enumerate(jobs):
        by_img.setdefault(p, []).append((i, sq))
    written = []
    for p, items in by_img.items():
        try:
            img = Image.open(p).convert("L")
        except (OSError, FileNotFoundError):
            continue
        for i, sq in items:
            dst = out_dir / f"{i:05d}.png"
            img.crop(sq).resize((SIZE, SIZE), Image.BILINEAR).save(dst)
            written.append(dst)
    return sorted(written)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flir", default=str(ML_DIR / "data" / "flir"))
    ap.add_argument("--out", default=str(ML_DIR / "data" / "crops"))
    ap.add_argument("--n", type=int, default=3000, help="crops per class for train")
    ap.add_argument("--n-val", type=int, default=600, help="crops per class for val")
    ap.add_argument("--min-h", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--runtime-out", default=str(RUNTIME_DIR))
    args = ap.parse_args()

    flir, out = Path(args.flir), Path(args.out)
    rng = random.Random(args.seed)
    for split, src, n in (("train", "images_thermal_train", args.n), ("val", "images_thermal_val", args.n_val)):
        pos, neg = collect(flir / src, n, args.min_h, rng)
        wp = write_crops(pos, out / split / "pos")
        wn = write_crops(neg, out / split / "neg")
        print(f"{split}: {len(wp)} pos, {len(wn)} neg")

    # runtime crops: held-out val crops that the sim floor plan points at
    rt = Path(args.runtime_out)
    rt.mkdir(parents=True, exist_ok=True)
    rrng = random.Random(args.seed + 1)
    for cls in ("pos", "neg"):
        files = sorted((out / "val" / cls).glob("*.png"))
        rrng.shuffle(files)
        # prefer bigger-object-looking crops: just take the first 3 after shuffle
        for k, f in enumerate(files[:3], start=1):
            Image.open(f).save(rt / f"{cls}_{k:04d}.png")
    print(f"runtime crops -> {rt}")


if __name__ == "__main__":
    main()
