"""Bounded LWW-map CRDT for opt-in offline drafts, separate from dispatch."""
from copy import deepcopy
from typing import Any
from uuid import uuid4

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from .plan import Identifier, Model, Number, PlanError, Region, Requirements, SearchPlan

ZONE_FIELDS = {"robot", "poly", "priority", "comms", "requires", "deleted"}
NOGO_FIELDS = {"poly", "reason", "deleted"}
MAX_REGISTERS = 1024


class PlanOp(Model):
    client: Identifier
    counter: int = Field(strict=True, ge=1, le=2**53 - 1)
    target: str = Field(pattern=r"^(plan|zone:[A-Za-z0-9_.-]{1,64}|no_go:[A-Za-z0-9_.-]{1,64})$")
    field: str = Field(max_length=32)
    value: Any

    @model_validator(mode="after")
    def typed_value(self):
        allowed = {"lost_link_budget_s"} if self.target == "plan" else (
            ZONE_FIELDS if self.target.startswith("zone:") else NOGO_FIELDS)
        if self.field not in allowed:
            raise ValueError("Unsupported draft field")
        value = self.value
        if self.field == "deleted":
            if type(value) is not bool:
                raise ValueError("deleted must be boolean")
        elif self.field == "poly":
            self.value = Region.model_validate({"id": "region", "poly": value}).model_dump(mode="json")["poly"]
        elif self.field == "robot":
            TypeAdapter(Identifier).validate_python(value)
        elif self.field == "priority":
            if type(value) is not int or not 1 <= value <= 10:
                raise ValueError("priority must be integer 1-10")
        elif self.field == "comms":
            if value not in ("relay", "lost_link_ok"):
                raise ValueError("Unsupported comms mode")
        elif self.field == "requires":
            self.value = Requirements.model_validate(value).model_dump(mode="json")
        elif self.field == "reason":
            if not isinstance(value, str) or not 1 <= len(value) <= 200:
                raise ValueError("reason must be 1-200 characters")
        elif self.field == "lost_link_budget_s":
            TypeAdapter(Number).validate_python(value)
            if not 0 <= value <= 900:
                raise ValueError("budget must be 0-900 seconds")
        return self


class MergeBatch(Model):
    epoch: Identifier
    plan_id: Identifier
    ops: list[PlanOp] = Field(min_length=1, max_length=256)


def stamp(op):
    return op["counter"], op["client"]


class PlanSync:
    def __init__(self, manager):
        self.manager = manager
        self.docs = {}

    def invalidate(self, plan_id):
        self.docs.pop(plan_id, None)

    def seed(self, plan):
        if plan.plan_id in self.manager.dispatched:
            raise PlanError("plan_dispatched", "Use a new plan ID for offline edits")
        base = self.manager.save(plan)
        self.docs[plan.plan_id] = {"epoch": uuid4().hex, "base": base, "regs": {}}
        return self.state(plan.plan_id)

    def _state(self, doc):
        candidate = deepcopy(doc["base"])
        zones = {z["id"]: z for z in candidate["zones"]}
        no_go = {z["id"]: z for z in candidate["no_go"]}
        for (target, field), op in sorted(doc["regs"].items()):
            if target == "plan":
                candidate[field] = deepcopy(op["value"])
            else:
                kind, region_id = target.split(":", 1)
                regions = zones if kind == "zone" else no_go
                regions.setdefault(region_id, {"id": region_id})[field] = deepcopy(op["value"])
        for key, regions in (("zones", zones), ("no_go", no_go)):
            candidate[key] = [{k: v for k, v in region.items() if k != "deleted"}
                              for _, region in sorted(regions.items()) if not region.get("deleted", False)]
        issues = []
        try:
            normalized = SearchPlan.model_validate(candidate)
            for region in [*normalized.zones, *normalized.no_go]:
                if any(not (0 <= x <= self.manager.sim.prior.W and 0 <= y <= self.manager.sim.prior.H)
                       for x, y in region.poly):
                    issues.append({"loc": [region.id, "poly"], "msg": "Region outside building"})
            candidate = normalized.model_dump(mode="json")
        except ValidationError as error:
            issues = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in error.errors()]
        return {"epoch": doc["epoch"], "plan": candidate,
                "ops": [deepcopy(op) for _, op in sorted(doc["regs"].items())],
                "valid": not issues, "issues": issues}

    def state(self, plan_id):
        if plan_id not in self.docs:
            raise PlanError("sync_not_started", "Seed offline planning explicitly before syncing", 404)
        return self._state(self.docs[plan_id])

    def merge(self, batch):
        doc = self.docs.get(batch.plan_id)
        if doc is None or doc["epoch"] != batch.epoch:
            raise PlanError("sync_epoch", "Draft was replaced/reset; fetch and rebase pending edits")
        if batch.plan_id in self.manager.dispatched:
            raise PlanError("plan_dispatched", "Use a new plan ID for offline edits")
        regs = deepcopy(doc["regs"])
        for operation in batch.ops:
            op = operation.model_dump(mode="json")
            key = op["target"], op["field"]
            old = regs.get(key)
            if old and stamp(old) == stamp(op) and old["value"] != op["value"]:
                raise PlanError("sync_clock", "Reused client/counter/field for a different value")
            if old is None or stamp(op) > stamp(old):
                regs[key] = op
        if len(regs) > MAX_REGISTERS:
            raise PlanError("sync_limit", "Draft history full; explicitly reseed after all phones sync")
        proposed = dict(doc, regs=regs)
        state = self._state(proposed)
        if state["valid"]:
            self.manager.save(SearchPlan.model_validate(state["plan"]))
        self.docs[batch.plan_id] = proposed  # invalid candidates converge too, with visible issues
        return state

    def assert_valid(self, plan_id):
        if plan_id in self.docs and not self.state(plan_id)["valid"]:
            raise PlanError("plan_conflict", "Resolve the merged draft issues before checking or dispatching")
