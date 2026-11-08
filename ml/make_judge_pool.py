"""Judge test pool for the key-J overlay: can a judge beat the model on real thermal images?

    py ml/make_judge_pool.py

Writes ml/results/judge_pool/{pos,neg}_NN.png (20 person + 20 not-person, 288 px) and
ml/results/judge_pool/manifest.json. Aziz serves ml/results/ read-only at /ai-lab/results/
(DZ_AI_LAB=1), so the overlay loads /ai-lab/results/judge_pool/manifest.json and the files
next to it.

Rules for the pool:
  - only held-out FLIR val crops (the model never trained on them)
  - none of the AI Lab examples and none of the sim's runtime crops (both listed with their
    source frames in ml/real_crops.json); no crop from any frame those came from either
  - not-person crops are object-centered only (cars, signs, ...): random background crops can
    hold people nobody labeled
  - source box at least 40 px, so a person is recognisable at all
  - the model is the shipped one (ml/models/detector.pt), scoring the exact 96 px crop it was
    evaluated on; the image shown is a larger re-crop of the same box from the original frame
  - a few crops the model gets wrong are included on purpose (N_WRONG per class), so the pool
    is harder for the model than the full held-out set; the manifest says so
"""
import argparse
import json
import random
import sys
from pathlib import Path

from PIL import Image

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
sys.path.insert(0, str(ML_DIR))
import common  # noqa: E402
import real_crops  # noqa: E402

OUT_PX = 288
N_EACH = 20
N_WRONG = 2            # model mistakes per class kept in the pool
MIN_SIDE = 40
PAD = 0.15             # same square padding as prep_crops.py
CAPTION = "Real thermal camera image, Teledyne FLIR dataset"   # the wording asked for the judge test


def used_elsewhere(crops, meta):
    """(crop names, source frames) already used by the runtime crops or the AI Lab examples.
    Both come from ml/real_crops.json (real_crops.py), which names every source frame."""
    sel = json.loads(real_crops.SELECTION.read_text())
    used = {Path(real_crops.parse_key(e["key"])[1]).name
            for group in ("survivors", "decoys", "lab_pos", "lab_neg") for e in sel[group]}
    names, frames = set(), set()
    for cls in ("pos", "neg"):
        for name, m in meta[cls].items():
            if Path(m["src"].replace("\\", "/")).name in used:
                names.add((cls, name))
                frames.add(m["src"])
    return names, frames, len(used)


def poses():
    """Pose of each person image, set by eye after looking at the pool (ml/judge_pool_poses.json)."""
    p = ML_DIR / "judge_pool_poses.json"
    return json.loads(p.read_text()) if p.is_file() else {}


MIN_FRAME_GAP = 150   # crops from one video must be this many frames apart (no near-duplicates)


def video_frame(src):
    """FLIR frames are named video-<id>-frame-<n>-...; neighbouring frames look alike."""
    vid, rest = Path(src.replace("\\", "/")).name.split("-frame-")
    return vid, int(rest.split("-")[0])


def too_close(src, used):
    vid, n = video_frame(src)
    return any(abs(n - f) < MIN_FRAME_GAP for f in used.get(vid, ()))


def big_crop(src, box):
    """Square crop of the source box with the training padding, from the original frame."""
    img = Image.open(ROOT / src.replace("\\", "/")).convert("L")
    x0, y0, x1, y1 = box
    side = max(x1 - x0, y1 - y0) * (1 + 2 * PAD)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    l, t = max(0, cx - side / 2), max(0, cy - side / 2)
    r, b = min(img.width, l + side), min(img.height, t + side)
    return img.crop((int(l), int(t), int(r), int(b))).resize((OUT_PX, OUT_PX), Image.BICUBIC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", default=str(ML_DIR / "data" / "crops" / "val"))
    ap.add_argument("--model", default=str(ML_DIR / "models" / "detector.pt"))
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    raw = json.loads((Path(args.crops) / "manifest.json").read_text())
    meta = {cls: {f"{m['i']:05d}.png": m for m in raw[cls]} for cls in ("pos", "neg")}
    skip_names, skip_frames, n_used = used_elsewhere(args.crops, meta)
    pose_of = poses()

    model, ckpt = common.load_checkpoint(args.model, "cpu")
    thr = float(ckpt.get("threshold", common.THRESHOLD))
    tf = common.eval_transform()

    out = ML_DIR / "results" / "judge_pool"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    rng = random.Random(args.seed)
    items, used_frames = [], {}
    for cls, truth in (("pos", "person"), ("neg", "not person")):
        cands = []
        for name, m in sorted(meta[cls].items()):
            w = min(m["box"][2] - m["box"][0], m["box"][3] - m["box"][1])
            if ((cls, name) in skip_names or m["src"] in skip_frames or w < MIN_SIDE
                    or (cls == "neg" and not m.get("object"))):
                continue
            cands.append(name)
        rng.shuffle(cands)
        right, wrong = [], []
        for name in cands:
            m = meta[cls][name]
            if too_close(m["src"], used_frames):   # no near-duplicate frames from one video
                continue
            conf = float(common.predict_pos_prob(model, tf(Image.open(Path(args.crops) / cls / name)).unsqueeze(0))[0])
            ok = (conf >= thr) == (cls == "pos")
            bucket = right if ok else wrong
            if (ok and len(right) < N_EACH - N_WRONG) or (not ok and len(wrong) < N_WRONG):
                bucket.append((name, conf))
                vid, n = video_frame(m["src"])
                used_frames.setdefault(vid, []).append(n)
            if len(right) == N_EACH - N_WRONG and len(wrong) == N_WRONG:
                break
        chosen = right + wrong
        rng.shuffle(chosen)
        for k, (name, conf) in enumerate(chosen, 1):
            m = meta[cls][name]
            fname = f"{cls}_{k:02d}.png"
            big_crop(m["src"], m["box"]).save(out / fname, optimize=True)
            verdict = "person" if conf >= thr else "not person"
            items.append({"file": fname, "truth": truth, "verdict": verdict, "confidence": round(conf, 3),
                          "pose": pose_of.get(fname) if cls == "pos" else None, "caption": CAPTION,
                          # same values under the names Aziz's J overlay reads (web/src/panels/judgePool.js)
                          "label": truth, "predicted": verdict, "conf": round(conf, 3)})

    right = sum(i["truth"] == i["verdict"] for i in items)
    manifest = {
        "caption": CAPTION,
        "held_out": True,
        "split": "val",
        "source": "Teledyne FLIR ADAS v2 thermal dataset, validation split (held out: never used in training)",
        "model": {"name": "MobileNetV3-Small", "file": "ml/models/detector.pt (the shipped model)", "threshold": thr},
        "threshold": thr,
        "truth_source": "FLIR's human annotations (person boxes; not-person crops are centred on labelled objects such as cars and signs)",
        "confidence": "model probability that the image shows a person (0 to 1); verdict is person at or above the threshold",
        "pose": "person images only, set by eye: standing, walking, sitting, crouching, bent, lying, partly hidden; null for not-person",
        "model_right": right,
        "n": len(items),
        "note": (f"{N_WRONG} person and {N_WRONG} not-person images the model gets wrong are included on purpose, "
                 f"so the model scores {right} of {len(items)} here; on all 1,200 held-out images it scores 96.2%. "
                 "None of these images are in the AI Lab examples or the simulation's crops, or from their frames."),
        "paths": "file is relative to this manifest: /ai-lab/results/judge_pool/<file> (DZ_AI_LAB=1)",
        "items": items,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"wrote {out}: {len(items)} images, model right on {right}, {sum(i['pose'] is None for i in items if i['truth'] == 'person')} "
          f"person images without a pose; excluded {len(skip_names)} crops from {n_used} frames used by the runtime and AI Lab")


if __name__ == "__main__":
    main()
