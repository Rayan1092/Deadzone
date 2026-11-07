# Deadzone: Devpost draft

> **Notes for us, delete before submitting**
> - Only list Gemini under Built with and tick the Gemini prize if Aziz's Gemini briefing ships. Right now G gives a local summary.
> - Reed-Solomon isn't built, so it's only in "What's next". Add it back if it lands.
> - Add the demo video link, the repo link, and the 4 screenshots (split view at the S1 burst, phone safety card, scheduler strip during O, ML slide from `docs/assets/`).
> - Prize categories: Best General, Best AI/ML, Most Over Engineered, Best UI/UX (+ MLH Best Use of Gemini API only if Gemini ships).

## Tagline

Rescue robots that keep searching when the signal dies.

## Inspiration

When a building collapses, the radio dies first. Concrete and steel block the signal, and there's no GPS underground. Most rescue robots today just stop when they lose their link, and the team outside can't see anything.

The DARPA Subterranean Challenge showed a better way. The winning robots explored on their own, dropped radio relays as they went, and reported back when they reconnected. We wanted to build that idea end to end and make the gap between "what's really happening" and "what the command post knows" something you can actually see.

## What it does

Deadzone simulates three rescue robots searching a collapsed warehouse. The big screen shows two synced 3D views of the same building:

- **Reality**: where the robots are and what they found.
- **Command post**: only what has actually arrived over the radio.

Here's the demo:

1. A judge plans the search on their phone (just a web page, scan a QR code). They send Robot 2 into the north-east corner. Our safety checker rejects it because the steel cage there is a predicted radio dead zone. They tap "Allow it to go dark" and the plan goes through.
2. The robots split up the building, map it with lidar, and drop relays right before their signal breaks.
3. Robot 2 goes into the steel cage and loses signal. On the command post it turns into a grey ghost.
4. 10 seconds later it finds a survivor in the dark. The AI model on the robot says "person, 100%". Only the Reality side knows. Robot 2 drops a beacon relay next to the survivor and plans the safest route in from the entrance.
5. It drives back to signal. **14.1 seconds after the find**, the map, the survivor and a 49.7 m rescue route all appear on the command post at once.
6. Along the way the robots look at a radiator, a car engine and a coffee machine. The AI says "not a person" every time, so there are no false alarms.
7. We drop rubble in front of a robot, jam its wheel and overload its CPU. It stops, backs up, replans, and its safety task never misses a deadline.

Everything runs on a fixed seed, so the story happens on cue. Between cues the robots really are on their own.

## How we built it

**Robots.** Each robot only sees the world through its sensors (lidar, thermal camera, odometry) and its radio. It builds its own occupancy grid from lidar, picks frontiers to explore, and drives with A\*. Robots share their targets with each other so they don't all search the same room. Each robot carries 2 relays and drops one when its best upstream link falls between -81 and -76 dBm, at least 4 m from any other relay. That's before the link actually breaks. When a robot goes dark it keeps exploring for up to 60 s, or goes back to its last good spot as soon as it finds someone. Onboard there's a rate monotonic scheduler with 6 tasks (safety, motion, comms, mapping, perception, battery) at 1 ms resolution. Utilization is 0.377, under the 0.735 Liu and Layland bound. The fault protection handles wheel overcurrent, getting stuck, low battery and being trapped, and goes into safe stop after 3 faults in a minute.

**Radio and network.** Signal strength uses a multi-wall path loss model. Every wall the signal crosses costs a fixed amount by material: drywall 4 dB, brick 10, concrete 16, metal 22. Links come up above -82 dBm and drop below -88, so they don't flicker. Messages are delay-tolerant bundles with per-hop custody: a node only deletes a bundle after the next node confirms it stored it, so nothing gets lost when a link dies mid-transfer. Survivor reports go first, then faults and routes, then telemetry, then map updates. Robots never forward for each other. Only relays and phones do.

**Command post.** The command view only changes when a bundle actually arrives. We have a test that fails if it ever knows a survivor or a map cell before the bundle carrying it was delivered. The safety checker only uses what the command post knows. It predicts dead zones, battery reserve and reachability, and rejects unsafe plans with a clear reason.

**Rescue routes.** When a robot confirms a survivor it runs A\* from the entrance to the survivor on its own map. It only uses mapped open floor, never rubble or no-go areas, and keeps to the middle of corridors. The route goes to the command post as a priority-1 bundle, so responders get it the moment it arrives.

**Big screen and phones.** React, three.js and react-three-fiber. Two synced 3D panes with fog of war, lidar rays, relay links, ghost robots, survivor figures, AI detection cards, a live scheduler strip, follow cameras and a robot's-eye thermal view. Phones get the command view only, plan zones with a drag, run the safety check, and can even act as a relay.

## The ML

- **Data:** person boxes from the FLIR ADAS thermal dataset. 96 × 96 crops. Positives are people at least 20 px tall. Negatives are half object-centered (cars, bikes, buses) and half random background. 3,000 per class for training, 600 per class held out for testing.
- **Model:** MobileNetV3-Small pretrained on ImageNet, last layer swapped for person / not person, 5 epochs. The model file is 6 MB, small enough to run on the robot.
- **Results on 1,200 held-out images (threshold 0.6):** 96.2% accuracy, 96.3% precision, 96.0% recall. Confusion matrix: 576 people found, 24 missed, 578 backgrounds rejected, 22 false alarms.
- **In the sim:** every hot spot the thermal camera sees gets cropped and scored on the robot. The survivors and decoys in the building use held-out crops, so the radiator, engine and coffee machine get rejected by the real model, not by a rule. If PyTorch isn't installed the robots fall back to a simple sim sensor and the decoys turn off, so a missing library can never put a radiator on screen as a person.

## Challenges we ran into

- **Relays that never fired.** Our first relay rule waited for the signal to drop below -80 dBm. In a real-looking building the signal doesn't fade smoothly. It jumps when a wall comes between you and the antenna, so the rule almost never triggered. Worse, one relay got dropped at -83 dBm, where a new link can't even come up, so it was useless. We added a drop window (-81 to -76 dBm) so robots drop relays while a new link can still form.
- **Our features kept killing our own demo.** With 3 robots, they relayed messages for each other and nobody ever went dark. So we made robots endpoints only. Then working relays reached the survivor's room through one concrete wall. So we built a steel storage cage around the survivor and a shelf inside it. Then beacons at every survivor shifted the whole relay network and the dark moment disappeared again, so beacons now only drop in dead zones.
- **Proving the command view isn't cheating.** Robot code can only use its `io` object, and the command post only learns from delivered bundles. We wrote tests for both so we'd find out right away if anything leaked.
- **Robots skipping rooms.** A 1.2 m door seen at an angle only shows up as 2 or 3 frontier cells, and our filter ignored anything under 4. Robots walked right past the room with the survivor.
- **Three laptops, one repo.** We kept a short history file per person in the repo so everyone knew what the others had changed and what they needed.

## Accomplishments that we're proud of

- The whole loop works end to end with no fake data path. A survivor found in the dark reaches the command post only when a real bundle gets there.
- The AI runs where it would in real life, on the robot, and it rejects decoys on its own.
- 200 automated server tests, including the core story and the "command post never knows early" test.
- The demo is deterministic, so it's the same 3-minute story every time.

## What we learned

- Radio in buildings is jumpy, not smooth, and that changes everything about when to drop a relay.
- Small rules have big side effects in a multi-robot system. One extra relay in the wrong place changed what every robot did after it.
- Real-time scheduling is easier to explain when you can watch it. Seeing perception go red while safety stays on time makes rate monotonic click.

## What's next

- Multi-floor buildings.
- Running the same robot code on real ROS 2 robots. It only talks to `io`, so you'd swap the sim for real drivers.
- Reed-Solomon error correction on weak links.
- Mesh radios and real phone relays in the field.

## Built with

Python, FastAPI, numpy, PyTorch, torchvision, React, three.js, react-three-fiber, Vite, zustand.
