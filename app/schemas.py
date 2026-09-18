"""Request/response models for the GridWise API.

Field names follow Problem Statement sections 07 and 10 exactly; the judge checks them byte-for-byte.
This file is the shared contract: everyone imports types from here.

Request models validate structure; any failure becomes a 400 (handler in main.py).
"""
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Finite and >= 0: every numeric input in the spec is a non-negative quantity.
NonNegFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


# ---------- Request (spec §07) ----------

class HourInput(BaseModel):
    hour: Annotated[int, Field(ge=0, le=23)]
    demand_kwh: NonNegFloat
    solar_kwh: NonNegFloat
    tariff_bdt_per_kwh: NonNegFloat


class Battery(BaseModel):
    capacity_kwh: NonNegFloat
    initial_energy_kwh: NonNegFloat
    minimum_energy_kwh: NonNegFloat
    max_charge_kwh_per_hour: NonNegFloat
    max_discharge_kwh_per_hour: NonNegFloat

    @model_validator(mode="after")
    def _levels_consistent(self):
        # Outside this range no schedule can exist (end-of-day neutrality forces E_after[23] = initial).
        if not (self.minimum_energy_kwh <= self.initial_energy_kwh <= self.capacity_kwh):
            raise ValueError("battery must satisfy minimum_energy_kwh <= initial_energy_kwh <= capacity_kwh")
        return self


class Scenario(BaseModel):
    """POST /optimize-energy request body."""
    scenario_id: str
    operator_notes: Annotated[list[str], Field(min_length=1, max_length=3)]
    hours: Annotated[list[HourInput], Field(min_length=24, max_length=24)]
    battery: Battery

    @field_validator("operator_notes")
    @classmethod
    def _notes_non_empty(cls, notes: list[str]) -> list[str]:
        if any(not n.strip() for n in notes):
            raise ValueError("operator_notes must be non-empty strings")
        return notes

    @field_validator("hours")
    @classmethod
    def _hours_complete(cls, hours: list[HourInput]) -> list[HourInput]:
        if sorted(h.hour for h in hours) != list(range(24)):
            raise ValueError("hours must contain each hour 0-23 exactly once")
        return sorted(hours, key=lambda h: h.hour)


# ---------- Directives (spec §04, §10.2) ----------

class DirectiveType(str, Enum):
    solar_reduction = "solar_reduction"
    minimum_battery_reserve = "minimum_battery_reserve"
    no_charge_window = "no_charge_window"
    no_discharge_window = "no_discharge_window"
    max_grid_window = "max_grid_window"
    no_op = "no_op"


class Directive(BaseModel):
    """One directive_interpretation entry per operator note, in note_index order.

    structured_adjustment shapes (spec §04):
      solar_reduction          {"hours": [...], "factor": float}
      minimum_battery_reserve  {"hours": [...], "minimum_energy_kwh": float}
      no_charge_window         {"hours": [...]}
      no_discharge_window      {"hours": [...]}
      max_grid_window          {"hours": [...], "max_grid_kwh": float}
      no_op                    None  (and applies = False)
    """
    note_index: int
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: dict | None
    explanation: str


# ---------- Plan / response (spec §10) ----------

class HourPlan(BaseModel):
    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: Literal["charge", "discharge", "idle"]
    battery_kwh: float
    battery_energy_after_kwh: float


class Plan(BaseModel):
    """What optimize() returns: the 24-hour schedule plus totals recalculated from it."""
    hourly_plan: list[HourPlan]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float


class OptimizeResponse(BaseModel):
    """POST /optimize-energy response body."""
    scenario_id: str
    directive_interpretation: list[Directive]
    hourly_plan: list[HourPlan]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str
