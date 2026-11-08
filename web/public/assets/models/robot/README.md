# Rescue robot model (`robot.glb`)

Drop the tracked rescue robot here as **`robot.glb`** and every robot in the app picks it up
on the next page load: the 3D map, Command's ghosts and the robot's-eye camera
(`web/src/three/RoverModel.jsx`). Nothing else needs to change. While the file is missing, or
if it fails to load, the app draws the procedural rover from `Rover.jsx`, so the demo never
breaks on a bad export: check the browser console for `[RoverModel]` if the model does not
show up.

Served at `/assets/models/robot/robot.glb` (Vite copies `web/public/` into `dist/`).

## License

CC0 or CC-BY only. Add a row to `web/public/assets/CREDITS.md` with the asset name, link,
author(s) and license (CC-BY needs the author credited by name), and keep any license file
that came with the download next to it in this folder.

## File

| | |
| --- | --- |
| Format | glTF 2.0 binary (`.glb`), textures embedded. Uncompressed or meshopt (`EXT_meshopt_compression`). Avoid Draco: its decoder is fetched from Google's CDN at runtime and the demo laptop may be offline |
| Triangles | target 15-30k, hard max 50k (up to 4 robots are on screen, plus the robot camera's copy) |
| Meshes / materials | as few as possible, ideally <= 10 meshes (one draw call each, per robot) |
| Textures | PBR metal/roughness, 1K or smaller, whole file <= ~8 MB |
| Forward | **+X**. The sim's yaw spins the robot around Y and the nose must point along +X. This is the one thing the loader cannot measure, so get it right (Blender: the robot faces +X in Blender, export with "+Y up") |
| Up | +Y |
| Origin | floor center: on the ground, in the middle of the footprint |
| Units | 1 unit = 1 m. The loader rescales so the longest horizontal extent is 0.56 m and re-centers the origin anyway, so proportions matter more than absolute size |
| Shadows | not needed; robots draw without shadows |
| Animations | ignored; the lidar spin is driven by the app |

A real tracked USAR robot (Packbot / Talon class) is about 0.55-0.9 m long and 0.4-0.5 m
wide. The app draws it 1.8x larger so robots read on a projector; the lidar mast, headlights
and antenna should still be clearly recognisable at thumbnail size.

## Node names (case-insensitive; mesh name or material name both work)

| Name | Used for |
| --- | --- |
| `lidar` | the spinning sensor head on the mast. The whole node spins around the robot's up axis, so make it a single node that is round around its own center |
| `led*` (e.g. `led_left`, `led_ring`) | status LEDs / light strips: tinted and made emissive in the robot's color (teal, amber, violet per robot) |
| `paint*` or `body*` | panels painted in the robot's color (deck panel, flank stripes). Keep the base color light grey so the tint reads |
| `headlight*` | front lamps: white emissive |
| `antenna_tip` | the ball on the radio whip: green while the radio link is up, red when it is down |
| `tag*` (optional) | a small flat quad on each flank, UV-mapped 0..1: receives the robot's id as a decal. Without it the app places two 9 x 4.5 cm stickers on the flanks |

Everything else keeps its own materials. Materials are cloned per robot before tinting, so
the file can share one material across robots freely.

## Checking the export

1. Put `robot.glb` in this folder, reload the app (`cd web && npm run dev`).
2. The three robots at the entry should face the way they drive (nose toward their first
   waypoint). If they drive sideways, the model does not face +X.
3. Press V on a robot card: the other robots in that camera should be the same model.
4. The lidar head spins, the LEDs match each robot's color, the whip tip is green.
5. Press K (night): the headlights should glow.
