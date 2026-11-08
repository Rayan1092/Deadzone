"""AUDIT #38: robots send cumulative counters in telemetry so the counters panel fills in."""
from deadzone.sim import Sim


def test_telemetry_carries_cumulative_counters(monkeypatch):
    monkeypatch.setenv("DETECTOR", "sim")
    sim = Sim(n_robots=2, seed=7)
    for _ in range(300):
        sim.tick()
    for r in sim.robots.values():
        c = r.telemetry(None)["counters"]
        assert set(c) >= {"detector_calls", "deadlines_met", "deadlines_missed"}
        assert c["deadlines_met"] == r.scheduler.met > 0 and c["deadlines_missed"] == r.scheduler.missed
        assert c["detector_calls"] == r.counters["detector_calls"]
    first = {rid: r.telemetry(None)["counters"]["deadlines_met"] for rid, r in sim.robots.items()}
    for _ in range(50):
        sim.tick()
    assert all(r.telemetry(None)["counters"]["deadlines_met"] > first[rid] for rid, r in sim.robots.items()), "cumulative"
    assert sim.snapshot()["stats"]["scheduler_deadlines_met"] == sum(r.scheduler.met for r in sim.robots.values())
