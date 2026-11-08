"""Benchmark v2: does the Deadzone advantage survive a different radio model? (in simulation)

Same comparison as ml/benchmark.py (Deadzone vs a baseline robot that stops when its link
drops), but every run also gets random rubble, and the radio model is swept:

  wall losses       0.7x, 1x, 1.3x every wall material (and rubble)
  path exponent     2.2, 2.6 (model default), 3.0
  link thresholds   -4 dB (links easier), 0, +4 dB (links harder), up and down moved together

One knob is moved at a time from the model default, plus two corners: "easy radio" (all three
knobs at their easiest) and "hard radio" (all three at their hardest). collapse_01 runs every
config with 30 seeds; each generated building on main (data/floorplans/generated/*.json) runs
the default and the hard corner with 10 seeds. A seed fixes the survivor layout and the rubble,
and both modes see the same seed, so every comparison is paired.

The radio model is changed only inside each worker process by patching module constants
(network.propagation, command.safety) and the loaded floor plan's wall losses. Robot code is
untouched and still predicts links with its own fixed assumptions, so a changed radio is also
a test of the robots coping with a radio that differs from what they expect.

    py ml/benchmark_v2.py                       # full sweep, about 90 min on 13 workers
    py ml/benchmark_v2.py --seeds 2 --gen-seeds 1 --seconds 60 --out <dir>   # quick check

Writes docs/assets/benchmark_v2.{md,png,json}.
"""
import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ML_DIR))

import numpy as np  # noqa: E402

import benchmark as v1  # noqa: E402  (reuses survivor placement, palette, constants)

MODES = v1.MODES
N_ROBOTS = v1.N_ROBOTS
DEFAULT_PLAN = ROOT / "data" / "floorplans" / "collapse_01.json"

# name -> (wall loss factor, path exponent, threshold shift dB)
CONFIGS = {
    "default":     (1.0, 2.6, 0.0),
    "walls 0.7x":  (0.7, 2.6, 0.0),
    "walls 1.3x":  (1.3, 2.6, 0.0),
    "exponent 2.2": (1.0, 2.2, 0.0),
    "exponent 3.0": (1.0, 3.0, 0.0),
    "thresholds -4 dB": (1.0, 2.6, -4.0),
    "thresholds +4 dB": (1.0, 2.6, 4.0),
    "easy radio":  (0.7, 2.2, -4.0),
    "hard radio":  (1.3, 3.0, 4.0),
}
GEN_CONFIGS = ("default", "hard radio")

RUBBLE_SIZE_M = 1.0
RUBBLE_CLEAR_M = 1.6      # pile center at least this far from any wall: never seals a door or corridor
RUBBLE_FROM_ENTRY_M = 4.0
RUBBLE_FROM_SURVIVOR_M = 2.0


def set_radio(walls, exponent, shift):
    """Patch the radio model in this worker process only."""
    from deadzone.command import safety
    from deadzone.network import propagation
    propagation.PATH_EXP = exponent
    propagation.LINK_UP_DBM = -82.0 + shift
    propagation.LINK_DOWN_DBM = -88.0 + shift
    safety.LINK_DOWN_DBM = propagation.LINK_DOWN_DBM
    return walls


def random_rubble(fp, seed, survivors):
    """3 to 6 static 1 m debris piles at random open spots (seeded). Added to the truth map
    before the run starts, so robots and Command only learn about them from the lidar."""
    from deadzone.robot import planning
    rng = np.random.default_rng([seed, 99])
    clear = int(math.ceil(RUBBLE_CLEAR_M / fp.cell))
    open_cells = ~planning.dilate(fp.occ | fp.nogo, clear) & v1.reachable_cells(fp)
    iy, ix = np.nonzero(open_cells)
    pts = np.stack([(ix + 0.5) * fp.cell, (iy + 0.5) * fp.cell], axis=1)
    ok = np.hypot(pts[:, 0] - fp.entry[0], pts[:, 1] - fp.entry[1]) >= RUBBLE_FROM_ENTRY_M
    for s in survivors:
        ok &= np.hypot(pts[:, 0] - s["pos"][0], pts[:, 1] - s["pos"][1]) >= RUBBLE_FROM_SURVIVOR_M
    pts = pts[ok]
    piles = []
    want = int(rng.integers(3, 7))
    h = RUBBLE_SIZE_M / 2
    for k in rng.permutation(len(pts)):
        x, y = (float(v) for v in pts[k])
        if all(math.dist((x, y), p) >= 3.0 for p in piles):
            fp.add_rubble([[x - h, y - h], [x + h, y - h], [x + h, y + h], [x - h, y + h]])
            piles.append((x, y))
        if len(piles) == want:
            break
    return [[round(x, 2), round(y, 2)] for x, y in piles]


def run_one(job):
    """One headless run. job = (building, config name, seed, mode, seconds)."""
    building, cfg, seed, mode, seconds = job
    walls, exponent, shift = CONFIGS[cfg]
    set_radio(walls, exponent, shift)
    from deadzone.floorplan import UNKNOWN
    from deadzone.robot import perception
    from deadzone.sim import Sim

    perception.reset_detector()
    plan = DEFAULT_PLAN if building == "collapse_01" else ROOT / "data" / "floorplans" / "generated" / f"{building}.json"
    sim = Sim(plan_path=plan, n_robots=N_ROBOTS, seed=seed)
    sim.fp.data["survivors"] = v1.place_survivors(sim.fp, seed)
    rubble = random_rubble(sim.fp, seed, sim.fp.data["survivors"])
    sim.fp.seg_loss = sim.fp.seg_loss * walls
    sim.fp.data["materials"] = {k: v * walls for k, v in sim.fp.data["materials"].items()}
    for r in sim.robots.values():
        r.mode = mode
    free = ~sim.fp.occ
    found, reported, relays, waits = {}, {}, 0, 0
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
                waits += 1
    known = (sim.post.map != UNKNOWN) & free
    return {"building": building, "config": cfg, "seed": seed, "mode": mode, "seconds": seconds,
            "n_survivors": len(sim.fp.data["survivors"]), "rubble": rubble,
            "found": found, "reported": reported, "relays": relays, "waits": waits,
            "coverage": round(float(known.sum() / free.sum()), 4),
            "detector": perception.get_detector().mode}


# ---------------------------------------------------------------------- summary
def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"mean": None, "min": None, "max": None, "n": 0}
    return {"mean": float(np.mean(vals)), "min": float(np.min(vals)), "max": float(np.max(vals)),
            "n": len(vals)}


def summarize(runs, seconds):
    """Per (building, config, mode): survivors reported, time to report, coverage, relays."""
    out = {}
    keys = sorted({(r["building"], r["config"]) for r in runs}, key=lambda k: (k[0] != "collapse_01", k[0], list(CONFIGS).index(k[1])))
    for b, c in keys:
        row = {}
        for m in MODES:
            rs = [r for r in runs if (r["building"], r["config"], r["mode"]) == (b, c, m)]
            n_surv = sum(r["n_survivors"] for r in rs)
            t_rep = [t for r in rs for t in r["reported"].values()]
            # time to report with never-reported survivors counted at the end of the run
            t_cens = [t for r in rs for t in
                      list(r["reported"].values()) + [seconds] * (r["n_survivors"] - len(r["reported"]))]
            row[m] = {"runs": len(rs), "survivors": n_surv,
                      "reported": sum(len(r["reported"]) for r in rs),
                      "reported_pct": 100 * sum(len(r["reported"]) for r in rs) / max(n_surv, 1),
                      "reported_per_run": stats([len(r["reported"]) for r in rs]),
                      "t_report": stats(t_rep),
                      "t_report_censored_mean": float(np.mean(t_cens)) if t_cens else None,
                      "coverage": stats([100 * r["coverage"] for r in rs]),
                      "relays": stats([r["relays"] for r in rs]),
                      "waits": stats([r["waits"] for r in rs])}
        by = {(r["seed"], r["mode"]): r for r in runs if (r["building"], r["config"]) == (b, c)}
        seeds = sorted({s for s, _ in by})
        diff = [len(by[(s, "deadzone")]["reported"]) - len(by[(s, "baseline")]["reported"])
                for s in seeds if (s, "deadzone") in by and (s, "baseline") in by]
        row["paired"] = {"seeds": len(diff), "dz_more": sum(d > 0 for d in diff),
                         "equal": sum(d == 0 for d in diff), "dz_fewer": sum(d < 0 for d in diff),
                         "mean_extra": float(np.mean(diff)) if diff else None}
        out[f"{b} | {c}"] = {"building": b, "config": c, "radio": CONFIGS[c], **row}
    return out


def verdict(summ):
    """Plain-English answer: does Deadzone report more survivors in every config?"""
    rows = list(summ.values())
    more = [r for r in rows if r["deadzone"]["reported"] > r["baseline"]["reported"]]
    equal = [r for r in rows if r["deadzone"]["reported"] == r["baseline"]["reported"]]
    fewer = [r for r in rows if r["deadzone"]["reported"] < r["baseline"]["reported"]]
    seed_fewer = sum(r["paired"]["dz_fewer"] for r in rows)
    seeds = sum(r["paired"]["seeds"] for r in rows)
    return {"rows": len(rows), "more": len(more), "equal": len(equal), "fewer": len(fewer),
            "fewer_names": [f"{r['building']} | {r['config']}" for r in fewer],
            "equal_names": [f"{r['building']} | {r['config']}" for r in equal],
            "seed_fewer": seed_fewer, "seeds": seeds,
            "holds": not fewer and len(more) == len(rows)}


# ---------------------------------------------------------------------- chart
def chart(summ, v, seconds, path, title="radio sensitivity sweep",
          footer="Radio values are model choices swept around our defaults; every run adds random rubble; paired seeds per row."):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    SURFACE, INK, INK2, GRID = v1.SURFACE, v1.INK, v1.INK2, v1.GRID
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "axes.titlecolor": INK, "axes.titlesize": 13, "axes.titleweight": "bold",
                         "axes.titlelocation": "left"})
    rows = list(summ.values())
    labels = [r["config"] if r["building"] == "collapse_01" else f"{r['building']}: {r['config']}" for r in rows]
    y = np.arange(len(rows))[::-1]
    fig, axes = plt.subplots(1, 3, figsize=(15, 0.42 * len(rows) + 2.6), facecolor=SURFACE,
                             gridspec_kw={"width_ratios": [1.25, 1, 1]})
    for ax in axes:
        ax.set_facecolor(SURFACE)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    off = {"deadzone": 0.17, "baseline": -0.17}

    # 1. survivors reported (% of all survivors in that row)
    ax = axes[0]
    for m in MODES:
        vals = [r[m]["reported_pct"] for r in rows]
        ax.barh(y + off[m], vals, height=0.32, color=v1.COLORS[m], label=v1.LABELS[m])
        for yy, val in zip(y, vals):
            ax.text(val + 1, yy + off[m], f"{val:.0f}%", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 112)
    ax.set_title("Survivors reported to Command")
    ax.set_xlabel(f"% of survivors, {seconds:.0f} s")
    # separator between collapse_01 rows and generated buildings
    n_main = sum(r["building"] == "collapse_01" for r in rows)
    for a in axes:
        if n_main < len(rows):
            a.axhline(len(rows) - n_main - 0.5, color=INK2, linewidth=0.8, linestyle=(0, (2, 3)))

    # 2. time until Command knows: mean with never-reported counted at the run end, range = reported only
    ax = axes[1]
    for m in MODES:
        mean = [r[m]["t_report_censored_mean"] for r in rows]
        ax.scatter(mean, y + off[m], color=v1.COLORS[m], s=36, zorder=3, edgecolor=SURFACE, linewidth=1)
        for yy, r in zip(y, rows):
            t = r[m]["t_report"]
            if t["n"]:
                ax.hlines(yy + off[m], t["min"], t["max"], color=v1.COLORS[m], alpha=0.35, linewidth=3)
    ax.set_yticks(y, [""] * len(rows))
    ax.set_xlim(0, seconds * 1.03)
    ax.set_title("Time until Command knows")
    ax.set_xlabel("sim s (dot = mean, unreported = run end)")

    # 3. map coverage on Command
    ax = axes[2]
    for m in MODES:
        mean = [r[m]["coverage"]["mean"] for r in rows]
        ax.scatter(mean, y + off[m], color=v1.COLORS[m], s=36, zorder=3, edgecolor=SURFACE, linewidth=1)
        for yy, r in zip(y, rows):
            c = r[m]["coverage"]
            ax.hlines(yy + off[m], c["min"], c["max"], color=v1.COLORS[m], alpha=0.35, linewidth=3)
    ax.set_yticks(y, [""] * len(rows))
    ax.set_xlim(0, 103)
    ax.set_title("Building mapped on Command")
    ax.set_xlabel("% of open floor (dot = mean, bar = range)")

    handles = [plt.Rectangle((0, 0), 1, 1, color=v1.COLORS[m]) for m in MODES]
    fig.legend(handles, [v1.LABELS[m] for m in MODES], loc="upper left", ncol=2, frameon=False,
               bbox_to_anchor=(0.005, 0.955), fontsize=11)
    holds = ("Deadzone reports more survivors in every radio setting tested" if v["holds"] else
             f"Deadzone reports more survivors in {v['more']} of {v['rows']} settings")
    fig.suptitle(f"In simulation: {title}. {holds}", x=0.01, ha="left",
                 fontsize=15, fontweight="bold", color=INK)
    fig.text(0.01, 0.012, "Simulation only, not a real-world result. " + footer,
             ha="left", va="bottom", fontsize=10.5, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 0.9), w_pad=2.5)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------- report
def rng_txt(s, fmt="{:.0f}", unit=""):
    if s["n"] == 0:
        return "none"
    return f"{fmt.format(s['mean'])}{unit} ({fmt.format(s['min'])} to {fmt.format(s['max'])})"


def report(summ, v, args, elapsed, path):
    seeds_main, seeds_gen = args.seeds, args.gen_seeds
    gens = sorted({r["building"] for r in summ.values()} - {"collapse_01"})
    if v["holds"]:
        answer = (f"**Yes.** In every one of the {v['rows']} radio settings and buildings tested, Deadzone "
                  "reported more survivors to Command than the baseline.")
    else:
        parts = []
        if v["equal"]:
            parts.append(f"tied in {v['equal']} ({', '.join(v['equal_names'])})")
        if v["fewer"]:
            parts.append(f"reported fewer in {v['fewer']} ({', '.join(v['fewer_names'])})")
        answer = (f"**Not everywhere.** Deadzone reported more survivors in {v['more']} of {v['rows']} "
                  f"settings and {'; '.join(parts)}.")
    answer += (f" Seed by seed (same survivors and rubble for both modes), Deadzone reported fewer "
               f"survivors than the baseline in {v['seed_fewer']} of {v['seeds']} paired runs.")
    lines = [
        "# Benchmark v2: radio sensitivity sweep (in simulation)",
        "",
        "> **Every number on this page is from our simulation, not from real robots or a real building.** "
        "The radio model's values are our choices; this sweep moves them around the defaults to check "
        "that the result does not depend on one lucky setting. It is still not a real-world result.",
        "",
        f"**Does the Deadzone advantage hold across the whole sweep?** {answer}",
        "",
        "![benchmark v2](benchmark_v2.png)",
        "",
        "## Setup",
        "",
        f"- Deadzone vs baseline (a robot that stops and waits when its link drops, no relays), "
        f"{N_ROBOTS} robots, {args.seconds:.0f} s of sim time per run, no plan dispatched, detector: "
        f"{args.detector}.",
        f"- **collapse_01** (the demo building): every radio setting below, {seeds_main} seeds each.",
        f"- **Generated buildings on main** ({', '.join(gens) if gens else 'none'}): default and hard radio, "
        f"{seeds_gen} seeds each.",
        "- A seed fixes the survivor layout (3 survivors at random reachable spots, at least 8 m from the "
        "entrance, 6 m apart) **and 3 to 6 random 1 m rubble piles** (at least 1.6 m from any wall so they "
        "never seal a door, 4 m from the entrance, 2 m from survivors). Rubble is in the truth map only; "
        "robots and Command learn about it from the lidar. Both modes run the same seeds.",
        "- Radio settings, one knob at a time from the default, plus two corners:",
        "",
        "| Setting | Wall losses | Path exponent | Link thresholds (up / down) |",
        "| --- | --- | --- | --- |",
    ]
    for name, (w, n, s) in CONFIGS.items():
        lines.append(f"| {name} | {w:g}x (concrete {16 * w:.1f} dB) | {n:g} | {-82 + s:g} / {-88 + s:g} dBm |")
    lines += [
        "",
        "The radio is changed in the simulated world only. Robot code is untouched and keeps its own "
        "fixed assumptions, so a changed radio also tests robots coping with a radio that behaves "
        "differently from what they expect.",
        "",
        "## Results (in simulation)",
        "",
        "Means with the range (min to max over seeds) in brackets. \"Reported\" means Command received the "
        "survivor bundle. Time to report covers reported survivors only, so it flatters the mode that "
        "reports fewer; the \"with misses\" column counts every unreported survivor at the run end.",
        "",
        "| Building, radio (in simulation) | Mode | Survivors reported | Per run | Time to report | Time with misses | Mapped on Command | Relays | Seeds where Deadzone reported more / same / fewer |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in summ.values():
        p = r["paired"]
        for m in MODES:
            d = r[m]
            lines.append(
                f"| {r['building']}, {r['config']} | {v1.LABELS[m].split(' (')[0]} | "
                f"{d['reported']} / {d['survivors']} ({d['reported_pct']:.0f}%) | "
                f"{rng_txt(d['reported_per_run'], '{:.1f}')} | {rng_txt(d['t_report'], unit=' s')} | "
                f"{d['t_report_censored_mean']:.0f} s | {rng_txt(d['coverage'], unit='%')} | "
                f"{rng_txt(d['relays'], '{:.1f}')} | "
                + (f"{p['dz_more']} / {p['equal']} / {p['dz_fewer']} |" if m == "deadzone" else " |"))
    lines += [
        "",
        f"Generated by `py ml/benchmark_v2.py` ({sum(r['deadzone']['runs'] + r['baseline']['runs'] for r in summ.values())} "
        f"runs, {elapsed / 60:.0f} min wall time). Raw runs in `benchmark_v2.json`. The original 20-seed "
        "benchmark (`benchmark.md`, no rubble, default radio) is unchanged.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--gen-seeds", type=int, default=10)
    ap.add_argument("--seconds", type=float, default=360.0)
    ap.add_argument("--workers", type=int, default=max(1, min(13, (os.cpu_count() or 2) - 3)))
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "assets")
    ap.add_argument("--replot", action="store_true", help="redraw chart and report from the saved benchmark_v2.json")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.replot:
        saved = json.loads((args.out / "benchmark_v2.json").read_text(encoding="utf-8"))
        runs = saved["runs"]
        args.seconds = runs[0]["seconds"]
        args.detector = runs[0]["detector"]
        args.seeds = max(r["seed"] for r in runs if r["building"] == "collapse_01")
        args.gen_seeds = max([r["seed"] for r in runs if r["building"] != "collapse_01"] or [0])
        summ = summarize(runs, args.seconds)
        v = verdict(summ)
        chart(summ, v, args.seconds, args.out / "benchmark_v2.png")
        elapsed = saved.get("elapsed_s", 57 * 60)
        report(summ, v, args, elapsed, args.out / "benchmark_v2.md")
        print("replotted from", args.out / "benchmark_v2.json")
        return

    gens = sorted(p.stem for p in (ROOT / "data" / "floorplans" / "generated").glob("*.json"))
    jobs = [("collapse_01", c, s, m, args.seconds) for c in CONFIGS for s in range(1, args.seeds + 1) for m in MODES]
    jobs += [(g, c, s, m, args.seconds) for g in gens for c in GEN_CONFIGS
             for s in range(1, args.gen_seeds + 1) for m in MODES]
    print(f"{len(jobs)} runs on {args.workers} workers", flush=True)
    t0 = time.time()
    runs = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_one, j) for j in jobs]
        for k, f in enumerate(as_completed(futs), 1):
            runs.append(f.result())
            if k % 20 == 0 or k == len(jobs):
                el = time.time() - t0
                print(f"{k}/{len(jobs)} done, {el / 60:.1f} min, eta {el / k * (len(jobs) - k) / 60:.0f} min", flush=True)
    elapsed = time.time() - t0
    runs.sort(key=lambda r: (r["building"], list(CONFIGS).index(r["config"]), r["seed"], r["mode"]))
    args.detector = runs[0]["detector"]
    summ = summarize(runs, args.seconds)
    v = verdict(summ)
    (args.out / "benchmark_v2.json").write_text(
        json.dumps({"configs": CONFIGS, "verdict": v, "summary": summ, "elapsed_s": round(elapsed),
                    "runs": runs}, indent=1), encoding="utf-8")
    chart(summ, v, args.seconds, args.out / "benchmark_v2.png")
    report(summ, v, args, elapsed, args.out / "benchmark_v2.md")
    for key, r in summ.items():
        print(f"{key:34s} dz {r['deadzone']['reported']:3d}/{r['deadzone']['survivors']}  "
              f"bl {r['baseline']['reported']:3d}/{r['baseline']['survivors']}  "
              f"cov {r['deadzone']['coverage']['mean']:.0f}/{r['baseline']['coverage']['mean']:.0f}%  "
              f"paired +{r['paired']['dz_more']} ={r['paired']['equal']} -{r['paired']['dz_fewer']}")
    print("holds across sweep:", v["holds"], f"({elapsed / 60:.0f} min)")


if __name__ == "__main__":
    main()
