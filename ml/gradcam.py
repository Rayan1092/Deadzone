"""Grad-CAM "where the AI looked" heatmaps for every runtime crop, plus a crop manifest.

    py ml/gradcam.py

For each crop in ml/crops/runtime/ (the thermal images the sim's survivors and decoys use):
  heatmaps/<name>.png        the crop with the heatmap blended on top (ready for the AI card)
  heatmaps/<name>_alpha.png  the heatmap alone as RGBA, transparent where the model didn't look
                             (for overlays and 3D textures on top of the crop)
and ml/crops/runtime/manifest.json listing every crop. The server already serves this folder
at /crops, so the files are at /crops/heatmaps/<name>.png and /crops/manifest.json.

Grad-CAM (Selvaraju et al. 2017): weight each channel of a conv layer's activations by the mean
gradient of the "person" score, sum, ReLU, upsample. We use the person class for every crop,
so on a decoy the map shows what looked most person-like, even though the model said no.
Layer: features[8], the last block at 1/16 resolution (6 x 6 for a 96 px crop). The final
block is only 3 x 3, too coarse to show anything on a 96 px crop.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ML_DIR = Path(__file__).resolve().parent
REPO = ML_DIR.parent
sys.path.insert(0, str(ML_DIR))
import common  # noqa: E402

RUNTIME = ML_DIR / "crops" / "runtime"
FLOORPLAN = REPO / "data" / "floorplans" / "collapse_01.json"
LAYER = 8
OUT_PX = 192                     # 2x the crop: smoother for cards and textures
HEAT_RGB = (235, 104, 52)        # one warm hue; opacity carries the magnitude
MAX_ALPHA = 0.75


def gradcam(model, x, layer=LAYER, cls=1):
    """Grad-CAM map in [0, 1] at the layer's resolution, and P(class) for x (1 x 3 x H x W)."""
    acts, grads = {}, {}

    def keep(module, inp, out):
        acts["a"] = out
        out.register_hook(lambda g: grads.__setitem__("g", g))   # tensor hook: safe with inplace ops

    h = model.features[layer].register_forward_hook(keep)
    try:
        model.zero_grad(set_to_none=True)
        logits = model(x)
        logits[0, cls].backward()
    finally:
        h.remove()
    a, g = acts["a"][0].detach(), grads["g"][0].detach()          # C x h x w
    cam = torch.relu((g.mean(dim=(1, 2))[:, None, None] * a).sum(0))
    cam = cam / cam.max() if cam.max() > 0 else cam
    prob = float(torch.softmax(logits.detach(), dim=1)[0, cls])
    return cam.numpy(), prob


def render(crop_path, cam, out_dir):
    """Write the blended card image and the RGBA overlay; return their names."""
    stem = crop_path.stem
    heat = Image.fromarray(np.uint8(cam * 255)).resize((OUT_PX, OUT_PX), Image.BICUBIC)
    a = np.asarray(heat, dtype=np.float32) / 255.0
    rgba = np.zeros((OUT_PX, OUT_PX, 4), np.uint8)
    rgba[..., :3] = HEAT_RGB
    rgba[..., 3] = np.uint8(np.clip(a * MAX_ALPHA, 0, 1) * 255)
    overlay = Image.fromarray(rgba, "RGBA")
    overlay.save(out_dir / f"{stem}_alpha.png")
    base = Image.open(crop_path).convert("L").resize((OUT_PX, OUT_PX), Image.BICUBIC).convert("RGBA")
    Image.alpha_composite(base, overlay).convert("RGB").save(out_dir / f"{stem}.png")
    return f"heatmaps/{stem}.png", f"heatmaps/{stem}_alpha.png"


def selection():
    """crop file -> pose / what the image shows / source frame, from ml/real_crops.json."""
    sel_path = ML_DIR / "real_crops.json"
    if not sel_path.is_file():
        return {}, None
    sel = json.loads(sel_path.read_text(encoding="utf-8"))
    out = {}
    for group, prefix in (("survivors", "pos"), ("decoys", "neg")):
        for k, e in enumerate(sel[group], 1):
            out[f"{prefix}_{k:04d}.png"] = {"pose": e.get("pose"), "shows": e.get("shows"), "source": e["key"]}
    return out, sel.get("caption")


def floorplan_uses():
    """crop file -> the survivor / decoy that uses it in collapse_01."""
    fp = json.loads(FLOORPLAN.read_text(encoding="utf-8"))
    uses = {}
    for role, key in (("survivor", "survivors"), ("decoy", "decoys")):
        for s in fp.get(key, []):
            uses[s["thermal"]] = {"id": s["id"], "role": role, "object": s.get("label"),
                                  "pos": s["pos"]}
    return uses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ML_DIR / "models" / "detector.pt"))
    ap.add_argument("--crops", default=str(RUNTIME))
    args = ap.parse_args()
    crops = Path(args.crops)
    out = crops / "heatmaps"
    out.mkdir(exist_ok=True)

    torch.set_num_threads(1)
    model, ckpt = common.load_checkpoint(args.model, "cpu")
    thr = float(ckpt.get("threshold", common.THRESHOLD))
    tf = common.eval_transform()
    uses = floorplan_uses()
    picks, caption = selection()

    entries = []
    for p in sorted(crops.glob("*.png")):
        x = tf(Image.open(p)).unsqueeze(0)
        cam, prob = gradcam(model, x)
        with torch.no_grad():   # the same score the robot's detector computes
            conf = round(float(common.predict_pos_prob(model, x)[0]), 3)
        heatmap, alpha = render(p, cam, out)
        use = uses.get(p.name, {})
        entries.append({
            "id": use.get("id"),                 # S1 / D1 ... in collapse_01, or null if unused
            "file": p.name,                      # /crops/<file>
            "heatmap": heatmap,                  # /crops/<heatmap>, crop + heatmap blended
            "heatmap_alpha": alpha,              # /crops/<heatmap_alpha>, RGBA overlay only
            "label": "person" if p.stem.startswith("pos") else "not person",   # ground truth
            "conf": conf,                        # model P(person), same as survivor_found.conf
            "predicted": "person" if conf >= thr else "not person",
            "role": use.get("role"),             # survivor / decoy
            "object": use.get("object"),         # decoy stand-in: radiator, engine, coffee machine
            "pos": use.get("pos"),               # where it sits in the building (m)
            "pose": picks.get(p.name, {}).get("pose"),     # survivors: sitting / crouching / lying / bent
            "shows": picks.get(p.name, {}).get("shows"),   # what the real image actually shows
            "caption": caption,
            "source": picks.get(p.name, {}).get("source"),  # FLIR split/frame#crop box (held out)
        })
        print(f"{p.name}: {entries[-1]['id']} conf {conf:.3f} -> {heatmap}")

    manifest = {"threshold": thr, "layer": f"features[{LAYER}]", "size_px": OUT_PX, "caption": caption,
                "note": ("Grad-CAM for the person class. Paths are relative to /crops. Crops are held-out "
                         "FLIR ADAS v2 frames picked by ml/real_crops.py; `object` is the decoy's role in "
                         "the building, `shows` is what the real image is."),
                "crops": entries}
    (crops / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"wrote {len(entries)} crops to {crops / 'manifest.json'}")


if __name__ == "__main__":
    main()
