"""Step 3 of the asset pack build: plain copies for a loader without KTX2 support.

    py -I assets-pack/_build/plain.py <work dir> <assets-pack dir>

Copies the raw Poly Haven 2K JPGs of the three sets Yusuf asked for into
<assets-pack>/plain/textures/<set>/{diff,nor_gl,rough}.jpg (the web/public/assets/textures layout:
color sRGB, normal OpenGL +Y, roughness linear) and the decal PNGs (1K RGBA) into
<assets-pack>/plain/decals/. Nothing is re-encoded. Adds a "plain" list to manifest.json.
"""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

SETS = ["cracked_concrete_wall", "cracked_concrete_floor", "damaged_plaster"]
MAPS = {"color": "diff", "normal": "nor_gl", "roughness": "rough"}
DECALS = ["crack_01", "crack_02", "crack_03", "stain_water_01", "stain_soot_01"]


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    with Image.open(dst) as im:
        return dst.stat().st_size, im.size[0], im.size[1]


def main():
    work, out = Path(sys.argv[1]), Path(sys.argv[2])
    raw, plain = work / "raw", out / "plain"
    shutil.rmtree(plain, ignore_errors=True)
    entries = []
    for s in SETS:
        for slot, name in MAPS.items():
            size, w, h = copy(raw / f"{s}_{slot}.jpg", plain / "textures" / s / f"{name}.jpg")
            entries.append({"path": f"plain/textures/{s}/{name}.jpg", "bytes": size, "kind": "texture", "set": s,
                            "map": slot, "format": "jpg", "colorSpace": "srgb" if slot == "color" else "linear",
                            "width": w, "height": h, "credit": s})
    for d in DECALS:
        size, w, h = copy(raw / f"{d}.png", plain / "decals" / f"{d}.png")
        entries.append({"path": f"plain/decals/{d}.png", "bytes": size, "kind": "decal", "format": "png",
                        "colorSpace": "srgb", "alpha": True, "width": w, "height": h, "credit": d})
    manifest = out / "manifest.json"
    m = json.loads(manifest.read_text(encoding="utf-8"))
    total = sum(e["bytes"] for e in entries)
    m["plain"] = {"note": "uncompressed copies of three texture sets and the decals for loaders without KTX2 "
                          "(same sources and credits as the KTX2 files); not counted in total_bytes",
                  "layout": "plain/textures/<set>/{diff,nor_gl,rough}.jpg mirrors web/public/assets/textures/<set>/",
                  "total_bytes": total, "files": entries}
    manifest.write_text(json.dumps(m, indent=1), encoding="utf-8")
    print(f"plain: {len(entries)} files, {total / 1e6:.1f} MB")
    for e in entries:
        print(f"{e['bytes'] / 1e6:6.2f} MB  {e['path']}  {e['width']}x{e['height']}")


if __name__ == "__main__":
    main()
