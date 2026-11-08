"""Per-viewer reductions; never alters simulation ticks, maps or events."""
import json


class LiteScreen:
    def __init__(self):
        self.ticks = 0

    def transform(self, message, *, initial=False):
        frame = json.loads(message)
        if frame["t"] == "hello":
            self.ticks = 0
            frame["data"]["screen_profile"] = {"lite": True, "tick_stride": 2, "lidar_max_points": 0}
        elif frame["t"] == "tick":
            if not initial:
                self.ticks += 1
                if self.ticks % 2:
                    return None
            for robot in frame["data"]["reality"]["robots"]:
                robot["lidar"] = []
        else:
            return message
        return json.dumps(frame, separators=(",", ":"))
