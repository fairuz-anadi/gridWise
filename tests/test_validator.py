"""Every replay rule must catch its violation, and the organizers' reference plans must pass."""
import pytest

from app.optimizer import optimize
from app.schemas import Directive, Plan, Scenario
from app.validator import replay_check
from conftest import PUBLIC_CASES


def test_reference_plans_are_valid(public_case):
    scenario = Scenario.model_validate(public_case["input"])
    directives = [Directive.model_validate(d) for d in public_case["expected_output"]["directive_interpretation"]]
    assert replay_check(scenario, directives, Plan.model_validate(public_case["expected_output"])) == []


# SAMPLE-06: solar x0.5 at hours 10-11, no charging at 14-15, battery 35..220 kWh, 50 kWh/h limits
CASE = PUBLIC_CASES[5]
SCENARIO = Scenario.model_validate(CASE["input"])
DIRECTIVES = [Directive.model_validate(d) for d in CASE["expected_output"]["directive_interpretation"]]
PLAN = optimize(SCENARIO, DIRECTIVES)


def _set(**changes):
    def apply(plan):
        for path, value in changes.items():
            target = plan
            *parts, last = path.split("__")
            for p in parts:
                target = target.hourly_plan[int(p[1:])] if p.startswith("h") else getattr(target, p)
            setattr(target, last, value)
    return apply


def _charge_at(hour, kwh):
    def apply(plan):
        row = plan.hourly_plan[hour]
        prev = plan.hourly_plan[hour - 1].battery_energy_after_kwh
        row.battery_action, row.battery_kwh, row.battery_energy_after_kwh = "charge", kwh, prev + kwh
        row.grid_kwh += kwh
    return apply


BREAKS = {
    "hours out of order": lambda p: p.hourly_plan.reverse(),
    "negative value": _set(h3__grid_kwh=-1.0),
    "idle with energy": _set(h3__battery_kwh=5.0),
    "bad transition": _set(h3__battery_energy_after_kwh=999.0),
    "energy balance": _set(h3__grid_kwh=PLAN.hourly_plan[3].grid_kwh + 5),
    "solar over effective": _set(h10__solar_used_kwh=999.0),
    "charge in no-charge window": _charge_at(14, 5.0),
    "charge rate": _charge_at(5, 80.0),
    "end-of-day neutrality": _set(h23__battery_energy_after_kwh=0.0),
    "total grid mismatch": _set(total_grid_kwh=1.0),
    "total cost mismatch": _set(total_cost_bdt=1.0),
    "peak mismatch": _set(peak_grid_kwh=1.0),
}


@pytest.mark.parametrize("name", BREAKS)
def test_violation_is_detected(name):
    plan = PLAN.model_copy(deep=True)
    BREAKS[name](plan)
    assert replay_check(SCENARIO, DIRECTIVES, plan), f"{name} was not detected"


def test_ignoring_a_directive_is_detected():
    ignored = optimize(SCENARIO, [])  # plan built without the solar cut / no-charge window
    assert replay_check(SCENARIO, DIRECTIVES, ignored)
