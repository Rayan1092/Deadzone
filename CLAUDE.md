# Deadzone, notes for Claude Code

24 hour hackathon project (UB Hacking 2026). Speed matters but main must always run.

## Read first
- `docs/PLAN.md` is the full build plan: data formats, WebSocket protocol, algorithms, hour by hour plan.
- Message shapes in `docs/PLAN.md` sections "Data formats" and "APIs and WebSocket protocol" are the contract between server and web. Do not change a message shape without saying so in the PR description.

## Ownership (ask before editing someone else's area)
- Rayan: `server/deadzone/robot/`, `ml/`, `data/floorplans/`
- Person 2: `server/deadzone/sim.py`, `app.py`, `floorplan.py`, `network/`, `command/`
- Person 3: `web/`

## Rules
- Robot code only touches the world through the `io` object passed to `Robot.step`. Never import or read `Sim` or the truth grid from robot code.
- The command post view only changes from delivered bundles. Never copy truth into it.
- Keep the sim deterministic for a given seed.
- Run `cd server && python -m pytest -q` before every PR. Run `cd web && npm run build` if you touched web.
- Small commits, short-lived branches named `name/feature`, PR into `main`.

## Commands
- Server: `cd server && DZ_AUTOSTART=1 uvicorn deadzone.app:app --host 0.0.0.0 --port 8000 --reload`
- Web: `cd web && npm run dev` then open http://localhost:5173
- Tests: `cd server && python -m pytest -q`
