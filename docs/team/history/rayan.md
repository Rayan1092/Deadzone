# Rayan Diya: robots + ML

Owns `server/deadzone/robot/`, `ml/`, `data/floorplans/`. Only Rayan's sessions edit this file.

## Now
- **Working on:** `rayan/plans` next: robots follow dispatched zones / no-go / `lost_link_budget_s` from `io.radio.receive()`.
- **Works on main:** frontier exploration, 3-robot target sharing, relay auto-drop, A* return home, lost-link + 10 s reconnect hold, REPLANNING around rubble, rate monotonic scheduler with carry-over and deadline misses, full fault FSM (OVERCURRENT, STUCK, SAFE_STOP, LOW_BATTERY, TRAPPED). Seed 7, 3 robots: S1 found dark at 182.3 s, on Command at 187.3 s, 4 relays.
- **In flight (not merged):** `rayan/safe-stop-resume`: CMD `resume` command bundle clears SAFE_STOP.
- **Blocked on / need from others:** Aziz: two director values (see Blocked in the newest entry). Aziz's `p2/peer-telemetry-dtn` replaces my temporary shim; robots read peer telemetry from `robot.inbox` today, so tell me where peer bundles land (`robot.inbox` or `io.radio.receive()`) and I'll switch.
- **Promises to others:** states final: DEPLOYING, EXPLORING, LOST_LINK_EXPLORING, RETURNING_TO_SIGNAL, RETURNING_HOME, REPLANNING, FAULT, DONE. Faults final: null, OVERCURRENT, STUCK, LOW_BATTERY, TRAPPED, SAFE_STOP. `tasks` slices as in PR #7, `missed` can now be true. Robot hooks: `inject_overcurrent(seconds=1.0)`, `inject_perception_overload(seconds=3.0, wcet_ms=400)`.

## Log

### 2026-11-07 17:10 · rayan/safe-stop-resume · SAFE_STOP can be resumed from CMD
- **Did:** robots now read `io.radio.receive()` every step. A `command` bundle with payload `{"cmd": "resume"}` clears SAFE_STOP and the fault counter, raises a `resumed` event, then the robot replans and carries on. Plan bundles that arrive are stored on the robot (acted on in `rayan/plans`). The resume only reaches a robot that has a route to CMD; a robot that safe-stopped in a dead zone stays stopped until a relay reaches it (realistic, by design).
- **Contract changes:** new command bundle `kind:"command"`, `src:"CMD"`, `dst:<robot id>`, `payload:{"cmd":"resume"}` (builder `deadzone.robot.robot.resume_command(rid, now)`). New event `resumed {robot}`.
- **Heads-up for others:** Yusuf: optional toast for the `resumed` event.
- **Blocked:** Aziz, please wire two director values in `app.py` (nothing else needed from my side):
  1. Key **O** → `control {action:"director", value:{do:"overload", robot:"R1"}}` → `sim.robots[robot].inject_perception_overload()`. The scheduler overload moment: perception misses deadlines for 3 s, safety never does.
  2. `{do:"resume", robot:"R1"}` → `sim.network.queues["CMD"].append(resume_command(robot, sim.time))` with `from .robot.robot import resume_command`. Must go through the CMD queue, never straight into the robot, so it obeys the network like every other bundle.
- **Next:** robots follow dispatched plans.

### 2026-11-07 16:56 · rayan/scheduler-faults · PR #8 Scheduler overload and full fault FSM
- **Did:** scheduler carries unfinished jobs across frames, flags slices past their deadline `missed: true`, skips a release while the previous job overruns. `inject_perception_overload()` makes perception cost 400 ms for 3 s: about 1 perception deadline miss per second, safety never misses (still runs at 0 and 50 ms). Fault FSM: OVERCURRENT and STUCK stop, back up 0.5 m, mark ahead, REPLANNING; 3rd motion fault within 60 s gives SAFE_STOP (state FAULT, wheels off); LOW_BATTERY label while heading home; every fault sends a priority-1 `fault` bundle `{robot, fault, pos, t, state}` to CMD.
- **Contract changes:** new event `deadline_miss {robot, task}`. `fault` events now cover all 5 values. `tasks[].missed` can be true. New robot hook `inject_perception_overload(seconds=3.0, wcet_ms=400)`.
- **Heads-up for others:** Aziz: please wire a director key for `sim.robots[rid].inject_perception_overload()` (suggest O). Pressing F 3 times on one robot within 60 s puts it in SAFE_STOP (until the resume command lands next). Yusuf: red `missed` slices and `deadline_miss` events now really happen. Yusuf: the `.claude` hooks call `python3` and match only the Bash tool; on Rayan's Windows laptop only `py` exists and commits go through PowerShell, so neither hook runs there (Rayan's Claude follows the rules by hand).
- **Next:** SAFE_STOP resume command, then robots follow dispatched plans.

### 2026-11-07 · rayan/timeline-contract · PR #7 Timeline contract (merged)
- **Did:** scheduler records per-robot task pieces. Overcurrent fault hook. Final state list.
- **Contract changes:** telemetry gains `tasks`: per robot, `[{name,start,dur,missed}]` over the last 100 ms (0 to 100), sorted, never overlapping. A preempted task appears as several pieces. Names: safety, motion, comms, mapping, perception, battery. Telemetry also gains `wheel_a` (wheel current, amps).
- **Heads-up for others:** Yusuf's timeline strip builds against this. It's on main now.
- **Next:** robots follow dispatched zones and no-go areas.

### 2026-11-07 · rayan/replan · PR #6 Lost link polish and visible replanning
- **Did:** `link_lost` / `link_restored` fire once per outage (`link_restored` carries `dark_s`). After reconnecting, a robot holds until its outbox drains (at most 10 s). The path check catches rubble near waypoints. New REPLANNING state: stop 0.6 s, replan, resume. No route for 10 s raises TRAPPED plus a priority-1 fault bundle.
- **Contract changes:** new state `REPLANNING`, new fault `TRAPPED`, `replan` events carry `reason`, `link_restored.dark_s`.
- **Heads-up for others:** the R key (drop rubble) now shows a visible replan.
- **Next:** timeline contract.

### 2026-11-07 · rayan/relays · PR #5 Relays, A* return home, shielded survivor cage
- **Did:** robots auto-drop relays when the best upstream link is between -81 and -76 dBm, at least 4 m from other relays, never in no-go areas. 2 per robot (about 4 in a 3-robot run). The return-home cost uses A* path length. Frontier clusters go down to 2 cells.
- **Contract changes:** `relays_left` in telemetry is real. `relay_dropped` event `{kind, id:"RL1", pos:[x,y], owner}`. **Floorplan:** S1 moved to (36, 27) inside metal room E2 "Steel Storage Cage", door at (38.8, 21).
- **Heads-up for others:** two of Aziz's tests moved off the old S1 spot (approved). Anything with S1 coordinates hardcoded must update.
- **Next:** replanning.

### 2026-11-07 · rayan/multi-robot · PR #3 Share frontier targets through telemetry
- **Did:** telemetry carries the robot's target. Robots avoid frontiers within 4 m of a higher-priority robot's claim (R1 > R2 > R3). Deploy is staggered 1.5 s.
- **Contract changes:** telemetry `target` field.
- **Heads-up for others:** TEMPORARY shim in `sim.py` copies telemetry into peer inboxes. Aziz replaces it with DTN-delivered peer bundles.
- **Next:** relays.

### 2026-11-07 · main · Starter + PLAN.md
- **Did:** sim server, robot exploration, 3D split view starter, `docs/PLAN.md` (idea, roles, setup, git workflow), CLAUDE.md.
- **Contract changes:** initial message shapes in `docs/PLAN.md`.
- **Heads-up for others:** none
- **Next:** multi-robot.
