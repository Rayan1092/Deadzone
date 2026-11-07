import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.robot.robot import robot_rank  # noqa: E402
from deadzone.sim import Sim  # noqa: E402

TICKS = 600  # 60 s of sim time keeps the suite fast


def test_robot_rank_orders_ids():
    assert [robot_rank(r) for r in ("R1", "R2", "R3")] == [0, 1, 2]


def test_three_robots_share_targets_and_split():
    sim = Sim(n_robots=3, seed=7)
    close = both = 0
    for k in range(TICKS):
        sim.tick()
        sim.drain_events()
        # the command post still only learns through delivered bundles
        if k % 10 == 0:
            assert not ((sim.post.map > 0) & (sim.reality_map() == 0)).any()
        ts = [r.target for r in sim.robots.values()
              if r.target and r.state in ("EXPLORING", "LOST_LINK_EXPLORING")]
        if len(ts) >= 2:
            both += 1
            close += any(math.dist(a, b) < 4 for i, a in enumerate(ts) for b in ts[i + 1:])
    # every robot heard at least one peer's telemetry through its inbox
    assert all(r.peers for r in sim.robots.values())
    assert both > 0 and close / both < 0.5, f"robots chase the same frontier {close}/{both} ticks"

    solo = Sim(n_robots=1, seed=7)
    for _ in range(TICKS):
        solo.tick()
    assert (sim.reality_map() > 0).sum() > (solo.reality_map() > 0).sum()
