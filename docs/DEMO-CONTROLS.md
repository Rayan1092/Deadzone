# Person 2: director, thermal inputs and delivered plan status

## Director controls

Send these through `POST /api/control` or the existing screen WebSocket:

```json
{"action":"director","value":{"do":"overload","robot":"R1"}}
{"action":"director","value":{"do":"resume","robot":"R1"}}
```

For WebSocket, wrap the object as `{"t":"control","data":<object>}`. Yusuf can
bind O to overload and a resume button/key to resume for the selected robot.
Existing F/overcurrent and R/rubble controls keep their existing contracts.

Overload invokes `Robot.inject_perception_overload()` with Rayan's defaults:
400 ms perception work for 3 sim seconds. The real scheduler emits deadline misses;
safety continues running. Simulation pause pauses the countdown; reset clears it.

Resume enqueues the priority-1 `resume_command(robot, sim.time)` bundle at CMD.
The control acknowledgement means queued, not executed. A robot without a network
route remains in SAFE_STOP until the command arrives. Robot policy decides whether
to resume; commands to a robot that is not in SAFE_STOP have no effect. The existing
`resumed {robot}` event indicates execution. Reset removes queued commands.

Both controls require a valid robot ID. Missing/unknown robots or extra fields are
rejected (422 for schema errors, 404 for an unknown ID). WebSocket errors keep the
connection usable. These are director controls, not new `/api/fault` variants.

## Thermal decoys and model environment

With the trained model active, `RobotIO.thermal()` includes floorplan `decoys` along with survivors, using the
same range, forward-camera FOV and line-of-sight rules. Every hit has only
`{id,pos,crop,conf}`. Decoy labels and truth classification are not exposed to the
robot. Rayan's detector owns classification; the floorplan and robot policy are
unchanged by this backend work. Phone planning geometry excludes both survivors
and decoys.

Install the CPU inference dependencies into the server's virtual environment:

```powershell
# From the repository, with pip available in the chosen virtual environment:
.venv\Scripts\python.exe -m pip install pillow
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

This laptop's uv-managed environment has no pip module. The same packages were
installed using `uv pip install --python .venv/Scripts/python.exe`, with the CPU
index for torch/torchvision. Training tools such as matplotlib are not required
for inference.

Verify `perception.make_detector(env={}).mode == "model"` and run the model tests.
`DETECTOR=sim`, missing dependencies or a failed checkpoint load select the existing
passthrough fallback. In fallback mode the sensor emits survivors only, suppressing
decoys so a missing model cannot turn a radiator into a reported survivor. Use the
verified model environment to demonstrate real decoy classification/rejection.

## Delivered plan status

Robot entries in screen `tick.command.robots` and phone `cmd_view.robots` add
`plan_id` and `zone`, each a string or null. Before a plan is active (or with an
older sender that omits these fields), both are null.

The backend samples the robot's public telemetry when its new source report is
created, before peer fanout/byte accounting. It does not modify already queued
reports or fill Command from the current robot state at delivery time. The
CommandPost stores these fields only from a delivered report. A newer report can
clear them; an older delayed report cannot roll them back.

Phones should show this as last reported plan/zone, alongside existing `stale_s`.
An accepted dispatch is not proof of receipt or execution. The existing
`plan_applied` event and these delivered fields have different timing on purpose.
