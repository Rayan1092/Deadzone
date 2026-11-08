"""Registered local buildings and validated, opt-in disaster timelines."""
import json
import math
from pathlib import Path

from pydantic import Field, ValidationError

from .command.controls import director_adapter
from .command.plan import Model, PlanError
from .floorplan import FloorPlan

FLOORPLAN_DIR = Path(__file__).resolve().parents[2] / "data" / "floorplans"


class ResetScenario(Model):
    floorplan: str | None = Field(default=None, min_length=1, max_length=160, strict=True)
    timeline: bool | None = Field(default=None, strict=True)


class ScenarioTimeline:
    def __init__(self, data, robots, enabled):
        self.events, self.next = [], 0
        self.played, self.failed = 0, 0
        if not enabled:
            return
        raw = data.get("timeline", [])
        if not isinstance(raw, list) or len(raw) > 256:
            raise ValueError("Timeline must have at most 256 events")
        for index, event in enumerate(raw):
            if not isinstance(event, dict) or not {"t", "do"} <= event.keys():
                raise ValueError("Timeline events need t and do")
            t = event["t"]
            if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 0 <= t <= 86400:
                raise ValueError("Timeline time must be finite simulation seconds from 0 to 86400")
            if event["do"] not in ("rubble", "overcurrent", "aftershock"):
                raise ValueError("Unsupported timeline action")
            request = director_adapter.validate_python({"type": event["do"], **{
                k: v for k, v in event.items() if k not in {"t", "do", "label"}}})
            if request.type == "overcurrent" and request.robot not in robots:
                raise ValueError("Timeline references an undeployed robot")
            if getattr(request, "relay", None) is not None:
                raise ValueError("Timeline cannot reference a relay before deployment")
            at = getattr(request, "at", None)
            if at is not None and not (0 <= at[0] < data["size"][0] and 0 <= at[1] < data["size"][1]):
                raise ValueError("Timeline position is outside the building")
            self.events.append((float(t), index, request))
        self.events.sort(key=lambda item: item[:2])

    def apply_due(self, sim):
        while self.next < len(self.events) and self.events[self.next][0] <= sim.time + 1e-6:
            t, _, request = self.events[self.next]
            try:
                if request.type == "rubble":
                    sim.drop_rubble(request.at, request.size)
                elif request.type == "overcurrent":
                    sim.inject_overcurrent(request.robot, request.duration_s)
                else:
                    sim.earthquake(request.strength, request.at, request.relay)
            except ValueError as error:
                # An intervening manual action can make a previously valid disaster unavailable.
                # Report the failed attempt once instead of stopping the simulation loop.
                sim.events.append({"kind": "timeline_event_failed", "action": request.type,
                                   "scheduled_t": t, "reason": str(error)})
                self.failed += 1
            else:
                self.played += 1
            self.next += 1


def registered_floorplans():
    root = FLOORPLAN_DIR.resolve()
    return {p.relative_to(root).with_suffix("").as_posix(): p
            for p in sorted(root.rglob("*.json"))
            if p.resolve().is_relative_to(root) and not any(part.startswith(".") for part in p.relative_to(root).parts)}


def prepare_scenario(identifier, robots, timeline=False, *, allow_aftershock=False):
    # Accept the original startup proposal's repo-relative path as well as the public ID.
    identifier = identifier.replace("\\", "/")
    if identifier.startswith("data/floorplans/"):
        identifier = identifier[len("data/floorplans/"):]
    if identifier.endswith(".json"):
        identifier = identifier[:-5]
    path = registered_floorplans().get(identifier)
    if path is None:
        raise PlanError("floorplan_not_found", "Choose a registered floorplan ID from /api/scenarios", 404)
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("Floorplan is too large")
        data = json.loads(path.read_text(encoding="utf-8"))
        width, height = data["size"]
        cell = data["cell"]
        if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in (width, height, cell)) or not 0 < width <= 200 or not 0 < height <= 200
                or not .05 <= cell <= 2 or width * height / cell ** 2 > 1_000_000):
            raise ValueError("Unsupported floorplan dimensions")
        FloorPlan(data)  # validate geometry/material references before replacing the running world
        player = ScenarioTimeline(data, robots, timeline)
        if not allow_aftershock and any(r.type == "aftershock" for _, _, r in player.events):
            raise PlanError("feature_disabled", "Enable DZ_AFTERSHOCK=1 for this disaster timeline", 409)
    except PlanError:
        raise
    except (OSError, ValueError, KeyError, TypeError, OverflowError, ValidationError) as error:
        raise PlanError("invalid_scenario", "Invalid floorplan or disaster timeline", 422) from error
    return identifier, path, player


def scenario_catalog():
    result = []
    for identifier, path in registered_floorplans().items():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result.append({"id": identifier, "name": str(data.get("name", identifier))})
        except (OSError, ValueError):
            continue
    return result
