"""Request/response models for the GridWise API.

Field names follow Problem Statement sections 07 and 10 exactly; the judge checks them byte-for-byte.
This file is the shared contract: everyone imports types from here.
"""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------- Request (spec §07) ----------

class HourInput(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="Hour of the day (0-23)")
    demand_kwh: float = Field(..., ge=0.0, description="Campus demand in kWh")
    solar_kwh: float = Field(..., ge=0.0, description="Available solar energy in kWh")
    tariff_bdt_per_kwh: float = Field(..., ge=0.0, description="Grid tariff in BDT per kWh")


class Battery(BaseModel):
    capacity_kwh: float = Field(..., gt=0.0, description="Maximum storage capacity in kWh")
    initial_energy_kwh: float = Field(..., ge=0.0, description="Starting energy in kWh")
    minimum_energy_kwh: float = Field(..., ge=0.0, description="Base reserve level in kWh")
    max_charge_kwh_per_hour: float = Field(..., ge=0.0, description="Hourly charge rate limit")
    max_discharge_kwh_per_hour: float = Field(..., ge=0.0, description="Hourly discharge rate limit")

    @model_validator(mode="after")
    def validate_battery_levels(self) -> "Battery":
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        return self


class Scenario(BaseModel):
    """POST /optimize-energy request body."""
    scenario_id: str = Field(..., min_length=1, description="Unique scenario identifier")
    operator_notes: list[str] = Field(..., description="1-3 natural language notes")
    hours: list[HourInput] = Field(..., description="Exactly 24 hourly entries")
    battery: Battery

    @field_validator("operator_notes")
    @classmethod
    def validate_notes(cls, v: list[str]) -> list[str]:
        if not (1 <= len(v) <= 3):
            raise ValueError(f"operator_notes must contain between 1 and 3 items, got {len(v)}")
        for idx, note in enumerate(v):
            if not isinstance(note, str) or not note.strip():
                raise ValueError(f"operator_note at index {idx} must be a non-empty string")
        return v

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v: list[HourInput]) -> list[HourInput]:
        if len(v) != 24:
            raise ValueError(f"hours array must contain exactly 24 entries, got {len(v)}")
        seen_hours = [item.hour for item in v]
        if seen_hours != list(range(24)):
            raise ValueError("hours must contain unique hours 0 through 23 in exact ascending order")
        return v


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
