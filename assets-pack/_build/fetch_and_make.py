"""Step 1 of the asset pack build: download the CC0 sources and make the procedural assets.

    py assets-pack/_build/fetch_and_make.py <work dir>

Writes raw inputs into <work dir>/raw/ (JPG/PNG/HDR/GLB). Step 2 (build.mjs) compresses them
into assets-pack/. Only CC0 sources that need no login: Poly Haven and Poly Pizza (CC0
models only). Procedural assets (robot, crack and stain decals) are made here and are CC0 (Deadzone team).
"""
import io
import json
import math
import random
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

UA = {"User-Agent": "deadzone-asset-pack/1.0"}

# Poly Haven texture sets: (pack name, Poly Haven id, resolution). 2k only for floor and walls.
TEXTURES = [
    ("cracked_concrete_floor", "concrete_floor_damaged_01", "2k"),
    ("cracked_concrete_wall", "concrete_wall_008", "2k"),
    ("damaged_plaster", "damaged_plaster", "2k"),
    ("brick", "brick_wall_02", "2k"),
    ("dusty_tiles", "dirty_tiles", "1k"),
    ("rusted_metal", "rust_coarse_01", "1k"),
]
MAPS = {"color": "Diffuse", "normal": "nor_gl", "roughness": "Rough"}
HDRI = ("overcast_industrial_courtyard", "1k")
PERSON = {"id": "nbLBTJMg0b", "title": "Man", "author": "Polygonal Mind",
          "glb": "https://static.poly.pizza/ebb63435-0167-402e-9eb2-541e43599d6e.glb"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def poly_haven(raw, credits):
    for name, pid, res in TEXTURES:
        info = json.loads(get(f"https://api.polyhaven.com/info/{pid}"))
        files = json.loads(get(f"https://api.polyhaven.com/files/{pid}"))
        for slot, key in MAPS.items():
            url = files[key][res]["jpg"]["url"]
            (raw / f"{name}_{slot}.jpg").write_bytes(get(url))
        credits.append({"name": name, "kind": "texture", "source": "Poly Haven",
                        "url": f"https://polyhaven.com/a/{pid}", "title": info["name"],
                        "author": ", ".join(info.get("authors", {})), "license": "CC0 1.0", "resolution": res})
    pid, res = HDRI
    info = json.loads(get(f"https://api.polyhaven.com/info/{pid}"))
    files = json.loads(get(f"https://api.polyhaven.com/files/{pid}"))
    (raw / "sky_overcast.hdr").write_bytes(get(files["hdri"][res]["hdr"]["url"]))
    credits.append({"name": "sky_overcast", "kind": "hdri", "source": "Poly Haven",
                    "url": f"https://polyhaven.com/a/{pid}", "title": info["name"],
                    "author": ", ".join(info.get("authors", {})), "license": "CC0 1.0", "resolution": res})


def stain_decals(raw, credits, size=1024):
    """Procedural stain decals (CC0, our own work): a water stain and a soot mark, RGBA."""
    yy, xx = np.mgrid[0:size, 0:size] / size
    for k, (name, rgb, seed) in enumerate([("stain_water_01", (92, 74, 52), 7), ("stain_soot_01", (22, 20, 19), 11)]):
        rng = np.random.default_rng(seed)
        r = np.hypot(xx - 0.5, (yy - 0.5) * (1.6 if k == 0 else 1.0))
        noise = np.zeros((size, size))
        for octave in range(5):                     # value noise from upsampled random grids
            n = 4 * 2 ** octave
            g = rng.random((n + 1, n + 1))
            noise += np.asarray(Image.fromarray(np.uint8(g * 255)).resize((size, size), Image.BICUBIC)) / 255 / 2 ** octave
        noise /= noise.max()
        edge = 0.32 + 0.12 * (noise - 0.5)
        a = np.clip((edge - r) / 0.06, 0, 1) * (0.55 + 0.45 * noise)
        if k == 0:                                  # tide line at the rim of a water stain
            a = np.maximum(a * 0.6, np.exp(-((r - edge) / 0.012) ** 2) * 0.85)
        img = np.zeros((size, size, 4), np.uint8)
        img[..., :3] = rgb
        img[..., 3] = np.uint8(np.clip(a, 0, 1) * 230)
        Image.fromarray(img, "RGBA").save(raw / f"{name}.png")
        credits.append({"name": name, "kind": "decal", "source": "procedural (fetch_and_make.py)",
                        "url": None, "title": name.replace("_", " "), "author": "Deadzone team",
                        "license": "CC0 1.0", "resolution": "1k"})


def crack_decals(raw, credits, n=3, size=1024):
    """Procedural crack decals (CC0, our own work): branching dark lines on transparent."""
    for k in range(n):
        rng = random.Random(100 + k)
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        def crack(x, y, ang, length, width, depth):
            steps = int(length / 6)
            for _ in range(steps):
                ang += rng.uniform(-0.45, 0.45)
                nx, ny = x + math.cos(ang) * 6, y + math.sin(ang) * 6
                d.line([(x, y), (nx, ny)], fill=(18, 16, 14, int(220 * min(1, width / 3))), width=max(1, int(width)))
                x, y = nx, ny
                width *= 0.985
                if depth < 3 and rng.random() < 0.035:
                    crack(x, y, ang + rng.choice([-1, 1]) * rng.uniform(0.5, 1.1), length * 0.45, width * 0.7, depth + 1)
        for _ in range(rng.randint(2, 3)):
            crack(size / 2 + rng.uniform(-60, 60), size / 2 + rng.uniform(-60, 60), rng.uniform(0, 2 * math.pi),
                  rng.uniform(380, 520), rng.uniform(3.5, 5.5), 0)
        a = img.split()[3].filter(ImageFilter.GaussianBlur(0.8))
        img.putalpha(a)
        img.save(raw / f"crack_{k + 1:02d}.png")
        credits.append({"name": f"crack_{k + 1:02d}", "kind": "decal", "source": "procedural (fetch_and_make.py)",
                        "url": None, "title": f"Crack decal {k + 1}", "author": "Deadzone team",
                        "license": "CC0 1.0", "resolution": "1k"})


def robot(raw, credits):
    """Tracked rescue robot, procedural, faces +X, 1 unit = 1 m, Y up, origin at floor center.
    Named nodes: body, track_L, track_R, mast, lidar, antenna, headlight, led_status, led_link."""
    import trimesh
    from trimesh.visual.material import PBRMaterial

    def mat(rgb, metal=0.1, rough=0.6, emissive=None):
        m = PBRMaterial(baseColorFactor=[*rgb, 1.0], metallicFactor=metal, roughnessFactor=rough,
                        emissiveFactor=emissive)
        return trimesh.visual.TextureVisuals(material=m)

    def place(mesh, x, y, z):
        mesh.apply_translation([x, y, z])
        return mesh

    def track(z):
        parts = [trimesh.creation.box([0.62, 0.12, 0.12])]
        for x in (-0.31, 0.31):
            c = trimesh.creation.cylinder(radius=0.06, height=0.12, sections=20)
            c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
            parts.append(place(c, x, 0, 0))
        for x in np.linspace(-0.28, 0.28, 8):               # grousers on the belt
            parts.append(place(trimesh.creation.box([0.02, 0.135, 0.13]), x, 0.0, 0))
        t = trimesh.util.concatenate(parts)
        return place(t, 0, 0.06, z)

    orange, dark, steel = (0.93, 0.42, 0.13), (0.12, 0.12, 0.13), (0.55, 0.57, 0.6)
    scene = trimesh.Scene()
    nodes = {
        "body": (place(trimesh.creation.box([0.6, 0.18, 0.36]), 0, 0.21, 0), mat(orange, 0.2, 0.5)),
        "track_L": (track(0.24), mat(dark, 0.0, 0.9)),
        "track_R": (track(-0.24), mat(dark, 0.0, 0.9)),
    }
    mast = trimesh.creation.cylinder(radius=0.02, height=0.3, sections=16)
    mast.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    nodes["mast"] = (place(mast, -0.12, 0.45, 0), mat(steel, 0.8, 0.35))
    lidar = trimesh.creation.cylinder(radius=0.06, height=0.07, sections=32)
    lidar.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    nodes["lidar"] = (place(lidar, -0.12, 0.635, 0), mat((0.08, 0.08, 0.09), 0.3, 0.3))
    ant = trimesh.creation.cylinder(radius=0.006, height=0.35, sections=8)
    ant.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    nodes["antenna"] = (place(ant, -0.26, 0.475, -0.12), mat(dark, 0.5, 0.5))
    head = trimesh.creation.cylinder(radius=0.035, height=0.03, sections=24)
    head.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 0, 1]))
    nodes["headlight"] = (place(head, 0.31, 0.24, 0), mat((1, 1, 0.95), 0.0, 0.2, emissive=[1.0, 0.97, 0.85]))
    nodes["led_status"] = (place(trimesh.creation.icosphere(subdivisions=2, radius=0.015), 0.2, 0.305, 0.1),
                           mat((0.1, 0.9, 0.4), 0.0, 0.3, emissive=[0.1, 0.9, 0.4]))
    nodes["led_link"] = (place(trimesh.creation.icosphere(subdivisions=2, radius=0.015), 0.2, 0.305, -0.1),
                         mat((0.2, 0.5, 1.0), 0.0, 0.3, emissive=[0.2, 0.5, 1.0]))
    tris = 0
    for name, (mesh, vis) in nodes.items():
        mesh.visual = vis
        tris += len(mesh.faces)
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    (raw / "robot.glb").write_bytes(scene.export(file_type="glb"))
    credits.append({"name": "robot", "kind": "model", "source": "procedural (fetch_and_make.py)", "url": None,
                    "title": "Tracked rescue robot", "author": "Deadzone team", "license": "CC0 1.0",
                    "triangles": tris, "nodes": list(nodes)})


def person(raw, credits):
    (raw / "person_src.glb").write_bytes(get(PERSON["glb"]))
    credits.append({"name": "person", "kind": "model", "source": "Poly Pizza",
                    "url": f"https://poly.pizza/m/{PERSON['id']}", "title": PERSON["title"],
                    "author": PERSON["author"], "license": "CC0 1.0",
                    "note": "laid on its back along +X (pose by rotation), origin at floor center"})


def main():
    work = Path(sys.argv[1])
    raw = work / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    credits = []
    poly_haven(raw, credits)
    stain_decals(raw, credits)
    crack_decals(raw, credits)
    robot(raw, credits)
    person(raw, credits)
    (work / "credits.json").write_text(json.dumps(credits, indent=1), encoding="utf-8")
    print(f"raw assets in {raw}: {len(list(raw.iterdir()))} files")


if __name__ == "__main__":
    main()
