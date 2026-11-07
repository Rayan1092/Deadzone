"""The robot-to-Command rescue route contract; no route planning or truth access."""
from typing import Annotated

from pydantic import AliasChoices, Field, TypeAdapter, model_validator

from .plan import Identifier, Model, Number, Point

legacy_path = TypeAdapter(Annotated[list[Point], Field(min_length=1, max_length=2048)])


class RescueRoute(Model):
    survivor_id: Identifier = Field(validation_alias=AliasChoices("survivor_id", "survivor"))
    by: Identifier
    t: Number = Field(ge=0)
    path: list[Point] = Field(min_length=1, max_length=60)
    length_m: Number = Field(ge=0)
    beacon_id: Identifier | None = Field(validation_alias=AliasChoices("beacon_id", "beacon"))
    clearance_m: Number | None = Field(default=None, ge=0, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def compact_legacy_straights(cls, data):
        """PR #25 samples straight corridors every 0.5 m; remove only redundant vertices."""
        if (not isinstance(data, dict) or "survivor_id" in data or "survivor" not in data
                or not isinstance(data.get("path"), list) or len(data["path"]) <= 60):
            return data
        points = legacy_path.validate_python(data["path"])
        compact = []
        for point in points:
            if compact and point == compact[-1]:
                continue
            while len(compact) > 1:
                a, b = compact[-2:]
                u = b[0] - a[0], b[1] - a[1]
                v = point[0] - b[0], point[1] - b[1]
                if u[0] * v[1] - u[1] * v[0] != 0 or u[0] * v[0] + u[1] * v[1] < 0:
                    break  # preserve corners and reversals; never invent a shortcut
                compact.pop()
            compact.append(point)
        return {**data, "path": compact}
