# Deadzone

Rescue robots that keep searching when the signal dies. Built at UB Hacking 2026.

## What it is

When a building collapses, concrete and steel kill the radio. Most rescue robots just stop when they lose their link, and the people outside go blind.

Our robots don't stop. They explore on their own, drop radio relays as they go, and keep searching in dead zones. When they find someone, they hold the report and bring it back the moment they get signal again. An AI model running on each robot checks every warm spot so a radiator never shows up as a person.

It's all simulated, so you only need a laptop. The big screen shows two views of the same building side by side:

- **Reality**: where the robots really are and what they really found.
- **Command post**: only what has actually reached the antenna over the radio. No cheating, a test fails if this side ever knows something early.

The gap between those two views is the whole point.

## The demo story

1. A judge scans a QR code and plans the search on their phone. They send Robot 2 into the north-east corner, where there's a steel storage cage. The safety checker rejects it: "that zone is a radio dead zone". They tap "Allow it to go dark" and send it.
2. Three robots drive in, map the building with lidar, and drop relays as the signal gets weak.
3. Robot 2 enters the steel cage and loses signal. The command post still shows it as a grey ghost at its last known spot.
4. Robot 2 finds a survivor in the dark. Its AI model says "person, 100%". Only the Reality side knows. It drops a beacon next to the survivor and plans the safest route in from the entrance.
5. It heads back to signal. 14 seconds later the map, the survivor and the 50 m rescue route all pop up on the command post at once.
6. We drop rubble on a robot, jam a wheel, and overload its CPU. It replans, backs off, and its safety task never misses a deadline.

Same seed every time, so the story happens on cue. The full script with timings is in [`docs/DEMO.md`](docs/DEMO.md).

## How it works

- **Robots** (`server/deadzone/robot/`): lidar mapping, frontier exploration, A\* paths, relay drop rule, lost-link behaviour, a rate monotonic task scheduler, fault protection, and rescue routes. Robot code can only touch the world through its sensors and radio. It never reads the sim's truth.
- **Network** (`server/deadzone/network/`): a radio model where every wall costs signal (metal costs the most), plus store and forward with custody, so a message is never lost, just late.
- **Command post** (`server/deadzone/command/`): only changes when a message actually arrives. It also runs the safety checker for phone plans.
- **AI survivor detector** (`ml/`): MobileNetV3-Small trained on real thermal images (FLIR street scenes plus SDT indoor scenes). 96.7% accuracy, 97.3% precision, 96.0% recall on 1,200 FLIR images it never trained on. Adding the indoor images raised accuracy on held-out people lying and sitting from 83.9% to 99.6%. The model is 6 MB and runs on the robot, so it works with no signal.
- **Big screen and phones** (`web/`): React and three.js. Phones are just a web page, so there's nothing to install.

## Run it

You need Python 3.11+ and Node 20+. On Windows use `py` where we write `python`.

Server:

```
cd server
python -m pip install -r requirements.txt
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
python -m pip install pillow
```

The torch line is optional. Without it the robots use a simple sim sensor instead of the AI model, and the decoys are turned off.

Build the web app once, then the server hosts everything on port 8000:

```
cd web
npm install
npm run build
```

Start it (PowerShell):

```
cd server
$env:DZ_ROBOTS=3; $env:DZ_SEED=7; $env:DZ_SPEED=2
python -m uvicorn deadzone.app:app --host 0.0.0.0 --port 8000
```

On macOS or Linux: `DZ_ROBOTS=3 DZ_SEED=7 DZ_SPEED=2 python -m uvicorn deadzone.app:app --host 0.0.0.0 --port 8000`.

Open http://localhost:8000. Press **Q** for the phone QR code. Phones need to be on the same Wi-Fi.

For web development, run `npm run dev` in `web/` and open http://localhost:5173.

### Keys on the big screen

| Key | What it does |
| --- | --- |
| Space | start / pause |
| Backspace | reset |
| + / - | faster / slower |
| 1, 2, 3 / 0 | follow a robot / overview |
| R | drop rubble in front of the followed robot |
| F | jam a wheel (overcurrent) |
| O | overload the robot's CPU |
| U | resume a robot from safe stop |
| G | situation briefing |
| V | robot's-eye camera |
| T | show the hidden truth on Reality |
| P | performance mode |
| Q | phone QR code |

### Settings

- `DZ_ROBOTS`: number of robots (default 1, the demo uses 3)
- `DZ_SEED`: random seed (default 7)
- `DZ_SPEED`: sim speed (default 2)
- `DZ_AUTOSTART=1`: start right away instead of paused
- `DETECTOR=sim`: skip the AI model and use the sim sensor
- `DZ_PUBLIC_URL`: the address phones should use, if the QR code points to the wrong one

### Tests

```
cd server
python -m pytest -q
```

## AI tools

We used AI coding assistants to build this, and we're saying so because MLH asks (and because it's true): **Claude Code** (Anthropic) and **OpenAI Codex** wrote and edited code alongside us, each teammate driving one session on their own laptop. The design, the demo story, what gets built and what gets cut were ours; the assistants worked inside the rules in `CLAUDE.md` and `docs/team/INSTRUCTIONS.md` (ownership per folder, tests before every PR, a history entry with every commit). The survivor detector is a model we trained ourselves (see below); Gemini only writes the command-post briefing from data the command post already has, and never drives a robot.

## Resources and licenses

**Datasets**

- **Teledyne FLIR ADAS v2 thermal dataset**: street-scene thermal images with person boxes; training data, the held-out test set (1,200 images), the judge test pool and the decoy images. Used under Teledyne's free dataset terms; nothing from it is committed to this repo.
- **SDT, Synthetic Depth & Thermal dataset** ([Zenodo 4124309](https://zenodo.org/records/4124309)), **CC BY 4.0** (the record also says non-commercial research use): we use only its real indoor split, FLIR Lepton 3.5 frames of people lying, sitting and standing plus empty rooms. 80% trains, 20% is held out; the sim's three survivors come from the held-out part. Nothing from it is committed either.

**Published numbers we lean on**

- Rappaport, *Wireless Communications: Principles and Practice*, 2nd ed., Table 4.3: partition losses (our 1 dB per furniture piece).
- Stone, W. C. (1997), *Electromagnetic Signal Attenuation in Construction Materials*, NISTIR 6055: wall losses at 2.4 GHz for the published-values benchmark.
- ITU-R Recommendation P.1238: indoor path-loss exponents at 2.4 GHz, same benchmark.
- Liu & Layland (1973): the rate-monotonic bound the robot scheduler is checked against.

**3D assets**: Poly Haven and Poly Pizza, all CC0; the full list is in `assets-pack/CREDITS.md` and `web/public/assets/CREDITS.md`.

**Code we depend on** (one line each, licenses as published by the projects)

- Python (`server/requirements.txt`): fastapi (MIT), uvicorn (BSD-3-Clause), numpy (BSD-3-Clause), pytest (MIT), httpx (BSD-3-Clause), python-dotenv (BSD-3-Clause), reedsolo (public domain). For training and slides (`ml/`): torch (BSD-3-Clause, with bundled components under their own terms), torchvision (BSD-3-Clause), Pillow (MIT-CMU), matplotlib (PSF-based matplotlib license), trimesh (MIT).
- JavaScript (`web/package.json`): react and react-dom (MIT), three (MIT), @react-three/fiber, @react-three/drei and @react-three/postprocessing (MIT), zustand (MIT), d3-delaunay (ISC), qrcode.react (ISC), vite and @vitejs/plugin-react (MIT).

Every number we say on stage, with the file it comes from, is in `docs/FACTS.md`.

## Team

- **Rayan Diya**: robots and the AI detector
- **Aziz**: sim, radio network and command post
- **Yusuf Nusrat**: big screen, phone app and 3D

More docs: [`docs/PLAN.md`](docs/PLAN.md) (the build plan), [`docs/DEMO.md`](docs/DEMO.md) (demo runbook), [`docs/DEVPOST.md`](docs/DEVPOST.md) (write-up draft).
