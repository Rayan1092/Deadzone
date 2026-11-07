# Deadzone

Rescue robots that keep searching where the signal dies. Built at UB Hacking 2026.

Robots explore a collapsed building on their own. When they lose radio they keep going, find survivors, then come back to signal and report. The big screen shows two views side by side. Left is what really happened. Right is only what the command post knows.

## Run it

You need Python 3.11+ and Node 20+.

Server (terminal 1):

```
cd server
pip install -r requirements.txt
DZ_AUTOSTART=1 uvicorn deadzone.app:app --host 0.0.0.0 --port 8000 --reload
```

Web (terminal 2):

```
cd web
npm install
npm run dev
```

Open http://localhost:5173. Space starts and pauses. Backspace resets. + and - change speed. R drops rubble in front of robot 1.

On Windows PowerShell set env vars like this: `$env:DZ_AUTOSTART=1` then run uvicorn on the next line.

Tests:

```
cd server
python -m pytest -q
```

## Settings

- `DZ_ROBOTS` number of robots (default 1)
- `DZ_SPEED` sim speed (default 2)
- `DZ_SEED` random seed (default 7)
- `DZ_AUTOSTART=1` start the sim right away

## Layout

- `server/deadzone/robot/` robot software. Lidar, mapping, frontier search, A*, lost link
- `server/deadzone/network/` radio model and store and forward
- `server/deadzone/command/` what the command post knows
- `server/deadzone/sim.py` the tick loop and the world
- `server/deadzone/app.py` FastAPI and WebSockets
- `web/src/three/` the 3D scene
- `web/src/panels/` top bar and sidebar
- `data/floorplans/` the building

The full plan is in `docs/PLAN.md`. The phone planning API and robot integration
contract are in [`docs/PHONE-PLANNING.md`](docs/PHONE-PLANNING.md).
