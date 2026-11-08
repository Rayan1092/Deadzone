"""Survivor belief map (Phase 1, display only): prior from the building prior, miss updates where
a camera looked and saw nobody, confirmations and rejections, normalization to the people still
missing, Reality team merge vs Command from delivered data, uint8 rendering on a shared scale."""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadzone.floorplan import FloorPlan  # noqa: E402
from deadzone.robot import belief  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def demo_prior():
    data = json.loads((ROOT / "data" / "floorplans" / "collapse_01.json").read_text())
    fp = FloorPlan(data)
    return data, fp, belief.prior_grid(data, fp.occ, fp.cell)


def test_prior_is_zero_in_walls_and_higher_in_rooms_collapse_and_dead_zones():
    data, fp, prior = demo_prior()
    assert prior.shape == fp.occ.shape and prior.dtype == np.float32
    assert (prior[fp.occ.astype(bool)] == 0).all()
    corridor = prior[fp.to_cell(16.0, 15.0)[1], fp.to_cell(16.0, 15.0)[0]]
    office = prior[fp.to_cell(5.0, 24.0)[1], fp.to_cell(5.0, 24.0)[0]]
    cage = prior[fp.to_cell(37.0, 27.0)[1], fp.to_cell(37.0, 27.0)[0]]
    pile = prior[fp.to_cell(28.5, 24.5)[1], fp.to_cell(28.5, 24.5)[0]]        # RB3 is occupied: 0
    edge = prior[fp.to_cell(26.5, 24.5)[1], fp.to_cell(26.5, 24.5)[0]]        # beside the pile
    assert 0 < corridor < office < cage and pile == 0 and edge > office
    assert belief.expected_survivors(data) == 3 and belief.expected_survivors({"expected_survivors": "x"}) == 3


def test_a_look_lowers_only_what_the_camera_could_see():
    data, fp, prior = demo_prior()
    b = belief.Belief(prior, fp.cell, expected=3)
    before = b.missing_grid().copy()
    pose = (5.0, 24.0, 0.0)                                   # in Office A, looking east
    n = b.observe(pose, fp.occ)
    assert n > 0 and b.observations == 1
    after = b.missing_grid()
    near = fp.to_cell(7.0, 24.0)                              # 2 m ahead: seen, recall 0.96
    far = fp.to_cell(9.6, 24.0)                               # 4.6 m ahead: seen, lower recall
    behind = fp.to_cell(3.0, 24.0)                            # behind the camera
    other_room = fp.to_cell(15.0, 24.0)                       # through the wall into Office B
    assert b.miss[near[1], near[0]] <= 1 - belief.RECALL_NEAR + 1e-6
    assert 1 - belief.RECALL_NEAR < b.miss[far[1], far[0]] < 1.0
    assert b.miss[behind[1], behind[0]] == 1.0 and b.miss[other_room[1], other_room[0]] == 1.0
    assert math.isclose(after.sum(), 3.0, rel_tol=1e-4)                          # still 3 missing
    assert after[near[1], near[0]] < before[near[1], near[0]]
    assert after[other_room[1], other_room[0]] > before[other_room[1], other_room[0]]   # mass moves elsewhere


def test_confirm_and_reject_and_normalization():
    data, fp, prior = demo_prior()
    b = belief.Belief(prior, fp.cell, expected=3)
    b.confirm("S3", (5.0, 26.0))
    g = b.missing_grid()
    ix, iy = fp.to_cell(5.0, 26.0)
    assert g[iy, ix] == 0 and math.isclose(g.sum(), 2.0, rel_tol=1e-4) and b.missing() == 2
    nb = fp.to_cell(6.5, 26.0)
    assert g[nb[1], nb[0]] < prior[nb[1], nb[0]] / prior.sum() * 3 * belief.CONFIRM_NEIGHBOUR_FACTOR * 1.6
    b.reject("D1", (15.0, 28.0))
    rx, ry = fp.to_cell(15.0, 28.0)
    g2 = b.missing_grid()
    assert g2[ry, rx] < g[ry, rx]
    img = b.render()
    assert img.dtype == np.uint8 and img[iy, ix] == 255 and img.max() == 255 and 0 < img[img < 255].max() <= 254
    for _ in range(3):
        b.confirm(f"S{_}", (10.0 + _, 5.0))
    final = b.render()
    assert b.missing() == 0 and b.missing_grid().sum() == 0 and final[final < 255].max() == 0


def test_team_merge_and_command_lag_on_a_shared_scale():
    data, fp, prior = demo_prior()

    class R:
        def __init__(self):
            self.belief = belief.Belief(prior, fp.cell, expected=3)

    r1, r2 = R(), R()
    r1.belief.observe((5.0, 24.0, 0.0), fp.occ)
    r2.belief.observe((20.0, 15.0, math.pi), fp.occ)
    r2.belief.confirm("S1", (36.0, 27.0))
    grid, confirmed, missing = belief.team_belief([r1, r2], prior, fp.cell, 3)
    assert missing == 2 and math.isclose(grid.sum(), 2.0, rel_tol=1e-4) and len(confirmed) == 1
    c1 = fp.to_cell(7.0, 24.0)
    c2 = fp.to_cell(18.0, 15.0)
    assert grid[c1[1], c1[0]] < prior[c1[1], c1[0]] / prior.sum() * 2 and grid[c2[1], c2[0]] < prior[c2[1], c2[0]] / prior.sum() * 2
    # Command knows only what was delivered: one pose and nothing confirmed yet
    cmd = belief.CommandBelief(prior, fp.cell, expected=3)
    cmd.observe((5.0, 24.0, 0.0), fp.occ)
    reality_img = belief.render(grid, confirmed)
    command_img = cmd.render(scale_max=float(grid.max()))
    assert cmd.missing() == 3 and command_img.max() <= 255 and command_img.shape == reality_img.shape
    # the same cell reads brighter on Command (it has not seen the second look, nor the find)
    assert command_img[c2[1], c2[0]] >= reality_img[c2[1], c2[0]]
    assert reality_img[fp.to_cell(36.0, 27.0)[1], fp.to_cell(36.0, 27.0)[0]] == 255
    assert command_img[fp.to_cell(36.0, 27.0)[1], fp.to_cell(36.0, 27.0)[0]] < 255


def test_robots_build_their_belief_in_the_demo_run_and_command_lags():
    """Seed 7, 3 robots, 60 s: each robot's camera lowers the belief where it looked, S3's find
    accounts for one person, and a CommandBelief fed only with delivered telemetry and survivor
    records never knows more than the team (same arithmetic, shared scale)."""
    from deadzone.robot import perception
    from deadzone.sim import Sim
    perception.reset_detector()
    sim = Sim(n_robots=3, seed=7)
    data, fp = sim.fp.data, sim.fp
    prior = belief.prior_grid(data, sim.prior.occ, fp.cell)
    expected = belief.expected_survivors(data)
    cmd = belief.CommandBelief(prior, fp.cell, expected)
    while sim.time < 60:
        sim.tick()
        sim.drain_events()
        for rid, rec in sim.post.robots.items():              # what Aziz's receive() would feed
            cmd.observe_delivered(rid, rec["pose"], rec.get("sent_t", rec.get("last_seen")), sim.prior.occ)
        for sid, rec in sim.post.survivors.items():
            cmd.confirm(sid, rec["pos"])
    grid, confirmed, missing = belief.team_belief(sim.robots.values(), prior, fp.cell, expected)
    assert all(r.belief.observations > 50 for r in sim.robots.values())
    assert "S3" in {s for r in sim.robots.values() for s in r.belief.confirmed} and missing == 2
    assert math.isclose(grid.sum(), 2.0, rel_tol=1e-3)
    looked = sum(float((r.belief.miss < 1).sum()) for r in sim.robots.values())
    assert looked > 500
    reality_img = belief.render(grid, confirmed)
    command_img = cmd.render(scale_max=float(grid.max()))
    assert reality_img.shape == command_img.shape == prior.shape
    assert cmd.missing() <= 3 and cmd.observations <= sum(r.belief.observations for r in sim.robots.values())
    # Command (one delivered pose per second) holds less evidence than the team (a look every
    # 0.5 s from the robots' own poses): less total certainty, never more confirmations
    team_miss = np.ones_like(prior)
    for r in sim.robots.values():
        team_miss *= r.belief.miss
    assert np.log(np.clip(cmd.miss, 1e-9, 1)).sum() >= np.log(np.clip(team_miss, 1e-9, 1)).sum()
    assert set(cmd.confirmed) <= set(confirmed_ids := {s for r in sim.robots.values() for s in r.belief.confirmed})
