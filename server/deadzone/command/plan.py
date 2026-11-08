"""Validated phone plans and dispatch through the existing DTN transport."""
import json
import math
import os
from copy import deepcopy
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..network.dtn import make_bundle

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Point = tuple[Number, Number]
Polygon = Annotated[list[Point], Field(min_length=3, max_length=64)]
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]


def area(poly):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) / 2


def centroid(poly):
    pairs = list(zip(poly, poly[1:] + poly[:1]))
    cross = [a[0] * b[1] - b[0] * a[1] for a, b in pairs]
    divisor = 3 * sum(cross)
    return tuple(sum((a[i] + b[i]) * c for (a, b), c in zip(pairs, cross)) / divisor for i in (0, 1))


def segments_intersect(a, b, c, d):
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    def on_segment(p, q, r):
        return (min(p[0], q[0]) - 1e-9 <= r[0] <= max(p[0], q[0]) + 1e-9 and
                min(p[1], q[1]) - 1e-9 <= r[1] <= max(p[1], q[1]) + 1e-9)
    ac, ad, ca, cb = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    if ((ac > 0 > ad or ad > 0 > ac) and (ca > 0 > cb or cb > 0 > ca)):
        return True
    return any(abs(value) <= 1e-9 and on_segment(p, q, r) for value, p, q, r in (
        (ac, a, b, c), (ad, a, b, d), (ca, c, d, a), (cb, c, d, b)))


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Region(Model):
    id: Identifier
    poly: Polygon

    @field_validator("poly")
    @classmethod
    def simple_polygon(cls, poly):
        if poly[0] == poly[-1]:
            poly = poly[:-1]
        if len(poly) < 3 or area(poly) <= 1e-6:
            raise ValueError("Polygon must have positive area")
        edges = list(zip(poly, poly[1:] + poly[:1]))
        for i, (a, b) in enumerate(edges):
            if math.dist(a, b) < 1e-9:
                raise ValueError("Polygon has a repeated adjacent vertex")
            for j in range(i + 1, len(edges)):
                if j == i + 1 or (i == 0 and j == len(edges) - 1):
                    continue
                if segments_intersect(a, b, *edges[j]):
                    raise ValueError("Polygon must not intersect itself")
        return poly


class Requirements(Model):
    stairs: bool = Field(default=False, strict=True)
    rubble_height: Number = Field(default=0.0, ge=0, le=10)


class Zone(Region):
    robot: Identifier
    priority: int = Field(default=1, ge=1, le=10, strict=True)
    comms: Literal["relay", "lost_link_ok"] = "relay"
    requires: Requirements = Field(default_factory=Requirements)


class NoGo(Region):
    reason: str = Field(default="Responder no-go area", min_length=1, max_length=200)


class SearchPlan(Model):
    plan_id: Identifier
    author: Identifier
    zones: list[Zone] = Field(min_length=1, max_length=32)
    no_go: list[NoGo] = Field(default_factory=list, max_length=32)
    lost_link_budget_s: Number = Field(default=60.0, ge=0, le=900)

    @model_validator(mode="after")
    def unique_regions(self):
        ids = [r.id for r in [*self.zones, *self.no_go]]
        if len(ids) != len(set(ids)):
            raise ValueError("Zone and no-go IDs must be unique within the plan")
        return self


class PlanRef(Model):
    plan_id: Identifier


class PlanDraft(SearchPlan):
    """Drafts can contain only exclusions, or clear the last drawn region."""
    zones: list[Zone] = Field(max_length=32)
    plan_epoch: Identifier | None = Field(default=None, exclude=True)


class EpochPlanRef(PlanRef):
    plan_epoch: Identifier | None = Field(default=None, exclude=True)


class PlanError(ValueError):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.status = code, status


class PlanManager:
    """One shared draft, saved by ID. Published IDs are immutable and idempotent."""
    def __init__(self, sim, checker):
        self.sim, self.checker = sim, checker
        # Default on (Rayan, with Aziz's files authorized): a phone no-go reaches every deployed robot and
        # a robot inside a new no-go is routed out; DZ_GLOBAL_NO_GO=0 restores the legacy behaviour.
        self.global_no_go = os.environ.get("DZ_GLOBAL_NO_GO", "1") != "0"
        self.saved = {}
        self.current_id = None
        self.dispatched = set()

    def current(self):
        return deepcopy(self.saved.get(self.current_id))

    def save(self, plan):
        for region in [*plan.zones, *plan.no_go]:
            if any(not (0 <= x <= self.sim.prior.W and 0 <= y <= self.sim.prior.H) for x, y in region.poly):
                raise PlanError("invalid_plan", f"{region.id} is outside the floor plan", 422)
        data = plan.model_dump(mode="json")
        if plan.plan_id in self.dispatched and self.saved[plan.plan_id] != data:
            raise PlanError("plan_dispatched", "Use a new plan_id to change an already dispatched plan")
        self.saved[plan.plan_id] = data
        self.current_id = plan.plan_id
        return deepcopy(data)

    def get(self, plan_id):
        if plan_id not in self.saved:
            raise PlanError("plan_not_found", f"Unknown plan: {plan_id}", 404)
        return PlanDraft.model_validate(self.saved[plan_id])

    def check(self, plan_id):
        plan = self.get(plan_id)
        if not plan.zones:
            raise PlanError("empty_plan", "Add a search zone before checking or dispatching", 422)
        return self.checker.check(plan, self.sim.post, self.sim.time)

    def dispatch(self, plan_id):
        if plan_id in self.dispatched:
            return {"ok": True, "plan_id": plan_id}
        result = self.check(plan_id)  # never rely on approval from an earlier submit
        if not result["ok"]:
            return result
        plan = self.get(plan_id)
        outgoing = []
        recipients = self.sim.robot_specs if self.global_no_go else {z.robot for z in plan.zones}
        for rid in sorted(recipients):
            payload = plan.model_dump(mode="json")
            payload["zones"] = [z.model_dump(mode="json") for z in sorted(plan.zones, key=lambda z: (z.priority, z.id))
                                if z.robot == rid]
            size = len(json.dumps(payload, separators=(",", ":")).encode()) + 64
            outgoing.append(make_bundle("CMD", rid, "plan", payload, self.sim.time, size))
        self.sim.network.queues["CMD"].extend(outgoing)
        self.dispatched.add(plan_id)
        return {"ok": True, "plan_id": plan_id}
