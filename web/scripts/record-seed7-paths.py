"""Record every robot's path in the main run (the demo guard's exact replay: seed 7, 3 robots,
DZ_OBSTACLES=1, DZ_SMART_RUBBLE=1, plan P-1 fixed to lost_link_ok, F at 177.5 s, O at 187.5 s)
into web/tests/fixtures/seed7-paths.json, for the web test that no visual-only prop in
collapse_01 sits on a path a robot drives (the picture must never show a robot phasing).

Run from the repo root with the server's venv:  server/.venv/bin/python web/scripts/record-seed7-paths.py
Re-run whenever the demo guard is re-baselined (server/tests/test_demo_guard.py BEATS)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "server" / "tests"))
os.environ.update({"DZ_OBSTACLES": "1", "DZ_SMART_RUBBLE": "1"})

import test_demo_guard as guard  # noqa: E402  (FLAGS, DIRECTOR, demo_plan: one source)
from deadzone.command.plan import PlanManager, SearchPlan  # noqa: E402
from deadzone.command.safety import SafetyChecker  # noqa: E402
from deadzone.robot import perception  # noqa: E402
from deadzone.sim import ROBOT_RADIUS_M, Sim  # noqa: E402

END = 300.0   # the demo ends about 3:25 on the 1.5x clock (sim ~250 s); margin past that
STEP_M = 0.1  # keep a pose [x, y, sim t] when the robot moved this far

assert all(os.environ.get(k) == v for k, v in guard.FLAGS.items()), "flags out of sync with the guard"
perception.reset_detector()
sim = Sim(n_robots=3, seed=7)
sim.tick()
plans = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
plans.save(SearchPlan.model_validate(guard.demo_plan("P-1", "relay")))
plans.check("P-1")
plans.save(SearchPlan.model_validate(guard.demo_plan("P-1", "lost_link_ok")))
plans.check("P-1")
plans.dispatch("P-1")
paths = {rid: [] for rid in sim.bodies}
while sim.time < END:
    act = guard.DIRECTOR.get(round(sim.time, 1))
    if act:
        name, rid = act
        (sim.robots[rid].inject_overcurrent if name == "overcurrent" else sim.robots[rid].inject_perception_overload)()
    sim.tick()
    sim.drain_events()
    for rid, b in sim.bodies.items():
        p = paths[rid]
        if not p or (b["x"] - p[-1][0]) ** 2 + (b["y"] - p[-1][1]) ** 2 >= STEP_M ** 2:
            p.append([round(b["x"], 2), round(b["y"], 2), round(sim.time, 1)])
out = ROOT / "web" / "tests" / "fixtures" / "seed7-paths.json"
out.write_text(json.dumps({"floorplan": "collapse_01", "seed": 7, "end_s": END, "flags": guard.FLAGS,
                           "robot_radius_m": ROBOT_RADIUS_M, "step_m": STEP_M, "paths": paths}, separators=(",", ":")))
print(out.relative_to(ROOT), {rid: len(p) for rid, p in paths.items()}, f"{out.stat().st_size // 1024} KB")
