"""Export the shipped survivor detector to ONNX, check it matches PyTorch, time it on the CPU.

    py ml/export_onnx.py

Writes ml/models/detector.onnx (input "crop": N x 3 x 96 x 96 float, normalised exactly like
common.eval_transform; output "logits": N x 2, P(person) = softmax(logits)[:, 1]) and
ml/results/onnx_benchmark.json:

  match     PyTorch vs onnxruntime P(person) on the 40-image judge pool, the 6 demo crops and,
            when the crops are on disk, the 1,200 held-out FLIR crops: largest difference and
            whether every verdict at the 0.6 threshold is the same
  latency   one crop at a time (batch 1, what the robot does), onnxruntime and PyTorch, 1 thread
            and 4 threads, after warm-up: mean, median, p95 in ms, on this machine's CPU
  budget    the robot's perception task (server/deadzone/robot/scheduler.py: every 500 ms with a
            40 ms compute budget) and how many crops fit in it at the measured speed

Needs `pip install onnx onnxruntime onnxscript` (ml/requirements.txt). Nothing in the server
uses the ONNX file; the robot still runs the PyTorch model.
"""
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))
import common  # noqa: E402

MODEL = ML_DIR / "models" / "detector.pt"
ONNX = ML_DIR / "models" / "detector.onnx"
OUT = ML_DIR / "results" / "onnx_benchmark.json"
WARMUP, RUNS = 50, 1000
PERCEPTION_PERIOD_MS, PERCEPTION_BUDGET_MS = 500, 40      # scheduler.py TASKS ("perception", 500, 40)


def cpu_name():
    try:
        if platform.system() == "Windows":
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                                 capture_output=True, text=True, timeout=20).stdout.strip()
            if out:
                return out
    except Exception:
        pass
    return platform.processor() or platform.machine()


def softmax_p(logits):
    z = logits - logits.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e[:, 1] / e.sum(axis=1)


def image_sets():
    tf = common.eval_transform()
    sets = {}
    pool = json.loads((ML_DIR / "results" / "judge_pool" / "manifest.json").read_text())
    sets["judge pool (40)"] = [ML_DIR / "results" / "judge_pool" / i["file"] for i in pool["items"]]
    rt = json.loads((ML_DIR / "crops" / "runtime" / "manifest.json").read_text())
    sets["demo crops (6)"] = [ML_DIR / "crops" / "runtime" / c["file"] for c in rt["crops"] if c.get("role")]
    val = ML_DIR / "data" / "crops" / "val"
    if val.is_dir():
        sets["FLIR held-out (1200)"] = sorted(val.glob("pos/*.png")) + sorted(val.glob("neg/*.png"))
    return {k: torch.stack([tf(Image.open(p)) for p in v]) for k, v in sets.items()}


def time_it(fn, x):
    for _ in range(WARMUP):
        fn(x)
    ts = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        fn(x)
        ts.append((time.perf_counter() - t0) * 1000)
    ts = np.array(ts)
    return {"mean_ms": round(float(ts.mean()), 3), "median_ms": round(float(np.median(ts)), 3),
            "p95_ms": round(float(np.percentile(ts, 95)), 3)}


def main():
    import onnx
    import onnxruntime as ort

    model, ckpt = common.load_checkpoint(MODEL, "cpu")
    model.eval()
    thr = float(ckpt.get("threshold", common.THRESHOLD))
    dummy = torch.zeros(1, 3, common.IMG_SIZE, common.IMG_SIZE)
    torch.onnx.export(model, dummy, str(ONNX), input_names=["crop"], output_names=["logits"],
                      dynamic_axes={"crop": {0: "n"}, "logits": {0: "n"}}, opset_version=17, dynamo=False)
    onnx.checker.check_model(onnx.load(str(ONNX)))

    # ---- outputs match
    sess = ort.InferenceSession(str(ONNX), providers=["CPUExecutionProvider"])
    match = {}
    for name, x in image_sets().items():
        with torch.no_grad():
            p_torch = torch.softmax(model(x), dim=1)[:, 1].numpy()
        p_onnx = softmax_p(sess.run(["logits"], {"crop": x.numpy()})[0])
        match[name] = {"n": int(len(x)), "max_abs_diff": float(np.abs(p_torch - p_onnx).max()),
                       "same_verdicts": int(((p_torch >= thr) == (p_onnx >= thr)).sum())}

    # ---- latency, one crop at a time
    one = image_sets()["demo crops (6)"][:1]
    lat = {}
    for threads in (1, 4):
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        s = ort.InferenceSession(str(ONNX), sess_options=so, providers=["CPUExecutionProvider"])
        xn = one.numpy()
        lat[f"onnxruntime, {threads} thread{'s' if threads > 1 else ''}"] = time_it(lambda a: s.run(["logits"], {"crop": a}), xn)
        torch.set_num_threads(threads)
        with torch.no_grad():
            lat[f"PyTorch, {threads} thread{'s' if threads > 1 else ''}"] = time_it(model, one)
    torch.set_num_threads(os.cpu_count() or 1)

    best1 = lat["onnxruntime, 1 thread"]["median_ms"]
    out = {
        "machine": {"cpu": cpu_name(), "logical_cores": os.cpu_count(), "os": platform.platform(),
                    "onnxruntime": ort.__version__, "torch": torch.__version__},
        "model": {"file": "ml/models/detector.onnx", "bytes": ONNX.stat().st_size, "input": "crop: N x 3 x 96 x 96",
                  "output": "logits: N x 2", "threshold": thr, "opset": 17},
        "match": match,
        "latency_batch1": lat,
        "budget": {"perception_period_ms": PERCEPTION_PERIOD_MS, "perception_budget_ms": PERCEPTION_BUDGET_MS,
                   "crops_per_budget_onnx_1_thread_here": int(PERCEPTION_BUDGET_MS // best1)},
        "runs": RUNS, "warmup": WARMUP,
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
