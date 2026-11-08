"""Belief-map Phase 2 comparison (py ml/bayes_compare.py, about 4 min): seed 7, 3 robots, P-1 dispatched, 300 s, DZ_SEARCH_BAYES off vs on.
Reports survivors found over time, Reality map coverage (known cells / cells that are not walls in
the truth plan) at 60 s and 180 s, and Command's known cells. Prints one JSON line per run."""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "server" / "tests"))
os.environ["DZ_MODE"] = "deadzone"


def run(flag_on, duration=300):
    os.environ["DZ_SEARCH_BAYES"] = "1" if flag_on else "0"
    from deadzone.command.plan import PlanManager, SearchPlan
    from deadzone.command.safety import SafetyChecker
    from deadzone.sim import Sim
    from test_demo_guard import demo_plan
    sim = Sim(n_robots=3, seed=7)
    sim.tick()
    pm = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
    pm.save(SearchPlan.model_validate(demo_plan("P-1", "lost_link_ok")))
    assert pm.dispatch("P-1")["ok"]
    floor = ~sim.fp.occ.astype(bool)
    found, reported, coverage, faults = {}, {}, {}, {}
    t0 = time.perf_counter()
    while sim.time < duration:
        sim.tick()
        for e in sim.drain_events():
            if e["kind"] == "survivor_found":
                found.setdefault(e["survivor"], round(sim.time, 1))
            elif e["kind"] == "survivor_reported":
                reported.setdefault(e["survivor"], round(sim.time, 1))
            elif e["kind"] == "fault":
                faults[e["fault"]] = faults.get(e["fault"], 0) + 1
        t = round(sim.time, 1)
        if t in (60.0, 120.0, 180.0, 240.0, 300.0):
            known = sim.reality_map() != 0
            coverage[int(t)] = {"reality_pct": round(100 * float((known & floor).sum() / floor.sum()), 1),
                                "command_cells": int((sim.post.map != 0).sum())}
    return {"flag": "on" if flag_on else "off", "found": found, "reported": reported, "coverage": coverage,
            "faults": faults, "states": {r: s.state for r, s in sim.robots.items()},
            "wall_s": round(time.perf_counter() - t0, 1)}


if __name__ == "__main__":
    for flag_on in (False, True):
        print(json.dumps(run(flag_on)), flush=True)
