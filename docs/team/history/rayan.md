# Rayan Diya: robots + ML

Owns `server/deadzone/robot/`, `ml/`, `data/floorplans/`. Only Rayan's sessions edit this file.

## Now
<!-- seeded 2026-11-07 ~16:30 ET from git history by Yusuf's Claude. Rayan's Claude: overwrite this on your next commit. -->
- **Working on:** unknown after PR #7. Rayan's Claude, fill this in.
- **Works on main:** frontier exploration, multi-robot target sharing, relay dropping, A* return home, lost-link behaviour, REPLANNING around rubble, TRAPPED fault, scheduler + `tasks` timeline in telemetry (PR #7)
- **In flight (not merged):** none known
- **Blocked on / need from others:** Aziz to replace the temporary peer-telemetry shim in `sim.py` (see `p2/peer-telemetry-dtn`)
- **Promises to others:** robots will follow dispatched zones and no-go areas after the scheduler task. States are final: DEPLOYING, EXPLORING, LOST_LINK_EXPLORING, RETURNING_TO_SIGNAL, RETURNING_HOME, REPLANNING, FAULT, DONE. Faults are final: null, OVERCURRENT, STUCK, LOW_BATTERY, TRAPPED, SAFE_STOP

## Log

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
