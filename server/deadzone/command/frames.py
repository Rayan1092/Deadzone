"""Bounded screen-rendered JPEGs, admitted only by Command's delivered knowledge."""
import base64
import binascii
from copy import deepcopy
from io import BytesIO
import time

from pydantic import BaseModel, ConfigDict, Field

from .plan import PlanError

MAX_WIDTH, MAX_HEIGHT, MAX_FPS = 320, 180, 3
CONTACT_AGE_S = 3.0  # same delivered-report gate as phone/control.js:isDark
MAX_JPEG_BYTES = 128 * 1024
MAX_BASE64 = 4 * ((MAX_JPEG_BYTES + 2) // 3)
MAX_BODY_BYTES = MAX_BASE64 + 512


class FrameUpload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    epoch: str = Field(pattern=r"^[0-9a-f]{32}$")
    t: float = Field(ge=0, allow_inf_nan=False)
    jpeg: str = Field(min_length=4, max_length=MAX_BASE64)


class PhoneFrames:
    def __init__(self, enabled, epoch, clock=time.monotonic):
        self.enabled, self.epoch, self.clock = enabled, epoch, clock
        self.latest = {}
        self.accepted_at = {}

    def capabilities(self):
        return {"phone_frames": {"epoch": self.epoch, "max_width": MAX_WIDTH,
                                "max_height": MAX_HEIGHT, "max_fps": MAX_FPS}} if self.enabled else {}

    @staticmethod
    def linked(post, rid, now):
        report = post.robots.get(rid)
        return (report is not None and report["state"] != "SHUTDOWN"
                and 0 <= now - report["sent_t"] <= CONTACT_AGE_S)

    def accept(self, rid, body, now):
        if body.epoch != self.epoch:
            raise PlanError("frame_epoch", "Frame belongs to an earlier incident", 409)
        if not 0 <= now - body.t <= CONTACT_AGE_S or body.t < self.latest.get(rid, {}).get("t", -1):
            raise PlanError("frame_time", "Frame timestamp is stale, future or out of order", 409)
        wall_time = self.clock()
        if wall_time - self.accepted_at.get(rid, -float("inf")) < 1 / MAX_FPS:
            raise PlanError("frame_rate", "At most 3 frames per second per robot", 429)
        from PIL import Image
        try:
            raw = base64.b64decode(body.jpeg, validate=True)
            if len(raw) > MAX_JPEG_BYTES:
                raise ValueError("oversize")
            with Image.open(BytesIO(raw)) as image:
                w, h = image.size
                if image.format != "JPEG" or not (0 < w <= MAX_WIDTH and 0 < h <= MAX_HEIGHT):
                    raise ValueError("dimensions or format")
                image.load()
        except (ValueError, binascii.Error, OSError, Image.DecompressionBombError):
            raise PlanError("invalid_frame", "Expected a valid base64 JPEG no larger than 320x180 / 128 KiB", 422) from None
        self.latest[rid] = {"jpeg": body.jpeg, "mime": "image/jpeg", "width": w, "height": h, "t": body.t}
        self.accepted_at[rid] = wall_time
        return {"ok": True, "robot": rid, "t": body.t}

    def view(self, rid, now):
        frame = self.latest.get(rid)
        return None if frame is None else deepcopy(frame) | {"last_seen_s": round(max(0, now - frame["t"]), 1)}
