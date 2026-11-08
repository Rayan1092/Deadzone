"""Compare actual camera coverage, discoveries and repeated travel for both policies."""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "server" / "tests"))
from deadzone.command.plan import PlanManager, SearchPlan
from deadzone.command.safety import SafetyChecker
from deadzone.robot.exploration import ProgressExplorer
from deadzone.sim import Sim
from test_demo_guard import demo_plan


def run(enabled, assigned, duration, seed, floorplan=None):
    os.environ["DZ_EXPLORATION_V2"] = "1" if enabled else "0"
    sim = Sim(**({"plan_path": floorplan} if floorplan else {}), n_robots=3, seed=seed)
    sim.tick()
    if assigned:
        manager = PlanManager(
            sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale)
        )
        manager.save(SearchPlan.model_validate(demo_plan("MEASURE", "lost_link_ok")))
        assert manager.dispatch("MEASURE")["ok"]
    cameras = {
        rid: ProgressExplorer(r.map.grid.shape, r.cell) for rid, r in sim.robots.items()
    }
    stats = {
        rid: {
            "planning_calls": 0,
            "target_changes": 0,
            "distance_m": 0.0,
            "room_entries": {},
            "visited": set(),
            "repeated_exploration_cells": 0,
        }
        for rid in sim.robots
    }
    last = {
        rid: (r.last_plan_t, tuple(r.pose[:2]), None, set())
        for rid, r in sim.robots.items()
    }
    found = {}
    faults = {}
    started = time.perf_counter()
    while sim.time < duration:
        sim.tick()
        for rid, r in sim.robots.items():
            st = stats[rid]
            t, pos, goal, rooms = last[rid]
            st["distance_m"] += math.dist(pos, r.pose[:2])
            active = r.state in ("EXPLORING", "LOST_LINK_EXPLORING")
            # Same independent camera observer for both policies, without altering robots.
            cameras[rid].observe(r.map.grid, r.pose, r.t, active)
            inside = set()
            # Floorplan truth is used ONLY by this external evaluator, never the policy.
            for room in sim.fp.data["rooms"]:
                xs, ys = zip(*room["poly"])
                if (
                    min(xs) + 0.75 < r.pose[0] < max(xs) - 0.75
                    and min(ys) + 0.75 < r.pose[1] < max(ys) - 0.75
                ):
                    inside.add(room["id"])
                    if active and room["id"] not in rooms:
                        st["room_entries"][room["id"]] = (
                            st["room_entries"].get(room["id"], 0) + 1
                        )
            if active:
                if r.last_plan_t != t:
                    st["planning_calls"] += 1
                if (
                    goal is not None
                    and r.goal_cell is not None
                    and math.dist(goal, r.goal_cell) * r.cell > 1
                ):
                    st["target_changes"] += 1
                q = (int(r.pose[0] // 0.5), int(r.pose[1] // 0.5))
                previous = (int(pos[0] // 0.5), int(pos[1] // 0.5))
                if q != previous:
                    if q in st["visited"]:
                        st["repeated_exploration_cells"] += 1
                    st["visited"].add(q)
            last[rid] = (r.last_plan_t, tuple(r.pose[:2]), r.goal_cell, inside)
        for event in sim.drain_events():
            if event["kind"] == "survivor_found":
                found.setdefault(event["survivor"], round(sim.time, 1))
            if event["kind"] == "fault":
                fault = event["fault"]
                faults[fault] = faults.get(fault, 0) + 1
    union = np.logical_or.reduce([c.surveyed for c in cameras.values()])
    safe = ~sim.fp.occ & ~sim.fp.nogo
    for rid, st in stats.items():
        st["unique_exploration_cells"] = len(st.pop("visited"))
        st["distance_m"] = round(st["distance_m"], 1)
        st["graph_searches"] = (
            sim.robots[rid].explorer.searches if enabled else st["planning_calls"]
        )
        st["state"] = sim.robots[rid].state
        st["fault"] = sim.robots[rid].fault
    return {
        "enabled": enabled,
        "assigned": assigned,
        "seed": seed,
        "simulated_s": duration,
        "wall_s": round(time.perf_counter() - started, 2),
        "camera_coverage_pct": round(100 * (union & safe).sum() / safe.sum(), 1),
        "known_command_cells": int((sim.post.map != 0).sum()),
        "found": found,
        "reported": sorted(sim.post.survivors),
        "fault_events": faults,
        "robots": stats,
        "floorplan": sim.fp.data["id"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=240)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--floorplan",
        type=Path,
        help="alternative layout; runs without the fixed demo plan",
    )
    args = parser.parse_args()
    os.environ.update(DZ_MODE="deadzone", DZ_FEC="0")
    results = []
    for enabled in (False, True):
        for assigned in (False,) if args.floorplan else (False, True):
            result = run(enabled, assigned, args.duration, args.seed, args.floorplan)
            results.append(result)
            print(json.dumps(result), flush=True)
    if args.output:
        args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
