"""Deadzone vs baseline benchmark: does keeping going in the dark actually help?

Runs the same 3-robot search in both robot modes:
  deadzone  the real thing: explores in the dark, drops relays, comes back to report
  baseline  "without Deadzone": stops and waits as soon as its link drops, no relays

Each seed is a different survivor layout: the 3 survivors (same ids and thermal crops) are
placed at random reachable spots in collapse_01, at least 8 m from the entrance and 6 m apart.
The authored demo layout is run as well, as a reference row. No plan is dispatched, so both
modes run plain autonomy. Everything is deterministic for a given seed.

Writes docs/assets/benchmark.md, docs/assets/benchmark.png and docs/assets/benchmark.json.

    py ml/benchmark.py                  # 20 seeds, 360 s each, both modes (~5 min on 14 cores)
    py ml/benchmark.py --seeds 3 --seconds 120 --out <dir>   # quick check
"""
import argparse
import json
import math
import os
import sys
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")   # one torch thread per worker process
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import numpy as np  # noqa: E402

MODES = ("deadzone", "baseline")
N_ROBOTS = 3
MIN_FROM_ENTRY_M = 8.0
MIN_APART_M = 6.0
SAMPLE_EVERY_S = 10.0


def reachable_cells(fp):
    """Cells a robot can stand in (1-cell wall inflation, like the planner) reachable from
    the entrance, on the truth map. Survivors are only placed where a robot could get to."""
    from deadzone.robot import planning
    trav = ~planning.dilate(fp.occ | fp.nogo, 1)
    sx, sy = fp.to_cell(*fp.entry)
    seen = np.zeros_like(trav)
    q = deque([(sx, sy)])
    seen[sy, sx] = True
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < fp.w and 0 <= ny < fp.h and trav[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((nx, ny))
    return seen


def place_survivors(fp, seed):
    """Random survivor layout for this seed. Keeps ids and thermal crops, moves positions."""
    rng = np.random.default_rng(seed)
    iy, ix = np.nonzero(reachable_cells(fp))
    pts = np.stack([(ix + 0.5) * fp.cell, (iy + 0.5) * fp.cell], axis=1)
    far = np.hypot(pts[:, 0] - fp.entry[0], pts[:, 1] - fp.entry[1]) >= MIN_FROM_ENTRY_M
    pts = pts[far]
    chosen = []
    for k in rng.permutation(len(pts)):
        p = pts[k]
        if all(math.dist(p, c) >= MIN_APART_M for c in chosen):
            chosen.append(p)
        if len(chosen) == len(fp.data["survivors"]):
            break
    survivors = []
    for s, p in zip(fp.data["survivors"], chosen):
        survivors.append(dict(s, pos=[round(float(p[0]), 2), round(float(p[1]), 2)]))
    return survivors


def run_one(job):
    """One headless run. job = (seed or None for the demo layout, mode, seconds)."""
    seed, mode, seconds = job
    from deadzone.floorplan import UNKNOWN
    from deadzone.robot import perception
    from deadzone.sim import Sim

    perception.reset_detector()
    sim = Sim(n_robots=N_ROBOTS, seed=7 if seed is None else seed)
    if seed is not None:
        sim.fp.data["survivors"] = place_survivors(sim.fp, seed)
    for r in sim.robots.values():
        r.mode = mode
    free = ~sim.fp.occ
    found, reported, relays, waiting = {}, {}, 0, 0
    curve = []
    next_sample = 0.0
    while sim.time < seconds - 1e-6:
        sim.tick()
        t = round(sim.time, 1)
        for e in sim.drain_events():
            k = e["kind"]
            if k == "survivor_found":
                found.setdefault(e["survivor"], t)
            elif k == "survivor_reported":
                reported.setdefault(e["survivor"], t)
            elif k == "relay_dropped":
                relays += 1
            elif k == "waiting_for_link":
                waiting += 1
        if t >= next_sample - 1e-6:
            known = (sim.post.map != UNKNOWN) & free
            curve.append([t, round(float(known.sum() / free.sum()), 4)])
            next_sample += SAMPLE_EVERY_S
    known = (sim.post.map != UNKNOWN) & free
    return {"seed": seed, "mode": mode, "seconds": seconds,
            "survivors": [s["id"] for s in sim.fp.data["survivors"]],
            "layout": {s["id"]: s["pos"] for s in sim.fp.data["survivors"]},
            "found": found, "reported": reported, "relays": relays, "waits": waiting,
            "coverage": round(float(known.sum() / free.sum()), 4), "curve": curve,
            "detector": perception.get_detector().mode}


def summarize(runs, mode):
    rs = [r for r in runs if r["mode"] == mode and r["seed"] is not None]
    n_surv = sum(len(r["survivors"]) for r in rs)
    found = sum(len(r["found"]) for r in rs)
    reported = sum(len(r["reported"]) for r in rs)
    t_rep = [t for r in rs for t in r["reported"].values()]
    t_found = [t for r in rs for t in r["found"].values()]
    return {"runs": len(rs), "survivors": n_surv, "found": found, "reported": reported,
            "per_run_reported": [len(r["reported"]) for r in rs],
            "median_t_found": float(np.median(t_found)) if t_found else None,
            "median_t_reported": float(np.median(t_rep)) if t_rep else None,
            "t_reported": t_rep,
            "coverage_mean": float(np.mean([r["coverage"] for r in rs])),
            "coverage_min": float(np.min([r["coverage"] for r in rs])),
            "coverage_max": float(np.max([r["coverage"] for r in rs])),
            "relays_mean": float(np.mean([r["relays"] for r in rs])),
            "waits_mean": float(np.mean([r["waits"] for r in rs]))}


# ---------------------------------------------------------------------- chart
# Reference palette (dataviz skill), light surface, categorical slots 1 and 2.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLORS = {"deadzone": "#2a78d6", "baseline": "#eb6834"}
LABELS = {"deadzone": "Deadzone", "baseline": "Baseline (stops when the link drops)"}


def chart(runs, summ, seconds, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "axes.titlecolor": INK, "axes.titlesize": 13, "axes.titleweight": "bold",
                         "axes.titlelocation": "left"})
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.2), facecolor=SURFACE)
    for ax in axes.flat:
        ax.set_facecolor(SURFACE)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
    names = [LABELS[m].split(" (")[0] for m in MODES]

    def bars(ax, vals, fmt, ymax=None):
        b = ax.bar(names, vals, width=0.5, color=[COLORS[m] for m in MODES], edgecolor=SURFACE,
                   linewidth=2)
        for rect, v in zip(b, vals):
            ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(), fmt.format(v),
                    ha="center", va="bottom", color=INK, fontsize=12, fontweight="bold")
        if ymax:
            ax.set_ylim(0, ymax)

    # 1. survivors that reached Command
    ax = axes[0, 0]
    pct = [100 * summ[m]["reported"] / summ[m]["survivors"] for m in MODES]
    bars(ax, pct, "{:.0f}%", 112)
    ax.set_title("Survivors that reached Command")
    ax.set_ylabel(f"% of {summ['deadzone']['survivors']} survivors, {seconds:.0f} s")

    # 2. time until Command knows (each reported survivor)
    ax = axes[0, 1]
    for i, m in enumerate(MODES):
        ts = summ[m]["t_reported"]
        if not ts:
            continue
        jitter = np.random.default_rng(i).uniform(-0.14, 0.14, len(ts))   # fixed, so reruns match
        ax.scatter(i + jitter, ts, s=36, color=COLORS[m], edgecolor=SURFACE, linewidth=1.5, zorder=3)
        med = summ[m]["median_t_reported"]
        ax.hlines(med, i - 0.25, i + 0.25, color=INK, linewidth=2, zorder=4)
        ax.text(i + 0.29, med, f"median {med:.0f} s", va="center", color=INK, fontsize=11)
    ax.set_xticks(range(len(MODES)), names)
    ax.set_xlim(-0.6, 1.9)
    ax.set_ylim(0, seconds)
    ax.set_title("Time until Command knows (reported survivors only)")
    ax.set_ylabel("sim seconds")

    # 3. Command map coverage over time
    ax = axes[1, 0]
    for m in MODES:
        rs = [r for r in runs if r["mode"] == m and r["seed"] is not None]
        t = np.array([p[0] for p in rs[0]["curve"]])
        c = np.array([[p[1] for p in r["curve"]] for r in rs]) * 100
        ax.fill_between(t, c.min(axis=0), c.max(axis=0), color=COLORS[m], alpha=0.15, linewidth=0)
        ax.plot(t, c.mean(axis=0), color=COLORS[m], linewidth=2)
        ax.text(t[-1] + 4, c.mean(axis=0)[-1], f"{names[MODES.index(m)]}\n{c.mean(axis=0)[-1]:.0f}%",
                va="center", color=INK, fontsize=11)
    ax.set_xlim(0, seconds * 1.13)
    ax.set_ylim(0, 100)
    ax.set_title("Building mapped on Command (mean, band = min to max)")
    ax.set_xlabel("sim seconds")
    ax.set_ylabel("% of open floor")

    # 4. relays dropped
    ax = axes[1, 1]
    bars(ax, [summ[m]["relays_mean"] for m in MODES], "{:.1f}", 2 * N_ROBOTS + 0.8)
    ax.set_title("Relays dropped per run")
    ax.set_ylabel(f"mean, {N_ROBOTS} robots x 2 carried")

    n = summ["deadzone"]["runs"]
    fig.suptitle(f"In simulation: Deadzone vs a robot that stops when its link drops ({n} survivor "
                 f"layouts, {N_ROBOTS} robots, {seconds:.0f} s each)", x=0.01, ha="left", fontsize=15,
                 fontweight="bold", color=INK)
    fig.text(0.01, 0.012, "Simulation only, not a real-world result. Radio wall losses and link "
             "thresholds are chosen model values, not measurements.", ha="left", va="bottom",
             fontsize=10.5, color=INK2)
    fig.tight_layout(rect=(0, 0.035, 1, 0.95), h_pad=2.2, w_pad=3)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------- report
def fmt_t(v):
    return "never" if v is None else f"{v:.0f} s"


def report(runs, summ, seconds, elapsed, path):
    d, b = summ["deadzone"], summ["baseline"]
    demo = {r["mode"]: r for r in runs if r["seed"] is None}
    lines = [
        "# Benchmark: Deadzone vs baseline (in simulation)",
        "",
        "> **Every number on this page is from our simulation, not from real robots or a real "
        "building.** The radio model's wall losses (drywall 4 dB, brick 10, concrete 16, metal 22) "
        "and link thresholds (up above -82 dBm, down below -88) are values we chose, not "
        "measurements. The results show the idea works in our model; they are not a real-world result.",
        "",
        f"Generated by `py ml/benchmark.py` ({d['runs']} survivor layouts x 2 modes + the demo layout, "
        f"{N_ROBOTS} robots, {seconds:.0f} s of sim time each, detector: {runs[0]['detector']}, "
        f"{elapsed:.0f} s wall time).",
        "",
        "- **Deadzone** (demo default): robots keep exploring when the signal dies, drop relays "
        "before the link breaks, and come back to report.",
        "- **Baseline** (\"without Deadzone\", `DZ_MODE=baseline`): same robots, same mapping and "
        "planning, but a robot stops and waits as soon as its link drops (like a tethered or "
        "teleoperated robot) and carries no relays.",
        "",
        "Each seed moves the 3 survivors to random reachable spots in collapse_01 (at least "
        f"{MIN_FROM_ENTRY_M:.0f} m from the entrance and {MIN_APART_M:.0f} m apart). No plan is dispatched. "
        "\"Reported\" means Command actually received the survivor bundle; \"found\" means a "
        "robot saw them (it may still be stuck in the dark with the news).",
        "",
        "![benchmark](benchmark.png)",
        "",
        "## Summary (in simulation)",
        "",
        "| In simulation | Deadzone | Baseline |",
        "| --- | --- | --- |",
        f"| Survivors reported to Command | **{d['reported']} / {d['survivors']}** | {b['reported']} / {b['survivors']} |",
        f"| Survivors seen by a robot | {d['found']} / {d['survivors']} | {b['found']} / {b['survivors']} |",
        f"| Median time until Command knows | {fmt_t(d['median_t_reported'])} | {fmt_t(b['median_t_reported'])} |",
        f"| Median time until a robot sees them | {fmt_t(d['median_t_found'])} | {fmt_t(b['median_t_found'])} |",
        f"| Building mapped on Command at {seconds:.0f} s (mean, min to max) | "
        f"**{100 * d['coverage_mean']:.0f}%** ({100 * d['coverage_min']:.0f} to {100 * d['coverage_max']:.0f}%) | "
        f"{100 * b['coverage_mean']:.0f}% ({100 * b['coverage_min']:.0f} to {100 * b['coverage_max']:.0f}%) |",
        f"| Relays dropped per run (mean) | {d['relays_mean']:.1f} | {b['relays_mean']:.1f} |",
        f"| Robots stuck waiting for a link per run (mean) | {d['waits_mean']:.1f} | {b['waits_mean']:.1f} |",
        "",
        "Median times only count survivors that were reported or seen, so they flatter the "
        "baseline: the survivors it never reports are the hard ones. Map coverage is the same for "
        "every layout because the building and the robots don't change, only where the survivors are.",
        "",
        "## Demo layout (in simulation: seed 7, authored survivors, no plan)",
        "",
        "| In simulation | Deadzone | Baseline |",
        "| --- | --- | --- |",
    ]
    for sid in demo["deadzone"]["survivors"]:
        cells = []
        for m in MODES:
            r = demo[m]
            rep = r["reported"].get(sid)
            fnd = r["found"].get(sid)
            if rep is not None:
                cells.append(f"reported {rep:.0f} s")
            elif fnd is not None:
                cells.append(f"seen {fnd:.0f} s, never reported")
            else:
                cells.append("not found")
        lines.append(f"| {sid} | {cells[0]} | {cells[1]} |")
    lines += [
        f"| Mapped on Command | {100 * demo['deadzone']['coverage']:.0f}% | {100 * demo['baseline']['coverage']:.0f}% |",
        f"| Relays | {demo['deadzone']['relays']} | {demo['baseline']['relays']} |",
        "",
        "## Per layout (in simulation)",
        "",
        "| Seed (in simulation) | Deadzone reported | Deadzone mapped | Baseline reported | Baseline mapped |",
        "| --- | --- | --- | --- | --- |",
    ]
    seeds = sorted({r["seed"] for r in runs if r["seed"] is not None})
    by = {(r["seed"], r["mode"]): r for r in runs}
    for s in seeds:
        dz, bl = by[(s, "deadzone")], by[(s, "baseline")]
        lines.append(f"| {s} | {len(dz['reported'])} / 3 | {100 * dz['coverage']:.0f}% | "
                     f"{len(bl['reported'])} / 3 | {100 * bl['coverage']:.0f}% |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--seconds", type=float, default=360.0)
    ap.add_argument("--workers", type=int, default=max(1, min(14, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "assets")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    jobs = [(s, m, args.seconds) for s in range(1, args.seeds + 1) for m in MODES]
    jobs += [(None, m, args.seconds) for m in MODES]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        runs = list(ex.map(run_one, jobs))
    elapsed = time.time() - t0
    summ = {m: summarize(runs, m) for m in MODES}

    (args.out / "benchmark.json").write_text(json.dumps({"summary": summ, "runs": runs}, indent=1),
                                             encoding="utf-8")
    chart(runs, summ, args.seconds, args.out / "benchmark.png")
    report(runs, summ, args.seconds, elapsed, args.out / "benchmark.md")
    for m in MODES:
        s = summ[m]
        print(f"{m:9s} reported {s['reported']}/{s['survivors']}  found {s['found']}  "
              f"median_t_rep {s['median_t_reported']}  coverage {s['coverage_mean']:.2f}  "
              f"relays {s['relays_mean']:.1f}")
    print(f"wrote {args.out} in {elapsed:.0f} s")


if __name__ == "__main__":
    main()
