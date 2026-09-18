from app.optimizer import Infeasible, optimize
from app.schemas import Directive, DirectiveType, Scenario
from app.validator import replay_check
from conftest import PUBLIC_CASES

import pytest


def _load(case):
    scenario = Scenario.model_validate(case["input"])
    directives = [Directive.model_validate(d) for d in case["expected_output"]["directive_interpretation"]]
    return scenario, directives


def test_public_case_matches_reference_cost(public_case):
    scenario, directives = _load(public_case)
    plan = optimize(scenario, directives)
    assert replay_check(scenario, directives, plan) == []
    assert abs(plan.total_cost_bdt - public_case["expected_output"]["total_cost_bdt"]) <= 0.01


def _impossible_grid_cap(case):
    """Cap grid at 0 kWh all day: no plan can meet night-time demand."""
    scenario, directives = _load(case)
    cap = Directive(note_index=len(directives), applies=True, directive_type=DirectiveType.max_grid_window,
                    structured_adjustment={"hours": list(range(24)), "max_grid_kwh": 0}, explanation="")
    return scenario, directives + [cap]


def test_infeasible_directives_raise():
    scenario, directives = _impossible_grid_cap(PUBLIC_CASES[4])
    with pytest.raises(Infeasible):
        optimize(scenario, directives)


def test_soft_resolve_still_obeys_base_rules():
    scenario, directives = _impossible_grid_cap(PUBLIC_CASES[4])
    plan = optimize(scenario, directives, soft=True)
    assert replay_check(scenario, [], plan) == []


def test_soft_resolve_equals_hard_when_feasible(public_case):
    scenario, directives = _load(public_case)
    assert optimize(scenario, directives, soft=True).total_cost_bdt == optimize(scenario, directives).total_cost_bdt
