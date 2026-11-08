# Deadzone asset pack

CC0 assets for the realistic look, compressed for the web (about 23 MB, plus 23 MB of plain
JPG/PNG copies in `plain/` for a loader without KTX2 support, see below). Everything is
CC0 1.0. Sources needed no login: Poly Haven (textures, HDRI) and Poly Pizza (CC0 models only).
The robot and the crack and stain decals are procedural (our own work, CC0).
Per-file credits: `CREDITS.md`. Machine-readable list: `manifest.json` (path, bytes, format,
codec, colour space, size, triangles, node names, credit).

Kept outside `web/` on purpose. To use a file, copy it into `web/public/assets/`.

## Contents

| Folder | What | Format |
|---|---|---|
| `textures/<set>/<set>_{color,normal,roughness}.ktx2` | cracked_concrete_floor, cracked_concrete_wall, damaged_plaster, brick (2K); dusty_tiles, rusted_metal (1K) | KTX2: color ETC1S sRGB, roughness ETC1S linear, normal UASTC + zstd linear, all with mipmaps |
| `decals/*.ktx2` | crack_01..03, stain_water_01, stain_soot_01 (1K, with alpha) | KTX2 ETC1S sRGB + alpha, mipmaps |
| `hdri/sky_overcast.hdr` | Overcast Industrial Courtyard, 1K | Radiance HDR |
| `models/robot.glb` | Tracked rescue robot, 1508 tris | GLB, meshopt + quantized |
| `models/person.glb` | Adult lying on its back, arms out, 3928 tris, KTX2 texture | GLB, meshopt + quantized |

## Plain copies (no KTX2 loader needed)

`plain/` holds uncompressed copies of three sets in the `web/public/assets/textures/<set>/{diff,nor_gl,rough}.jpg`
layout Yusuf's loader already uses: `cracked_concrete_wall`, `cracked_concrete_floor`, `damaged_plaster`
(2K JPG straight from Poly Haven: `diff` sRGB, `nor_gl` OpenGL +Y normal, `rough` linear), and the five
decals as 1K RGBA PNG in `plain/decals/`. Copy `plain/textures/*` into `web/public/assets/textures/`.
Listed under `plain` in `manifest.json`; same credits as the KTX2 files.

## Conventions

- 1 unit = 1 m, Y up. Models' origin is at floor center (the model sits on y = 0).
- Robot faces +X. Named nodes: `body`, `track_L`, `track_R`, `mast`, `lidar`, `antenna`,
  `headlight` (emissive), `led_status` (green), `led_link` (blue). Size 0.74 x 0.68 x 0.61 m.
- Person: lying on its back, head toward +X, arms out along Z, 1.75 m long. No debris
  (add rubble around it in the scene). Root node `person`.
- Normal maps use the OpenGL (+Y) convention, which is what three.js expects.
- Texture colour spaces: `color` and decals are sRGB, `normal` and `roughness` are linear.

## Loading in three.js

```js
import { KTX2Loader } from "three/examples/jsm/loaders/KTX2Loader.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { RGBELoader } from "three/examples/jsm/loaders/RGBELoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";

// copy node_modules/three/examples/jsm/libs/basis/ to web/public/basis/
const ktx2 = new KTX2Loader().setTranscoderPath("/basis/").detectSupport(renderer);
const gltf = new GLTFLoader().setKTX2Loader(ktx2).setMeshoptDecoder(MeshoptDecoder);

const tex = await ktx2.loadAsync("/assets/textures/brick/brick_color.ktx2");
tex.colorSpace = THREE.SRGBColorSpace;          // only for color maps and decals
tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
const robot = (await gltf.loadAsync("/assets/models/robot.glb")).scene;
const sky = await new RGBELoader().loadAsync("/assets/hdri/sky_overcast.hdr");
sky.mapping = THREE.EquirectangularReflectionMapping;
```

With react-three-fiber, `useKTX2(url, "/basis/")` and `useGLTF(url, true, true)` from drei do
the same job.

## Rebuilding

Two steps. Step 1 downloads the sources and makes the procedural assets. Step 2 compresses them.

```powershell
py -m pip install numpy pillow trimesh
py assets-pack/_build/fetch_and_make.py $env:TEMP/dz-pack          # raw inputs + credits.json
mkdir $env:TEMP/dz-tools; cd $env:TEMP/dz-tools; npm init -y
npm i ktx2-encoder@0.6.0 sharp@0.33.5 @gltf-transform/core@4.1.1 @gltf-transform/extensions@4.1.1 @gltf-transform/functions@4.1.1 meshoptimizer@0.22.0
copy <repo>/assets-pack/_build/build.mjs .
node build.mjs $env:TEMP/dz-pack <repo>/assets-pack          # writes KTX2/GLB/HDR + manifest + CREDITS
py -I <repo>/assets-pack/_build/plain.py $env:TEMP/dz-pack <repo>/assets-pack   # step 3: plain/ copies
```

The build is deterministic for the procedural parts (fixed seeds). The texture encode takes a
few minutes.
