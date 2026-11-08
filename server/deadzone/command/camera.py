"""Normalize delivered thermal observations, never reconstruct a live sensor view."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .plan import Identifier, Number, Point
from ..thermal import thermal_metadata

Crop = Annotated[str, Field(strict=True, max_length=128, pattern=r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*\.png$")]


class CameraHit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Identifier
    pos: Point
    verdict: Literal["person", "rejected", "unsure"]
    conf: Number | None = Field(default=None, ge=0, le=1)
    crop: Crop | None = None


class CameraFrame(BaseModel):
    model_config = ConfigDict(extra="ignore")
    t: Number = Field(ge=0)
    hits: list[CameraHit] = Field(max_length=64)


def delivered_frame(raw, created, arrived, size, *, heat_sources=False):
    try:
        frame = CameraFrame.model_validate(raw)
    except ValidationError:
        return None
    if frame.t > created + 1e-6 or created > arrived + 1e-6:
        return None
    if any(not (0 <= x <= size[0] and 0 <= y <= size[1]) for x, y in (hit.pos for hit in frame.hits)):
        return None
    result = frame.model_dump(mode="json") | {"delivered_t": created, "reported_t": arrived}
    if heat_sources and isinstance(raw, dict):
        for hit, original in zip(result["hits"], raw.get("hits", [])):
            hit.update(thermal_metadata(original))
    return result
