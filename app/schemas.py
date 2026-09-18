"""Request/response models for the GridWise API.

Field names follow Problem Statement sections 07 and 10 exactly; the judge checks them byte-for-byte.
This file is the shared contract: everyone imports types from here.

TODO(Anadi, P0): structural validation -> 400 (exactly 24 unique hours 0-23, 1-3 non-empty notes,
numeric values >= 0).
"""
from enum import Enum
from typing import Literal

from pydantic import BaseModel


# ---------- Request (spec §07) ----------

class HourInput(BaseModel):
    hour: int
    demand_kwh: float
    solar_kwh: float
    tariff_bdt_per_kwh: float


class Battery(BaseModel):
    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float


class Scenario(BaseModel):
    """POST /optimize-energy request body."""
    scenario_id: str
    operator_notes: list[str]
    hours: list[HourInput]
    battery: Battery


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
