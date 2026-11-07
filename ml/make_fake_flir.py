"""Tiny synthetic FLIR-shaped dataset for smoke-testing prep -> train -> eval.

  py ml/make_fake_flir.py --out <scratch>/fake_flir

Persons = tall warm ellipses, cars = wide warm rectangles, on noisy background.
"""
import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def make_split(root, n_images, rng):
    (root / "data").mkdir(parents=True, exist_ok=True)
    W, H = 320, 256
    images, anns, aid = [], [], 1
    for i in range(n_images):
        img = Image.effect_noise((W, H), 25).point(lambda v: int(v * 0.5 + 40))
        d = ImageDraw.Draw(img)
        for _ in range(rng.randint(1, 3)):
            ph = rng.randint(30, 70)
            pw = ph // 3
            x, y = rng.randint(0, W - pw - 1), rng.randint(0, H - ph - 1)
            d.ellipse([x, y, x + pw, y + ph], fill=rng.randint(190, 240))
            d.ellipse([x + pw // 4, y - pw // 2, x + 3 * pw // 4, y], fill=rng.randint(200, 250))
            anns.append({"id": aid, "image_id": i, "category_id": 1, "bbox": [x, y - pw // 2, pw, ph + pw // 2]})
            aid += 1
        for _ in range(rng.randint(0, 2)):
            cw, ch = rng.randint(40, 80), rng.randint(22, 35)
            x, y = rng.randint(0, W - cw - 1), rng.randint(0, H - ch - 1)
            d.rectangle([x, y, x + cw, y + ch], fill=rng.randint(150, 220))
            anns.append({"id": aid, "image_id": i, "category_id": 3, "bbox": [x, y, cw, ch]})
            aid += 1
        name = f"data/frame-{i:05d}.jpg"
        img.filter(ImageFilter.GaussianBlur(1)).save(root / name)
        images.append({"id": i, "file_name": name, "width": W, "height": H})
    coco = {"images": images, "annotations": anns,
            "categories": [{"id": 1, "name": "person"}, {"id": 3, "name": "car"}]}
    (root / "coco.json").write_text(json.dumps(coco))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=120)
    args = ap.parse_args()
    rng = random.Random(0)
    out = Path(args.out)
    make_split(out / "images_thermal_train", args.n, rng)
    make_split(out / "images_thermal_val", args.n // 3, rng)
    print(f"fake FLIR -> {out}")


if __name__ == "__main__":
    main()
