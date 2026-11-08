"""Indoor thermal people from SDT (real split) for fine-tuning the survivor detector.

SDT, "Synthetic Depth & Thermal", Zenodo record 4124309 (CC BY 4.0; the record also says
non-commercial research use). Only its REAL test.zip is used: 8,000 FLIR Lepton 3.5 frames
(160x120 upscaled to 640x480, 16-bit centi-Kelvin) from an overhead indoor camera, one person
lying / sitting / standing, or an empty room, 2,000 frames each, with a person box per frame.
Download to ml/data/ext/sdt/test/ (no login needed); nothing from it is committed.

    py ml/prep_sdt.py

Writes (all under ml/data/, gitignored):
  sdt_crops/{train,test}/{pos,neg}/   SDT crops only; test = the last 20% of every 2,000-frame
                                      block, so neighbouring frames of one recording never
                                      straddle train and test
  crops_mix/train/{pos,neg}/          FLIR train crops (hard links) + SDT train crops, the
                                      training set for `train.py --crops ml/data/crops_mix`

Crops follow prep_crops.py: square box with a 15% margin, 96 px grayscale. Temperatures are
mapped to 8 bits per crop (1st to 99.5th percentile, at least an 8 C span), which is close to
the automatic gain of FLIR ADAS frames without turning flat empty rooms into texture.
Negatives: 2 random squares per empty-room frame plus 1 square per person frame that does not
touch the person, with sides drawn from the person crops' sizes.
"""
import os
import random
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

ML_DIR = Path(__file__).resolve().parent
SDT = ML_DIR / "data" / "ext" / "sdt" / "test"
OUT = ML_DIR / "data" / "sdt_crops"
MIX = ML_DIR / "data" / "crops_mix"
FLIR_TRAIN = ML_DIR / "data" / "crops" / "train"
SIZE = 96
PAD = 0.15
BLOCK = 2000
TEST_FRAC = 0.2
MIN_SPAN_C = 8.0


def to8(c):
    lo = np.percentile(c, 1)
    hi = max(np.percentile(c, 99.5), lo + MIN_SPAN_C)
    return Image.fromarray((np.clip((c - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8))


def square(box, W, H):
    x0, y0, x1, y1 = box
    side = max(x1 - x0, y1 - y0) * (1 + 2 * PAD)
    side = min(side, W, H)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    l = min(max(0, cx - side / 2), W - side)
    t = min(max(0, cy - side / 2), H - side)
    return [int(l), int(t), int(l + side), int(t + side)]


def touches(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def main():
    rng = random.Random(0)
    labels = [ln.strip().split(",") for ln in (SDT / "labels.txt").read_text().splitlines() if ln.strip()]
    for d in (OUT, MIX):
        if d.exists():
            shutil.rmtree(d)
    for split in ("train", "test"):
        for cls in ("pos", "neg"):
            (OUT / split / cls).mkdir(parents=True)
    sides = []
    counts = {}
    frames = []
    for i, row in enumerate(labels):
        pose, box = int(row[0]), [int(float(v)) for v in row[1:5]]
        split = "test" if (i % BLOCK) >= BLOCK * (1 - TEST_FRAC) else "train"
        frames.append((i, pose, box, split))
        if pose != 3:
            sides.append(square(box, 640, 480)[2] - square(box, 640, 480)[0])
    for i, pose, box, split in frames:
        c = (np.asarray(Image.open(SDT / f"image_t_{i}.png"), dtype=np.float64) - 27315) / 100
        H, W = c.shape
        out = []
        if pose != 3:
            sq = square(box, W, H)
            out.append(("pos", sq))
            negs = 1
        else:
            negs = 2
        for _ in range(negs):
            for _try in range(30):
                s = min(rng.choice(sides), W, H)
                l, t = rng.randint(0, W - s), rng.randint(0, H - s)
                cand = [l, t, l + s, t + s]
                if pose == 3 or not touches(cand, box):
                    out.append(("neg", cand))
                    break
        for cls, sq in out:
            img = to8(c[sq[1]:sq[3], sq[0]:sq[2]]).resize((SIZE, SIZE), Image.BILINEAR)
            n = counts.get((split, cls), 0)
            img.save(OUT / split / cls / f"sdt_{i:04d}_{n:05d}.png")
            counts[(split, cls)] = n + 1
    # training mix: FLIR train (hard links, no copies) + SDT train
    for cls in ("pos", "neg"):
        dst = MIX / "train" / cls
        dst.mkdir(parents=True)
        for f in (FLIR_TRAIN / cls).glob("*.png"):
            try:
                os.link(f, dst / f"flir_{f.name}")
            except OSError:
                shutil.copy2(f, dst / f"flir_{f.name}")
        for f in (OUT / "train" / cls).glob("*.png"):
            os.link(f, dst / f.name)
    mix = {cls: len(list((MIX / "train" / cls).glob("*.png"))) for cls in ("pos", "neg")}
    print("SDT crops:", {f"{s}/{c}": n for (s, c), n in sorted(counts.items())}, "| train mix:", mix)


if __name__ == "__main__":
    main()
