"""Decoy crop pool: real thermal images for each heat-source type (docs/PLAN.md "Thermal hot spots"),
scored with the shipped detector. Writes ml/crops/decoys/<type>_NN.png (192 px, like the runtime
crops) + manifest.json, ml/results/decoy_eval.json (false-alarm rate per type), one example per type
in ml/results/lab/decoys/ and a `decoys` block in ml/results/lab.json for the Model Lab (key L).

Only frames the detector never trained on: FLIR ADAS v2 `images_thermal_val` and
`video_thermal_test`. FLIR labels street objects, so only two types have real counterparts:
`dog` (labelled dogs) and `sunlit` (sun-warmed pavement and walls, unlabelled bright patches).
The other five are stand-ins taken from the warmest examples of the closest labelled class and say
so in their caption, like the runtime decoys D1-D3 ("stand-in for a radiator").

    py ml/make_decoy_pool.py            # needs ml/data/flir and the trained model
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))
import prep_crops  # noqa: E402

FLIR = ML_DIR / "data" / "flir"
SPLITS = ["images_thermal_val", "video_thermal_test"]
OUT = ML_DIR / "crops" / "decoys"
RESULTS = ML_DIR / "results"
SIZE = 192
PER_TYPE = 12

# type -> (FLIR classes, min box side px, real?, caption)
TYPES = {
    "dog": (["dog"], 12, True, "dog, real FLIR thermal frame"),
    "sunlit": ([], 0, True, "sun-warmed pavement or wall, real FLIR thermal frame (no label: a bright patch away from every labelled object)"),
    "generator": (["truck", "other vehicle"], 60, False, "running truck engine and machinery (stand-in for a generator)"),
    "space_heater": (["car"], 70, False, "warm car front (stand-in for a space heater)"),
    "hot_pipe": (["light"], 28, False, "lamp post or light housing (stand-in for a hot pipe)"),
    "server_rack": (["bus"], 70, False, "boxy warm bus panel (stand-in for a server rack)"),
    "laptop": (["sign"], 28, False, "small warm panel (stand-in for a laptop)"),
}


def used_frames():
    """Frames already used by the runtime crops, the unsure pairs and the held-out test set."""
    text = ""
    for f in [ML_DIR / "crops" / "runtime" / "manifest.json", ML_DIR / "crops" / "runtime" / "unsure_sources.json",
              RESULTS / "judge_pool" / "manifest.json"]:
        if f.exists():
            text += f.read_text(encoding="utf-8")
    return text


def video_of(name):
    return name.split("-frame-")[0]


def load(split):
    coco = json.loads((FLIR / split / "coco.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c["name"] for c in coco["categories"]}
    images = {im["id"]: im for im in coco["images"]}
    per_img = {}
    for a in coco["annotations"]:
        per_img.setdefault(a["image_id"], []).append(a)
    return cats, images, per_img


def gray(split, im):
    return np.asarray(Image.open(FLIR / split / im["file_name"]).convert("L"), dtype=np.float32)


def collect():
    skip = used_frames()
    found = {t: [] for t in TYPES}
    for split in SPLITS:
        cats, images, per_img = load(split)
        for iid, im in sorted(images.items()):
            name = Path(im["file_name"]).name
            if name in skip:
                continue
            anns = per_img.get(iid, [])
            people = [a["bbox"] for a in anns if cats[a["category_id"]] == "person"]
            arr = None
            for kind, (classes, min_side, _, _) in TYPES.items():
                if kind == "sunlit":
                    continue
                for a in anns:
                    if cats[a["category_id"]] not in classes or max(a["bbox"][2:]) < min_side:
                        continue
                    if arr is None:
                        arr = gray(split, im)
                    sq = prep_crops.box_square(a["bbox"], im["width"], im["height"])
                    if any(prep_crops.iou(sq, (px, py, px + pw, py + ph)) > 0 for px, py, pw, ph in people):
                        continue                  # a labelled person in the crop: not a decoy
                    x, y, w, h = map(int, a["bbox"])
                    inner = arr[y:y + max(h, 1), x:x + max(w, 1)]
                    found[kind].append((float(inner.mean()), split, name, sq))
            # sunlit: a bright, even patch overlapping no labelled object, in a bright (daytime) frame
            if arr is None:
                arr = gray(split, im)
            if arr.mean() < 130:
                continue
            boxes = [(a["bbox"][0] - 8, a["bbox"][1] - 8, a["bbox"][0] + a["bbox"][2] + 8, a["bbox"][1] + a["bbox"][3] + 8) for a in anns]
            side, best = 120, None
            for y0 in range(0, im["height"] - side, 60):
                for x0 in range(0, im["width"] - side, 60):
                    sq = (x0, y0, x0 + side, y0 + side)
                    if any(prep_crops.iou(sq, b) > 0 for b in boxes):
                        continue
                    patch = arr[y0:y0 + side, x0:x0 + side]
                    if patch.std() > 30:
                        continue
                    key = float(patch.mean())
                    if best is None or key > best[0]:
                        best = (key, split, name, sq)
            if best:
                found["sunlit"].append(best)
    return found


def pick(cands):
    """The warmest, one per frame, spreading over videos first."""
    cands = sorted(cands, key=lambda c: (-c[0], c[2]))
    out, frames, videos = [], set(), {}
    for rnd in range(3):
        for c in cands:
            if len(out) == PER_TYPE:
                return out
            if c[2] in frames or videos.get(video_of(c[2]), 0) > rnd:
                continue
            out.append(c)
            frames.add(c[2])
            videos[video_of(c[2])] = videos.get(video_of(c[2]), 0) + 1
    return out


def main():
    sys.path.insert(0, str(ML_DIR.parent / "server"))
    from deadzone.robot.perception import DEFAULT_MODEL, Detector
    det = Detector(DEFAULT_MODEL, crop_dir=OUT)        # the robot's own detector, scoring files in OUT
    found = collect()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    crops, per_type = [], {}
    for kind, (classes, _, real, caption) in TYPES.items():
        chosen = pick(found[kind])
        alarms = 0
        scores = []
        for n, (warm, split, frame, sq) in enumerate(chosen, 1):
            name = f"{kind}_{n:02d}.png"
            img = Image.open(next((FLIR / split).rglob(frame))).convert("L").crop(sq).resize((SIZE, SIZE), Image.BILINEAR)
            img.save(OUT / name)
            p = det.score(name)
            scores.append(p)
            alarms += p >= det.threshold
            crops.append({"file": name, "type": kind, "real": real, "shows": caption, "split": split, "frame": frame,
                          "box_xyxy": list(sq), "p_person": p,
                          "verdict": "person" if p >= det.threshold else "not a person"})
        per_type[kind] = {"n": len(chosen), "false_alarms": int(alarms), "false_alarm_rate": round(alarms / max(1, len(chosen)), 3),
                          "max_p_person": max(scores) if scores else None, "mean_p_person": round(float(np.mean(scores)), 3) if scores else None,
                          "real": real, "classes": classes or ["unlabelled bright patch"], "caption": caption}
    n = sum(v["n"] for v in per_type.values())
    fa = sum(v["false_alarms"] for v in per_type.values())
    summary = {"threshold": det.threshold, "n": n, "false_alarms": fa, "false_alarm_rate": round(fa / max(1, n), 4),
               "per_type": per_type,
               "source": "Teledyne FLIR ADAS v2 thermal, images_thermal_val + video_thermal_test (never trained on); "
                         "frames used by the runtime crops, unsure pairs and the held-out test set excluded",
               "note": "dog and sunlit are real counterparts; the other five are stand-ins (warmest crops of the closest "
                       "labelled class), named as such in each caption"}
    (OUT / "manifest.json").write_text(json.dumps({**summary, "crops": crops}, indent=1), encoding="utf-8")
    (RESULTS / "decoy_eval.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    # Model Lab: one example per type (the most person-like one, the honest worst case)
    lab_dir = RESULTS / "lab" / "decoys"
    lab_dir.mkdir(parents=True, exist_ok=True)
    examples = []
    for kind in TYPES:
        mine = [c for c in crops if c["type"] == kind]
        if not mine:
            continue
        worst = max(mine, key=lambda c: c["p_person"])
        shutil.copy(OUT / worst["file"], lab_dir / worst["file"])
        examples.append({"file": f"lab/decoys/{worst['file']}", "type": kind, "real": worst["real"], "shows": worst["shows"],
                         "conf": worst["p_person"], "verdict": worst["verdict"],
                         "card": f"{worst['verdict'].capitalize()} · {round(100 * (1 - worst['p_person']))}% sure"})
    lab_path = RESULTS / "lab.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    lab["decoys"] = {**{k: summary[k] for k in ("threshold", "n", "false_alarms", "false_alarm_rate", "source", "note")},
                     "per_type": {k: {kk: v[kk] for kk in ("n", "false_alarms", "false_alarm_rate", "max_p_person", "real")}
                                  for k, v in per_type.items()},
                     "examples": examples}
    lab_path.write_text(json.dumps(lab, indent=1), encoding="utf-8")
    print(json.dumps({k: (v["n"], v["false_alarms"], v["max_p_person"]) for k, v in per_type.items()}))
    print(f"total {n} crops, {fa} false alarms ({100 * fa / max(1, n):.1f}%) at threshold {det.threshold}")


if __name__ == "__main__":
    main()
