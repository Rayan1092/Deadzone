"""Benchmark at published radio values (in simulation, benchmark only).

    py ml/benchmark_published.py              # about 25 min on 13 workers
    py ml/benchmark_published.py --replot     # redraw from docs/assets/benchmark_published.json

Same comparison as ml/benchmark_v2.py (Deadzone vs a baseline that stops when its link drops,
random rubble per seed, paired seeds), but the radio uses published 2.4 GHz values instead of
our chosen ones. Server radio code is NOT changed: values are patched inside each worker only.

Published values (sources in docs/assets/benchmark_published.md):
  wall losses   NIST, Stone 1997 (NISTIR 6055), measured at 2.437 GHz:
                drywall panel ~1 dB (a wall = 2 panels: 2 dB), brick 6 dB,
                concrete 15 dB (102 mm) / 29 dB (203 mm), reinforced concrete 31 dB (203 mm)
  path exponent ITU-R P.1238 indoor distance power loss coefficient at 2.4 GHz:
                N = 30 office (exponent 3.0), 28 residential (2.8)
  metal         no measurement of a steel cage at 2.4 GHz found; published door / partition
                figures range from 6-10 dB to 20-30 dB, so metal is bracketed at 10, 20, 30 dB
  rubble        treated as thin concrete: 15 dB (NIST 102 mm)
  thresholds    unchanged (-82 up / -88 down dBm): receiver sensitivity, not propagation
"""
import argparse
import json
import os
os.environ.setdefault("DZ_SCENARIO_EVENTS", "0")  # results predate scenario events (collapse_01's 162.5 s collapse)
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

import benchmark as v1  # noqa: E402
import benchmark_v2 as v2  # noqa: E402

OURS = {"drywall": 4, "brick": 10, "concrete": 16, "metal": 22, "rubble": 8}
BASE = {"drywall": 2, "brick": 6, "concrete": 29, "rubble": 15}
# name -> (materials dB, path exponent, threshold shift dB)
PUBLISHED = {
    "published low (n 2.8, metal 10)": ({**BASE, "metal": 10}, 2.8, 0.0),
    "published mid (n 3.0, metal 20)": ({**BASE, "metal": 20}, 3.0, 0.0),
    "published high (n 3.0, metal 30)": ({**BASE, "metal": 30}, 3.0, 0.0),
}
GEN = ("published low (n 2.8, metal 10)", "published high (n 3.0, metal 30)")
# register the names so benchmark_v2's summary / chart ordering knows them
v2.CONFIGS.update({k: (1.0, n, s) for k, (_, n, s) in PUBLISHED.items()})


def run_one(job):
    building, cfg, seed, mode, seconds = job
    mats, exponent, shift = PUBLISHED[cfg]
    v2.set_radio(1.0, exponent, shift)
    import numpy as np
    from deadzone.floorplan import UNKNOWN
    from deadzone.robot import perception
    from deadzone.sim import Sim

    perception.reset_detector()
    plan = v2.DEFAULT_PLAN if building == "collapse_01" else ROOT / "data" / "floorplans" / "generated" / f"{building}.json"
    sim = Sim(plan_path=plan, n_robots=v2.N_ROBOTS, seed=seed)
    sim.fp.data["survivors"] = v1.place_survivors(sim.fp, seed)
    rubble = v2.random_rubble(sim.fp, seed, sim.fp.data["survivors"])
    # every segment's loss came from one material value; map each value to the published one
    old = sim.fp.data["materials"]
    by_value = {float(v): float(mats[name]) for name, v in old.items()}
    if len(by_value) != len(old):
        raise SystemExit(f"{building}: two materials share a loss value, cannot remap: {old}")
    sim.fp.seg_loss = np.array([by_value[float(v)] for v in sim.fp.seg_loss])
    sim.fp.data["materials"] = {name: float(mats[name]) for name in old}
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


def report(summ, v, seconds, elapsed, path):
    rows = list(summ.values())
    main = [r for r in rows if r["building"] == "collapse_01"]
    holds = v["holds"]
    answer = ("**Yes.** At published values Deadzone reported more survivors than the baseline in every setting "
              f"and building ({v['rows']} of {v['rows']}), and fewer in {v['seed_fewer']} of {v['seeds']} paired runs."
              if holds else
              f"**Not everywhere.** Deadzone reported more in {v['more']} of {v['rows']} settings; tied in "
              f"{v['equal']} ({', '.join(v['equal_names'])}); fewer in {v['fewer']} ({', '.join(v['fewer_names'])}).")
    lines = [
        "# Benchmark at published radio values (in simulation)",
        "",
        "> **In simulation, not a real-world result.** The radio here uses published 2.4 GHz measurements "
        "instead of our chosen values; the building, robots and rubble are still simulated. Server radio code "
        "is unchanged: these values are patched inside the benchmark only.",
        "",
        f"**Does the Deadzone advantage hold at published values?** {answer}",
        "",
        "![benchmark at published values](benchmark_published.png)",
        "",
        "## Radio values",
        "",
        "| Item | Our model (server) | Published value used here | Source |",
        "| --- | --- | --- | --- |",
        "| Drywall wall | 4 dB | 2 dB (2 panels x ~1 dB) | NIST, Stone 1997, NISTIR 6055, 2.437 GHz |",
        "| Brick wall | 10 dB | 6 dB | NIST, Stone 1997 |",
        "| Concrete wall | 16 dB | 29 dB (203 mm; 102 mm measured 15 dB) | NIST, Stone 1997 |",
        "| Rubble pile | 8 dB | 15 dB (as 102 mm concrete) | NIST, Stone 1997 (by analogy) |",
        "| Metal (steel cage) | 22 dB | 10 / 20 / 30 dB bracket | no cage measurement found; published door / partition figures 6-10 to 20-30 dB |",
        "| Path exponent | 2.6 | 2.8 residential, 3.0 office | ITU-R P.1238, 2.4 GHz (N = 28 / 30) |",
        "| Link thresholds | -82 up / -88 down dBm | unchanged | receiver sensitivity, not propagation |",
        "",
        "## Results (in simulation)",
        "",
        "Means with min to max over seeds. \"Reported\" means Command received the survivor bundle.",
        "",
        "| Building, radio | Mode | Survivors reported | Time to report | Mapped on Command | Relays | Seeds where Deadzone reported more / same / fewer |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        p = r["paired"]
        for m in v2.MODES:
            d = r[m]
            lines.append(f"| {r['building']}, {r['config']} | {v1.LABELS[m].split(' (')[0]} | "
                         f"{d['reported']} / {d['survivors']} ({d['reported_pct']:.0f}%) | "
                         f"{v2.rng_txt(d['t_report'], unit=' s')} | {v2.rng_txt(d['coverage'], unit='%')} | "
                         f"{v2.rng_txt(d['relays'], '{:.1f}')} | "
                         + (f"{p['dz_more']} / {p['equal']} / {p['dz_fewer']} |" if m == "deadzone" else " |"))
    base = {r["config"]: r for r in main}
    lines += [
        "",
        "## For Aziz: calibrated values, your call",
        "",
        "If the server's radio should match published data, the values are: materials "
        "`{\"drywall\": 2, \"brick\": 6, \"concrete\": 29, \"metal\": 20, \"rubble\": 15}` "
        "(metal is the least certain; 10 to 30 dB all keep the result) and `PATH_EXP = 3.0`. "
        "This page changes nothing in the server; the demo guard was measured with the current values, "
        "so changing them would move the DEMO.md beats and needs a dry run first.",
        "",
        f"Generated by `py ml/benchmark_published.py` ({sum(r['deadzone']['runs'] + r['baseline']['runs'] for r in rows)} runs, "
        f"{seconds:.0f} s of sim time each, {elapsed / 60:.0f} min wall time).",
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
    ap.add_argument("--replot", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "benchmark_published.json"
    if args.replot:
        saved = json.loads(out_json.read_text(encoding="utf-8"))
        runs, elapsed = saved["runs"], saved.get("elapsed_s", 0)
    else:
        gens = sorted(p.stem for p in (ROOT / "data" / "floorplans" / "generated").glob("*.json"))
        jobs = [("collapse_01", c, s, m, args.seconds) for c in PUBLISHED for s in range(1, args.seeds + 1) for m in v2.MODES]
        jobs += [(g, c, s, m, args.seconds) for g in gens for c in GEN for s in range(1, args.gen_seeds + 1) for m in v2.MODES]
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
    seconds = runs[0]["seconds"]
    summ = v2.summarize(runs, seconds)
    v = v2.verdict(summ)
    out_json.write_text(json.dumps({"published": PUBLISHED, "ours": OURS, "verdict": v, "summary": summ,
                                    "elapsed_s": round(elapsed), "runs": runs}, indent=1), encoding="utf-8")
    v2.chart(summ, v, seconds, args.out / "benchmark_published.png", title="published 2.4 GHz radio values",
             footer="Wall losses from NIST (Stone 1997), path exponent from ITU-R P.1238, metal bracketed 10-30 dB; random rubble; paired seeds.")
    report(summ, v, seconds, elapsed, args.out / "benchmark_published.md")
    for key, r in summ.items():
        print(f"{key:50s} dz {r['deadzone']['reported']:3d}/{r['deadzone']['survivors']}  "
              f"bl {r['baseline']['reported']:3d}/{r['baseline']['survivors']}  "
              f"paired +{r['paired']['dz_more']} ={r['paired']['equal']} -{r['paired']['dz_fewer']}")
    print("holds:", v["holds"])


if __name__ == "__main__":
    main()
