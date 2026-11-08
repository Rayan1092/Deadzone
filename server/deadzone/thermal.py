"""Opt-in heat-source inputs and sampled-hit metadata; no world access from robots."""
import hashlib
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HEAT_TYPES = {"generator", "space_heater", "hot_pipe", "server_rack", "dog", "laptop", "sunlit"}
ID_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"


class HeatSource(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    id: str = Field(pattern=ID_PATTERN)
    type: Literal["generator", "space_heater", "hot_pipe", "server_rack", "dog", "laptop", "sunlit"]
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)
    temp_c: float = Field(allow_inf_nan=False)
    size_m: float = Field(gt=0, allow_inf_nan=False)


def heat_spots(fp, seed):
    """Compile the agreed x/y schema once per reset, without consuming any RNG.

    Existing negative runtime crops are stand-ins, as with the legacy decoys;
    they are not synthetic temperature images or new detector training data.
    """
    raw = fp.data.get("heat_sources", [])
    if not isinstance(raw, list):
        raise ValueError("heat_sources must be a list")
    ids = {item["id"] for key in ("survivors", "decoys") for item in fp.data.get(key, [])}
    spots = []
    for item in raw:
        source = HeatSource.model_validate(item)
        if source.id in ids or source.x >= fp.W or source.y >= fp.H:
            raise ValueError("Heat sources need unique IDs and centers inside the floor plan")
        ids.add(source.id)
        key = f"{seed}:{source.id}:{source.type}".encode()
        index = int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % 3 + 1
        spots.append({"id": source.id, "pos": (source.x, source.y), "kind": "decoy",
                      "type": source.type, "source_id": source.id, "temp_c": source.temp_c,
                      "thermal": f"neg_{index:04d}.png"})
    return spots


def thermal_metadata(hit):
    """Safe optional metadata from a sampled hit. Old data means survivor."""
    if not isinstance(hit, dict) or hit.get("kind", "survivor") not in ("survivor", "decoy"):
        return {}
    result = {"kind": hit.get("kind", "survivor")}
    if result["kind"] == "decoy":
        if isinstance(hit.get("type"), str) and hit["type"] in HEAT_TYPES:
            result["type"] = hit["type"]
        if isinstance(hit.get("source_id"), str) and re.fullmatch(ID_PATTERN, hit["source_id"]):
            result["source_id"] = hit["source_id"]
        temp = hit.get("temp_c")
        if type(temp) in (int, float) and math.isfinite(temp):
            result["temp_c"] = temp
    return result
