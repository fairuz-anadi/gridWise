"""Tests for optimizer and replay validator across all 10 public reference cases."""
import json
from pathlib import Path
import pytest

from app.directives import interpret_and_validate
from app.optimizer import optimize
from app.schemas import Directive, Scenario
from app.validator import replay_check

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "public_cases.json"


@pytest.fixture
def public_cases():
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["cases"]


def test_optimizer_and_validator_on_all_public_cases(public_cases):
    """Test that the LP optimizer achieves exact optimal costs and passes all replay checks."""
    tolerance = 0.01

    for case in public_cases:
        case_id = case["id"]
        inp = case["input"]
        exp = case["expected_output"]

        scenario = Scenario(**inp)
        expected_directives = [Directive(**d) for d in exp["directive_interpretation"]]

        # Run optimizer using ground-truth reference directives
        plan = optimize(scenario, expected_directives)

        # 1. Check replay validator produces zero violations
        violations = replay_check(scenario, expected_directives, plan)
        assert violations == [], f"Replay violations on {case_id}: {violations}"

        # 2. Check cost equivalence within 0.01 BDT
        exp_cost = exp["total_cost_bdt"]
        assert abs(plan.total_cost_bdt - exp_cost) <= tolerance, (
            f"{case_id}: cost mismatch, expected {exp_cost}, got {plan.total_cost_bdt}"
        )

        # 3. Check total grid import within 0.01 kWh
        exp_grid = exp["total_grid_kwh"]
        assert abs(plan.total_grid_kwh - exp_grid) <= tolerance, (
            f"{case_id}: grid mismatch, expected {exp_grid}, got {plan.total_grid_kwh}"
        )

        # 4. Check peak grid import within 0.01 kWh
        exp_peak = exp["peak_grid_kwh"]
        assert abs(plan.peak_grid_kwh - exp_peak) <= tolerance, (
            f"{case_id}: peak mismatch, expected {exp_peak}, got {plan.peak_grid_kwh}"
        )
