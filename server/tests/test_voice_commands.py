"""Robot side of voice / phone commands (rayan.md voice-contract entry): CMD sends a `command`
bundle with a cmd_id, the robot acts and answers with a priority-1 `command_ack`. Commands and
acks travel over the simulated radio, so a dark robot answers late."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from deadzone.command.plan import PlanManager, SearchPlan  # noqa: E402
from deadzone.command.safety import SafetyChecker  # noqa: E402
from deadzone.floorplan import FREE  # noqa: E402
from deadzone.network.dtn import make_bundle  # noqa: E402
from deadzone.sim import Sim  # noqa: E402
from test_demo_guard import demo_plan  # noqa: E402


def send(sim, rid, cmd_id, cmd, **extra):
    payload = {"cmd_id": cmd_id, "cmd": cmd, "source": "voice", "by": "test", "issued_t": sim.time, **extra}
    sim.network.queues["CMD"].append(make_bundle("CMD", rid, "command", payload, sim.time, 160))


def run_until(sim, t_end, log, stop=None):
    while sim.time < t_end - 1e-6:
        sim.tick()
        for e in sim.drain_events():
            log.append((round(sim.time, 1), e))
        if stop and stop():
            return


def received(log, cmd_id):
    return [e for _, e in log if e["kind"] == "command_received" and e["cmd_id"] == cmd_id]


def acks_at_cmd(log):
    return [t for t, e in log if e["kind"] == "bundle_delivered" and e.get("bundle_kind") == "command_ack"]


@pytest.fixture()
def sim30():
    sim = Sim(n_robots=3, seed=7)
    log = []
    run_until(sim, 30.0, log)
    return sim, log


def test_hold_then_resume(sim30):
    sim, log = sim30
    r = sim.robots["R1"]
    send(sim, "R1", "V-1", "hold")
    run_until(sim, 32.0, log)
    [ev] = received(log, "V-1")
    assert ev["status"] == "accepted" and ev["say"] == "Holding position." and r.state == "HOLDING"
    assert acks_at_cmd(log), "R1 is linked: the ack reaches Command at once"
    p0 = tuple(r.pose[:2])
    run_until(sim, 42.0, log)
    assert math.dist(p0, r.pose[:2]) < 0.2 and r.state == "HOLDING"
    send(sim, "R1", "V-2", "resume")
    run_until(sim, 50.0, log)
    assert received(log, "V-2")[0]["status"] == "accepted" and r.state != "HOLDING"
    assert math.dist(p0, r.pose[:2]) > 0.5


def test_go_to_a_known_point_then_holds(sim30):
    sim, log = sim30
    r = sim.robots["R3"]
    iy, ix = np.nonzero(r.map.grid == FREE)
    pts = [((x + 0.5) * r.cell, (y + 0.5) * r.cell) for x, y in zip(ix, iy)]
    target = min((p for p in pts if 4.0 < math.dist(p, r.pose[:2]) < 8.0 and r._plan_to(p)),
                 key=lambda p: abs(math.dist(p, r.pose[:2]) - 6.0))
    send(sim, "R3", "V-3", "go_to", target=[round(target[0], 2), round(target[1], 2)])
    run_until(sim, 31.0, log)
    [ev] = received(log, "V-3")
    assert ev["status"] == "accepted" and ev["eta_s"] > 0 and "about" in ev["say"]
    assert r.state == "GOING_TO_POINT"
    run_until(sim, 31.0 + 3 * ev["eta_s"] + 10, log,
              stop=lambda: any(e["kind"] == "command_completed" for _, e in log))
    done = [e for _, e in log if e["kind"] == "command_completed" and e["cmd_id"] == "V-3"]
    assert done and done[0]["say"] == "I'm there." and r.state == "HOLDING"
    assert math.dist(r.pose[:2], target) < 0.8
    assert r.cmds["V-3"]["status"] == "completed"


def test_return_home_completes_at_the_entrance(sim30):
    sim, log = sim30
    r = sim.robots["R2"]
    send(sim, "R2", "V-4", "return_home")
    run_until(sim, 31.0, log)
    [ev] = received(log, "V-4")
    assert ev["status"] == "accepted" and ev["eta_s"] > 0 and r.state == "RETURNING_HOME"
    run_until(sim, 31.0 + 3 * ev["eta_s"] + 15, log, stop=lambda: r.state == "DONE")
    run_until(sim, sim.time + 0.3, log)
    assert r.state == "DONE"
    assert any(e["kind"] == "command_completed" and e["cmd_id"] == "V-4" for _, e in log)


def test_explore_zone_becomes_top_priority(sim30):
    sim, log = sim30
    r = sim.robots["R1"]
    room = next(z for z in sim.prior.data["rooms"] if z["id"] == "E1")   # Warehouse Floor
    send(sim, "R1", "V-5", "explore_zone", zone={"id": room["id"], "name": room["name"], "poly": room["poly"]})
    run_until(sim, 31.0, log)
    [ev] = received(log, "V-5")
    assert ev["status"] == "accepted" and ev["say"].startswith("Heading to Warehouse Floor")
    assert r.zones[0]["id"] == "voice:E1"
    cx, cy = r.zones[0]["center"]
    d0 = math.dist(r.pose[:2], (cx, cy))
    run_until(sim, 60.0, log)
    assert math.dist(r.pose[:2], (cx, cy)) < d0 - 3, "R1 heads for the warehouse"


def test_refusals_and_dedupe(sim30):
    sim, log = sim30
    send(sim, "R1", "V-6", "dance")
    send(sim, "R1", "V-7", "go_to", target=[99, 99])
    send(sim, "R1", "V-8", "go_to", target=[38.0, 28.0])         # far corner, not mapped yet
    send(sim, "R1", "V-9", "hold")
    send(sim, "R1", "V-9", "hold")                               # same id again
    send(sim, "R1", "bad id!", "hold")                           # no valid id: ignored
    run_until(sim, 31.0, log)
    reasons = {cid: received(log, cid)[0]["reason"] for cid in ("V-6", "V-7", "V-8")}
    assert reasons == {"V-6": "bad_command", "V-7": "outside_building", "V-8": "no_route"}
    assert all(received(log, c)[0]["status"] == "refused" for c in reasons)
    assert len(received(log, "V-9")) == 1, "a repeated cmd_id is answered, not run twice"
    assert not any(e["kind"] == "command_received" and e["cmd_id"] == "bad id!" for _, e in log)
    # 4 answers + the repeat for V-9 = 5 acks at Command
    assert len(acks_at_cmd(log)) == 5


def test_safe_stop_refuses_until_resume(sim30):
    sim, log = sim30
    r = sim.robots["R1"]
    for _ in range(3):                      # the third motion fault in a minute -> SAFE_STOP
        r._enter_fault("STUCK")
    assert r.fault == "SAFE_STOP"
    send(sim, "R1", "V-10", "go_to", target=[5.0, 15.0])
    run_until(sim, 31.0, log)
    assert received(log, "V-10")[0]["reason"] == "safe_stop"
    send(sim, "R1", "V-11", "resume")
    run_until(sim, 32.0, log)
    assert received(log, "V-11")[0]["status"] == "accepted" and r.fault != "SAFE_STOP"


def test_dark_robot_answers_late():
    """The demo moment: a command to R2 while it is dark in the steel cage waits in custody;
    R2 answers when it reconnects, so Command hears back late."""
    sim = Sim(n_robots=3, seed=7)
    sim.tick()
    plans = PlanManager(sim, SafetyChecker(sim.prior, sim.robot_specs, sim.energy_time_scale))
    plans.save(SearchPlan.model_validate(demo_plan("P-1", "lost_link_ok")))
    assert plans.check("P-1")["ok"] and plans.dispatch("P-1")["ok"]
    log = []
    run_until(sim, 125.0, log)
    assert not sim.robots["R2"].linked, "R2 is in the steel cage (dark from 119.1 s)"
    send(sim, "R2", "V-12", "resume")
    run_until(sim, 160.0, log)
    [ev] = received(log, "V-12")
    t_decided = next(t for t, e in log if e["kind"] == "command_received")
    assert t_decided > 135.0, "R2 only gets the command after it reconnects"
    assert ev["status"] == "accepted"
    late = [t for t in acks_at_cmd(log) if t >= t_decided]
    assert late and late[0] - 125.0 > 10, "the answer reaches Command late"
