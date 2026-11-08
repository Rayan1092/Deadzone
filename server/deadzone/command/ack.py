"""Validated robot acknowledgements, published only after actual bundle delivery."""
from typing import Literal

from pydantic import Field, model_validator

from .plan import Identifier, Model, Number

Action = Literal["explore_zone", "go_to", "return_home", "hold", "resume"]
Status = Literal["accepted", "refused", "completed"]
STATUS_ORDER = {"accepted": 0, "refused": 1, "completed": 2}


class CommandAck(Model):
    cmd_id: Identifier
    robot: Identifier
    cmd: str = Field(min_length=1, max_length=64, strict=True)
    status: Status
    eta_s: Number | None = Field(default=None, ge=0)
    reason: Literal["low_battery", "battery_reserve", "fault", "safe_stop", "no_route",
                    "outside_building", "no_go", "bad_command"] | None = None
    say: str = Field(min_length=1, max_length=500, strict=True)
    state: Identifier
    t: Number = Field(ge=0)
    issued_t: Number | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def unknown_commands_only_refused(self):
        if self.cmd not in ("explore_zone", "go_to", "return_home", "hold", "resume") and not (
                self.status == "refused" and self.reason == "bad_command"):
            raise ValueError("Unsupported commands may only be refused")
        return self
