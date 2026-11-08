"""Robot.counters: Reality-side tallies for the "Under the hood" panel (detector calls, persons and
rejections, scheduler deadlines met and missed, rescue routes computed, replans, seconds without
link). They live on the Robot object for the sim to sum into tick.stats and never ride in a bundle."""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot import perception  # noqa: E402
from deadzone.robot.scheduler import Scheduler  # noqa: E402
from deadzone.sim import Sim  # noqa: E402

KEYS = {"detector_calls", "detector_persons", "detector_rejections", "detector_unsure", "scheduler_deadlines_met",
        "scheduler_deadlines_missed", "rescue_routes", "replans", "dark_s"}


def test_scheduler_counts_deadlines_met_and_missed():
    s = Scheduler()
    for frame in range(40):                       # 4 s nominal, through the cached hyperperiod
        s.run_frame(frame)
    met_nominal = s.met
    assert met_nominal > 0 and s.missed == 0
    s.set_wcet("perception", 400)                 # the demo's overload moment
    for frame in range(40, 80):
        s.run_frame(frame)
    assert s.missed > 0 and s.met > met_nominal
    s.reset_wcet("perception")
    before = s.met
    for frame in range(80, 120):
        s.run_frame(frame)
    assert s.met > before                         # keeps counting once the backlog clears


def test_robot_counters_follow_the_demo_run():
    perception.reset_detector()
    sim = Sim(n_robots=3, seed=7)
    events, fired = [], set()
    while sim.time < 60:
        t = round(sim.time, 1)
        if t == 20.0 and t not in fired:
            fired.add(t)
            sim.robots["R3"].inject_perception_overload()
        if t == 40.0 and t not in fired:
            fired.add(t)
            x, y, th = sim.robots["R1"].pose
            sim.drop_rubble((x + math.cos(th) * 1.5, y + math.sin(th) * 1.5))
        sim.tick()
        events += sim.drain_events()
    for r in sim.robots.values():
        c = r.counters
        assert set(c) == KEYS and all(v >= 0 for v in c.values())
        assert c["detector_calls"] == c["detector_persons"] + c["detector_rejections"] + c["detector_unsure"]
        assert c["detector_unsure"] == 0                  # the six demo crops are never unsure
        assert c["scheduler_deadlines_met"] > 0
        assert r.telemetry({})["counters"] == c          # the Reality snapshot carries them for tick.stats
    total = {k: sum(r.counters[k] for r in sim.robots.values()) for k in KEYS}
    assert total["detector_persons"] == sum(len(r.found) for r in sim.robots.values()) >= 1   # S3 at 14.4 s
    assert total["detector_rejections"] == sum(e["kind"] == "hotspot_rejected" for e in events)
    assert total["rescue_routes"] == sum(e["kind"] == "rescue_route" for e in events) >= 1
    assert total["replans"] == sum(e["kind"] == "replan" for e in events) >= 1                # rubble ahead of R1
    assert sim.robots["R3"].counters["scheduler_deadlines_missed"] >= 1                       # overloaded at 20 s
    assert sim.robots["R1"].counters["scheduler_deadlines_missed"] == 0
    # never on the radio or in Command: the panel reads Reality
    assert "counters" not in json.dumps(sim.snapshot()["command"])
    for queue in sim.network.queues.values():
        assert "counters" not in json.dumps(queue)
