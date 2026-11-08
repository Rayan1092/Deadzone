"""AI Lab export for the key-L overlay (Yusuf), in the format he asked for in yusuf.md.

    py ml/make_ai_lab.py --crops ml/data/crops/val

Writes ml/results/lab.json and ml/results/lab/{pos,neg}_NN.png (12 + 12 held-out crops, 192 px).
Aziz serves ml/results/ at /ai-lab/results/ (DZ_AI_LAB=1), so `file` paths in lab.json are
relative to /ai-lab/results/. Runtime crops and their Grad-CAM heatmaps are already served at
/crops/ (no gate), so those paths start with /crops/.

  model     name, input size, parameters, measured onboard CPU time per crop
  metrics   from ml/results/metrics.json (held-out FLIR val, written by eval.py)
  confusion [[tp, fn], [fp, tn]] with labels ["person", "not person"]
  curve     per-epoch train/val loss and accuracy from ml/results/train_history.json (logged
            retrain); empty with a note until that file exists
  examples  12 person + 12 not-person held-out crops, scored by the shipped model
  runtime   the 6 crops the sim's survivors and decoys use, with Grad-CAM (ml/gradcam.py)
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import torch
from PIL import Image

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))
import common  # noqa: E402

RESULTS = ML_DIR / "results"
RUNTIME = ML_DIR / "crops" / "runtime"
N_EACH = 12
OUT_PX = 192
MIN_SIDE = 40          # skip tiny source boxes: a 96 px crop of a 12 px person shows nothing


def onboard_ms(model, x, runs=50):
    torch.set_num_threads(1)               # the robot runs perception on one core
    with torch.no_grad():
        for _ in range(5):
            model(x)
        t0 = time.perf_counter()
        for _ in range(runs):
            model(x)
    return round((time.perf_counter() - t0) / runs * 1000, 1)


def pick(crops, cls, rng):
    """Seeded pick of held-out crops of one class with a readable source box."""
    folder = Path(crops) / cls
    files = sorted(folder.glob("*.png"))
    mf = Path(crops) / "manifest.json"
    if mf.is_file():
        meta = {f"{m['i']:05d}.png": m for m in json.loads(mf.read_text())[cls]}
        # negatives: object-centered only (cars etc.). Random background crops can hold
        # people nobody labeled, which would show a "not a person" that is a person.
        files = [f for f in files if f.name in meta and
                 meta[f.name]["box"][2] - meta[f.name]["box"][0] >= MIN_SIDE and
                 (cls == "pos" or meta[f.name].get("object"))] or files
    rng.shuffle(files)
    return files[:N_EACH]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", default=str(ML_DIR / "data" / "crops" / "val"))
    ap.add_argument("--model", default=str(ML_DIR / "models" / "detector.pt"))
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()

    model, ckpt = common.load_checkpoint(args.model, "cpu")
    thr = float(ckpt.get("threshold", common.THRESHOLD))
    tf = common.eval_transform()
    m = json.loads((RESULTS / "metrics.json").read_text())
    c = m["confusion"]

    out = RESULTS / "lab"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    rng = random.Random(args.seed)
    examples = []
    for cls, prefix, label in (("pos", "pos", "person"), ("neg", "neg", "not person")):
        for k, f in enumerate(pick(args.crops, cls, rng), 1):
            img = Image.open(f)
            conf = round(float(common.predict_pos_prob(model, tf(img).unsqueeze(0))[0]), 3)
            name = f"{prefix}_{k:02d}.png"
            img.convert("L").resize((OUT_PX, OUT_PX), Image.BICUBIC).save(out / name)
            examples.append({"file": f"lab/{name}", "label": label,
                             "predicted": "person" if conf >= thr else "not person", "conf": conf})

    hist_path = RESULTS / "train_history.json"
    hist = json.loads(hist_path.read_text()) if hist_path.is_file() else None
    curve = [{k: e[k] for k in ("epoch", "train_loss", "val_loss", "train_acc", "val_acc")}
             for e in (hist or {}).get("curve", [])]
    if hist is None:
        curve_note = "Training curve pending: logged retrain not run yet."
    elif hist.get("promoted"):
        curve_note = "Curve of the shipped model (logged retrain, promoted because it scored equal or better)."
    else:
        curve_note = ("Curve from a logged retrain with the same recipe and data; the shipped model "
                      "was kept because the retrain did not score better on the held-out test set.")

    runtime = []
    rm = RUNTIME / "manifest.json"
    if rm.is_file():
        for e in json.loads(rm.read_text())["crops"]:
            runtime.append({"id": e["id"], "role": e["role"], "object": e["object"], "label": e["label"],
                            "predicted": e["predicted"], "conf": e["conf"], "file": f"/crops/{e['file']}",
                            "heatmap": f"/crops/{e['heatmap']}", "heatmap_alpha": f"/crops/{e['heatmap_alpha']}"})

    lab = {
        "model": {"name": "MobileNetV3-Small", "input_px": common.IMG_SIZE,
                  "params": sum(p.numel() for p in model.parameters()),
                  "onboard_ms": onboard_ms(model, tf(Image.open(RUNTIME / "pos_0001.png")).unsqueeze(0)),
                  "size_mb": round(Path(args.model).stat().st_size / 1e6, 1), "threshold": thr,
                  "trained_on": "FLIR ADAS v2 thermal, person vs not-person 96 px crops"},
        "metrics": {"accuracy": round(m["accuracy"], 4), "precision": round(m["precision"], 4),
                    "recall": round(m["recall"], 4), "f1": round(m["f1"], 4), "n_test": m["n"]},
        "confusion": {"labels": ["person", "not person"],
                      "matrix": [[c["tp"], c["fn"]], [c["fp"], c["tn"]]]},
        "curve": curve,
        "curve_note": curve_note,
        "examples": examples,
        "runtime": runtime,
        "assets": {"confusion_png": "confusion_matrix.png",
                   "slides": ["/ai-lab/slides/pipeline.png", "/ai-lab/slides/crops_grid.png",
                              "/ai-lab/slides/stats_card.png"]},
        "paths": "file paths are relative to /ai-lab/results/ (DZ_AI_LAB=1); runtime paths start with /crops/",
        "note": "Examples and metrics are held-out FLIR val images, never used in training.",
    }
    (RESULTS / "lab.json").write_text(json.dumps(lab, indent=1), encoding="utf-8")
    right = sum(e["label"] == e["predicted"] for e in examples)
    print(f"wrote {RESULTS / 'lab.json'}: {len(examples)} examples ({right} right), "
          f"{len(curve)} curve points, {len(runtime)} runtime crops, onboard {lab['model']['onboard_ms']} ms")


if __name__ == "__main__":
    main()
