"""Curated real thermal crops for the sim's survivors and decoys and the AI Lab examples.

The old picks were street scenes (people crossing a road, whole cars). These follow strict
rules so they read as a collapsed-building search:

  person   exactly one person in the crop, tight to the body, no vehicle / bike / stroller in
           frame, a squat box (height <= 1.8 x width: sitting, crouching, bent, partly hidden,
           not a walker), at least 56 px on its long side
  decoy    a warm object filling the frame: the hottest window inside a large vehicle box
           (engine bay, exhaust, wheel), never a whole car on a street, no person in frame

Only held-out frames are used. FLIR ADAS v2 (images_thermal_val, video_thermal_test) is street
footage, so almost no FLIR person passes the person rules; the people come from the SDT real
indoor set instead (FLIR Lepton 3.5 frames of people lying / sitting, key prefix "sdt/"), taken
only from the 20% that prep_sdt.py holds out of training. Decoys and not-person examples are
FLIR. Two steps:

    py ml/real_crops.py cands     # cut every candidate, score it, write contact sheets
    py ml/real_crops.py build     # cut the picks listed in ml/real_crops.json

`cands` writes ml/data/real_cands/ (not committed) plus numbered sheets for checking by eye.
The picks, with poses chosen by eye, live in ml/real_crops.json (committed), so `build` and
everything downstream (gradcam.py, make_ai_lab.py, make_slide_assets.py) is reproducible.
`build` writes the 6 runtime crops to ml/crops/runtime/ at RUNTIME_PX.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
sys.path.insert(0, str(ML_DIR))

FLIR = ML_DIR / "data" / "flir"
SPLITS = ("images_thermal_val", "video_thermal_test")
CANDS = ML_DIR / "data" / "real_cands"
SELECTION = ML_DIR / "real_crops.json"
RUNTIME = ML_DIR / "crops" / "runtime"
RUNTIME_PX = 192            # the model resizes to 96; the screen shows this same image
CAPTION = "Real FLIR thermal frame, same input as the AI"

NOT_ALONE = {"car", "bus", "truck", "motor", "bike", "other vehicle", "stroller", "skateboard"}
WARM_SOURCES = {"car", "truck", "bus", "motor", "other vehicle"}
MIN_LONG = 56
MIN_SHORT = 28
MAX_ASPECT = 1.8
TIGHT = 1.08                # square side = long box side x this
WARM_MIN = 110              # vehicle box short side for a frame-filling warm window
WARM_FRAC = 0.55            # window side = this x the box's short side


def key_of(split, file_name, box):
    return f"{split}/{file_name}#{','.join(str(int(round(v))) for v in box)}"


def parse_key(key):
    path, box = key.split("#")
    split, file_name = path.split("/", 1)
    return split, file_name, [int(v) for v in box.split(",")]


def crop(key, px):
    """Square crop [x0, y0, x1, y1] from the original frame, resized to px.

    Keys are "<split>/<file>#x0,y0,x1,y1". FLIR splits are 8-bit frames; split "sdt" is the
    SDT real test set (16-bit centi-Kelvin), mapped to 8 bits exactly as prep_sdt.py does."""
    split, file_name, sq = parse_key(key)
    if split == "sdt":
        import prep_sdt
        c = (np.asarray(Image.open(prep_sdt.SDT / file_name), dtype=np.float64) - 27315) / 100
        return prep_sdt.to8(c[sq[1]:sq[3], sq[0]:sq[2]]).resize((px, px), Image.BICUBIC)
    img = Image.open(FLIR / split / file_name).convert("L")
    return img.crop(tuple(sq)).resize((px, px), Image.BICUBIC)


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def xyxy(bbox):
    x, y, w, h = bbox
    return [x, y, x + w, y + h]


def candidates():
    import common
    model, ckpt = common.load_checkpoint(ML_DIR / "models" / "detector.pt", "cpu")
    tf = common.eval_transform()
    out = []
    for split in SPLITS:
        coco = json.loads((FLIR / split / "coco.json").read_text())
        cat = {c["id"]: c["name"] for c in coco["categories"]}
        imgs = {i["id"]: i for i in coco["images"]}
        per = {}
        for a in coco["annotations"]:
            per.setdefault(a["image_id"], []).append(a)
        for iid, anns in per.items():
            im = imgs[iid]
            W, H = im["width"], im["height"]
            people = [xyxy(a["bbox"]) for a in anns if cat[a["category_id"]] == "person"]
            busy = [xyxy(a["bbox"]) for a in anns if cat[a["category_id"]] in NOT_ALONE]
            frame = None
            for a in anns:
                name = cat[a["category_id"]]
                x, y, w, h = a["bbox"]
                sq = None
                if name == "person" and max(w, h) >= MIN_LONG and min(w, h) >= MIN_SHORT and h <= MAX_ASPECT * w:
                    side = max(w, h) * TIGHT
                    cx, cy = x + w / 2, y + h / 2
                    sq = [cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2]
                    me = xyxy(a["bbox"])
                    if (sq[0] < 0 or sq[1] < 0 or sq[2] > W or sq[3] > H
                            or any(overlaps(sq, p) for p in people if p != me)
                            or any(overlaps(sq, b) for b in busy)):
                        continue
                    kind = "person"
                elif name in WARM_SOURCES and min(w, h) >= WARM_MIN:
                    if frame is None:
                        frame = np.asarray(Image.open(FLIR / split / im["file_name"]).convert("L"), dtype=float)
                    side = int(min(w, h) * WARM_FRAC)
                    best, bv = None, -1.0
                    step = max(4, side // 4)
                    for wy in range(int(y), int(y + h - side) + 1, step):
                        for wx in range(int(x), int(x + w - side) + 1, step):
                            v = frame[wy:wy + side, wx:wx + side].mean()
                            if v > bv:
                                best, bv = [wx, wy, wx + side, wy + side], v
                    if best is None or any(overlaps(best, p) for p in people):
                        continue
                    sq, kind = best, name
                else:
                    continue
                key = key_of(split, im["file_name"], sq)
                img = crop(key, RUNTIME_PX)
                conf = float(common.predict_pos_prob(model, tf(img).unsqueeze(0))[0])
                out.append({"key": key, "kind": kind, "aspect": round(h / w, 2), "long_px": int(max(w, h)),
                            "conf": round(conf, 3)})
    return out


def sheets(cands, prefix, per_sheet=60, cols=10, px=128):
    pages = []
    for start in range(0, len(cands), per_sheet):
        chunk = cands[start:start + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        g = Image.new("L", (cols * px, rows * (px + 14)), 255)
        d = ImageDraw.Draw(g)
        for k, c in enumerate(chunk):
            x, y = (k % cols) * px, (k // cols) * (px + 14)
            g.paste(crop(c["key"], px), (x, y))
            d.text((x + 2, y + px), f"{start + k} {c['conf']:.2f} {c['kind'][:5]}", fill=0)
        path = CANDS / f"{prefix}_{start // per_sheet:02d}.png"
        g.save(path)
        pages.append(path)
    return pages


def build():
    sel = json.loads(SELECTION.read_text())
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for role, prefix in (("survivors", "pos"), ("decoys", "neg")):
        for k, e in enumerate(sel[role], 1):
            crop(e["key"], RUNTIME_PX).save(RUNTIME / f"{prefix}_{k:04d}.png", optimize=True)
    print(f"wrote {len(sel['survivors'])} survivor and {len(sel['decoys'])} decoy crops to {RUNTIME}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["cands", "build"])
    args = ap.parse_args()
    if args.step == "build":
        build()
        return
    CANDS.mkdir(parents=True, exist_ok=True)
    cands = candidates()
    people = sorted([c for c in cands if c["kind"] == "person"], key=lambda c: (c["aspect"], -c["long_px"]))
    warm = sorted([c for c in cands if c["kind"] != "person"], key=lambda c: c["conf"])
    (CANDS / "cands.json").write_text(json.dumps({"people": people, "warm": warm}, indent=1))
    pp, wp = sheets(people, "people"), sheets(warm, "warm")
    print(f"{len(people)} person candidates ({len(pp)} sheets), {len(warm)} warm-object candidates ({len(wp)} sheets) in {CANDS}")


if __name__ == "__main__":
    main()
