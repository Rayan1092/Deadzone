"""Typed inputs shared by REST faults and screen/phone control messages."""
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator

from .plan import Identifier, Model, Number, Point


class RelayPower(Model):
    on: bool = Field(strict=True)


class RelayPlace(Model):
    pos: Point


class AskQuestion(Model):
    question: str = Field(min_length=1, max_length=1000, strict=True)

    @field_validator("question")
    @classmethod
    def trim_question(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Question must not be blank")
        return value


class RubbleFault(Model):
    type: Literal["rubble"]
    at: Point
    size: Number = Field(default=1.4, ge=0.25, le=5)


class OvercurrentFault(Model):
    type: Literal["overcurrent"]
    robot: Identifier
    duration_s: Number = Field(default=1.0, ge=0.6, le=10)


FaultRequest = Annotated[RubbleFault | OvercurrentFault, Field(discriminator="type")]
fault_adapter = TypeAdapter(FaultRequest)


class OverloadControl(Model):
    type: Literal["overload"]
    robot: Identifier


class ResumeControl(Model):
    type: Literal["resume"]
    robot: Identifier


DirectorRequest = Annotated[
    RubbleFault | OvercurrentFault | OverloadControl | ResumeControl,
    Field(discriminator="type"),
]
director_adapter = TypeAdapter(DirectorRequest)
