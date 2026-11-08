"""Per-screen lossless map deltas; independent of transport and phone knowledge."""
import base64
from copy import deepcopy
import json
import struct
import zlib

from .stream import GRID_KEYS

DRAWN_LIDAR_POINTS = 36  # Actors.Lidar draws every one of the robot's 36 endpoints.


def packed(raw):
    return base64.b64encode(zlib.compress(raw)).decode("ascii")


class MapDeltaState:
    def __init__(self, epoch):
        self.reset(epoch)

    def reset(self, epoch):
        self.epoch = epoch
        self.previous = None
        self.version = 0

    def transform(self, message):
        frame = json.loads(message)
        if frame["t"] == "hello":
            frame["data"]["compact_stream"] = {
                "epoch": self.epoch, "map_encoding": "zlib-base64",
                "patch_encoding": "zlib-base64-u32le-u8", "lidar_max_points": DRAWN_LIDAR_POINTS}
        elif frame["t"] == "maps":
            result = self.maps(frame["data"])
            if result is None:
                return None
            frame["t"], frame["data"] = result
        else:
            return message
        return json.dumps(frame, separators=(",", ":"))

    def maps(self, data):
        grids = {key: base64.b64decode(data[key], validate=True)
                 for key in GRID_KEYS if isinstance(data.get(key), str)}
        metadata = deepcopy({key: value for key, value in data.items()
                             if key not in (*GRID_KEYS, "version", "versions", "encoding")})
        current = metadata, grids
        previous = self.previous
        # A new socket/incident/geometry starts with exactly one compressed keyframe.
        resized = previous is not None and (set(grids) != set(previous[1]) or
            any(metadata.get(k) != previous[0].get(k) for k in ("w", "h", "cell")))
        if previous is None or resized:
            self.version = 0
            result = "maps", {**metadata, "epoch": self.epoch, "version": 0,
                "encoding": "zlib-base64", **{key: packed(raw) for key, raw in grids.items()}}
        else:
            patches = {}
            for key, raw in grids.items():
                old = previous[1][key]
                changed = b"".join(struct.pack("<IB", i, value)
                                   for i, value in enumerate(raw) if value != old[i])
                if changed:
                    patches[key] = packed(changed)
            if not patches and metadata == previous[0]:
                return None
            base = self.version
            self.version += 1
            result = "map_patch", {**metadata, "epoch": self.epoch, "base": base,
                "version": self.version, "encoding": "zlib-base64-u32le-u8", "grids": patches}
        self.previous = current
        return result
