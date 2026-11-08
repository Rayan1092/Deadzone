"""Opt-in observer optimization; never changes simulation or Command knowledge."""
import base64
from copy import deepcopy
import json
import time
import zlib

GRID_KEYS = ("reality", "command", "belief", "belief_command")
SCREEN_HZ = 15
LIDAR_POINTS = 24


def stream_profile(compact=False):
    return {"compact_available": True, "map_encoding": "zlib-base64" if compact else "base64",
            "screen_hz": SCREEN_HZ, "lidar_max_points": LIDAR_POINTS}


def thin_tick(snapshot):
    robots = []
    for robot in snapshot["reality"]["robots"]:
        points = robot.get("lidar", [])
        if len(points) > LIDAR_POINTS:
            points = [points[i * (len(points) - 1) // (LIDAR_POINTS - 1)] for i in range(LIDAR_POINTS)]
        robots.append(dict(robot, lidar=points))
    return dict(snapshot, reality=dict(snapshot["reality"], robots=robots))


def compact_message(message):
    frame = json.loads(message)
    kind, data = frame["t"], frame["data"]
    if kind == "hello":
        data["stream"] = stream_profile(True)
    elif kind == "maps":
        for key in GRID_KEYS:
            if isinstance(data.get(key), str):
                data[key] = _compress(data[key])
        data["encoding"] = "zlib-base64"
    elif kind == "cmd_view":
        data["map"] = _compress(data["map"])
        data["map_encoding"] = "zlib-base64"
    else:
        return message
    return json.dumps(frame, separators=(",", ":"))


def _compress(value):
    raw = base64.b64decode(value, validate=True)
    return base64.b64encode(zlib.compress(raw, level=1)).decode("ascii")


class StreamState:
    def __init__(self, enabled=False, clock=time.monotonic):
        self.enabled, self.clock = enabled, clock
        self.reset()

    def reset(self):
        self.last_tick = float("-inf")
        self.raw_maps = self.payload = None
        self.version = 0
        self.versions = {}
        self.sent_version = None

    def tick_due(self, force=False):
        if not self.enabled:
            return True
        now = self.clock()
        if force or now - self.last_tick >= 1 / SCREEN_HZ - 1e-9:
            self.last_tick = now
            return True
        return False

    def maps(self, data):
        if not self.enabled:
            return data
        if data != self.raw_maps:
            previous = self.raw_maps or {}
            resized = any(data.get(k) != previous.get(k) for k in ("w", "h", "cell"))
            self.version += 1
            self.versions = {
                key: self.versions.get(key, 0) + int(resized or data[key] != previous.get(key))
                for key in GRID_KEYS if key in data}
            self.raw_maps = deepcopy(data)
            self.payload = dict(data, version=self.version, versions=dict(self.versions))
        return self.payload

    def maps_due(self, data, force=False):
        if not self.enabled:
            return True
        if force or data["version"] != self.sent_version:
            self.sent_version = data["version"]
            return True
        return False
