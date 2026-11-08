"""Trained survivor detector hook, with the sim sensor as fallback.

Robot code calls `filter_hits(io.thermal())`. Each hit is a thermal hot spot from
the camera: {"id", "pos", "crop", "conf"}. The detector scores the crop image and
drops hits below the threshold (decoys like radiators or engines).

The module falls back to passthrough (sim sensor, hits unchanged) when:
  - DETECTOR=sim is set,
  - torch / torchvision is not installed,
  - the model file is missing or fails to load.

It only reads the crop filename that `io` handed over and never touches the Sim.
"""
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("deadzone.perception")

REPO = Path(__file__).resolve().parents[3]
ML_DIR = REPO / "ml"
DEFAULT_MODEL = ML_DIR / "models" / "detector.pt"
CROP_DIR = ML_DIR / "crops" / "runtime"


class Passthrough:
    mode = "sim"
    threshold = 0.0

    def __init__(self, reason):
        self.reason = reason

    def score(self, crop_name):
        return None

    def heatmap(self, crop_name):
        return None   # no model, so nothing to explain


class Detector:
    mode = "model"

    def __init__(self, model_path, crop_dir=CROP_DIR):
        import torch
        if str(ML_DIR) not in sys.path:
            sys.path.insert(0, str(ML_DIR))
        import common
        torch.set_num_threads(1)   # tiny model, keep the sim loop's CPU free
        self._torch = torch
        self._common = common
        self.model, ckpt = common.load_checkpoint(model_path, "cpu")
        self.threshold = float(ckpt.get("threshold", common.THRESHOLD))
        self.tf = common.eval_transform()
        self.crop_dir = Path(crop_dir)
        self.cache = {}

    def score(self, crop_name):
        """P(person) for a runtime crop, or None if the crop can't be read."""
        if not crop_name:
            return None
        if crop_name in self.cache:
            return self.cache[crop_name]
        from PIL import Image
        path = self.crop_dir / Path(crop_name).name   # no path traversal out of crop_dir
        try:
            img = Image.open(path)
            img.load()
        except OSError:
            log.warning("detector: crop %s not found, using sim sensor for it", path)
            self.cache[crop_name] = None
            return None
        x = self.tf(img).unsqueeze(0)
        s = round(float(self._common.predict_pos_prob(self.model, x)[0]), 3)
        self.cache[crop_name] = s
        return s

    def heatmap(self, crop_name):
        """Grad-CAM image for this crop, relative to /crops ("heatmaps/pos_0001.png"), or None.
        Precomputed by ml/gradcam.py with this same model, so it shows where it looked."""
        if not crop_name:
            return None
        name = f"heatmaps/{Path(crop_name).stem}.png"
        return name if (self.crop_dir / name).is_file() else None


_detector = None


def make_detector(model_path=None, env=None):
    env = os.environ if env is None else env
    if env.get("DETECTOR", "").lower() == "sim":
        return Passthrough("DETECTOR=sim")
    path = Path(model_path or env.get("DETECTOR_MODEL") or DEFAULT_MODEL)
    if not path.is_file():
        return Passthrough(f"no model at {path}")
    try:
        return Detector(path)
    except ImportError as e:
        return Passthrough(f"torch unavailable ({e.name})")
    except Exception as e:  # corrupt / incompatible checkpoint: never take the robot down
        return Passthrough(f"model load failed: {e!r}")


def get_detector():
    global _detector
    if _detector is None:
        _detector = make_detector()
        if _detector.mode == "sim":
            log.warning("survivor detector: sim sensor fallback (%s)", _detector.reason)
        else:
            log.info("survivor detector: trained model, threshold %.2f", _detector.threshold)
    return _detector


def reset_detector():
    """For tests: forget the cached detector so env changes take effect."""
    global _detector
    _detector = None


_close_cache = {}


def close_crop(crop_name):
    """The close-up view of a runtime crop, by convention `<name>_close.<ext>` next to it in
    ml/crops/runtime, or None when there is no such file. A hot spot the model is unsure about
    from a distance is judged again on this image once the robot has moved close."""
    if not crop_name:
        return None
    if crop_name not in _close_cache:
        p = Path(crop_name)
        candidate = f"{p.stem}_close{p.suffix}"
        _close_cache[crop_name] = candidate if (CROP_DIR / candidate).is_file() else None
    return _close_cache[crop_name]


def filter_hits(hits, detector=None):
    """Score each thermal hit with the trained model and keep likely survivors."""
    det = detector or get_detector()
    out = []
    for h in hits:
        s = det.score(h.get("crop"))
        if s is None:
            out.append(h)            # passthrough / no crop: trust the sim sensor
        elif s >= det.threshold:
            out.append({**h, "conf": s, "detector": "model"})
    return out
