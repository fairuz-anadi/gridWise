"""Randomised robustness checks: unexpected but valid numbers must never crash or yield an invalid plan.

Scenarios span 0.001x to 1,000,000x the public cases' magnitudes, zero-rate / zero-capacity batteries,
zero tariffs, and 0-3 random directives (often mutually impossible, which exercises the soft re-solve).
Seeds are fixed so failures are reproducible.
"""
import random

import pytest
from fastapi.testclient import TestClient

import app.main
from app.optimizer import Infeasible, optimize
from app.schemas import Directive, DirectiveType, Scenario
from app.validator import replay_check

N_SCENARIOS = 1000
N_REQUESTS = 150


def _window(rng):
    start = rng.randint(0, 23)
    return list(range(start, rng.randint(start + 1, 24)))


def _scenario(rng, i):
    scale = rng.choice([0.001, 1, 50, 1000, 1e6])
    cap = round(rng.uniform(0, 500) * scale, 3)
    lo = round(rng.uniform(0, cap), 3)
    battery = {
        "capacity_kwh": cap,
        "minimum_energy_kwh": lo,
        "initial_energy_kwh": round(rng.uniform(lo, cap), 3),
        "max_charge_kwh_per_hour": round(rng.choice([0, rng.uniform(0, 200)]) * scale, 3),
        "max_discharge_kwh_per_hour": round(rng.choice([0, rng.uniform(0, 200)]) * scale, 3),
    }
    hours = [{
        "hour": h,
        "demand_kwh": round(rng.choice([0, rng.uniform(0, 300)]) * scale, 3),
        "solar_kwh": round(rng.choice([0, rng.uniform(0, 300)]) * scale, 3),
        "tariff_bdt_per_kwh": round(rng.choice([0, rng.uniform(0, 40)]), 3),
    } for h in range(24)]
    return Scenario.model_validate({"scenario_id": f"FUZZ-{i}", "operator_notes": ["x"], "hours": hours, "battery": battery}), scale


def _directives(rng, cap, scale):
    out = []
    for k in range(rng.randint(0, 3)):
        t = rng.choice(list(DirectiveType))
        adj = None if t == DirectiveType.no_op else {"hours": _window(rng)}
        if t == DirectiveType.solar_reduction:
            adj["factor"] = rng.choice([0, 1, rng.random()])
        elif t == DirectiveType.minimum_battery_reserve:
            adj["minimum_energy_kwh"] = round(rng.uniform(0, cap), 3)
        elif t == DirectiveType.max_grid_window:
            adj["max_grid_kwh"] = round(rng.uniform(0, 300) * scale, 3)
        out.append(Directive(note_index=k, applies=t != DirectiveType.no_op, directive_type=t,
                             structured_adjustment=adj, explanation=""))
    return out


def test_random_scenarios_always_give_a_valid_plan():
    rng = random.Random(1)
    for i in range(N_SCENARIOS):
        scenario, scale = _scenario(rng, i)
        directives = _directives(rng, scenario.battery.capacity_kwh, scale)
        try:
            plan = optimize(scenario, directives)
            assert replay_check(scenario, directives, plan) == [], f"scenario {i}: hard plan invalid"
        except Infeasible:
            # impossible directive mix: the fallback must still obey every base GridWise rule
            plan = optimize(scenario, directives, soft=True)
            assert replay_check(scenario, [], plan) == [], f"scenario {i}: soft plan breaks base rules"


@pytest.fixture
def no_llm(monkeypatch):
    for key in ("OPENAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_random_valid_requests_never_return_5xx(no_llm):
    rng = random.Random(2)
    client = TestClient(app.main.app, raise_server_exceptions=False)
    notes = ["Do not charge the battery from 2 PM to 4 PM.", "The cafeteria menu changes tomorrow.",
             "Grid import must stay under 100 kWh from 6 PM to 9 PM."]
    for i in range(N_REQUESTS):
        scenario, _ = _scenario(rng, i)
        body = scenario.model_dump()
        body["operator_notes"] = rng.sample(notes, rng.randint(1, 3))
        rng.shuffle(body["hours"])                                   # hour order is not guaranteed
        if rng.random() < 0.2:
            body["hours"][0]["demand_kwh"] = str(body["hours"][0]["demand_kwh"])  # numeric string
        if rng.random() < 0.1:
            body["unexpected_field"] = "ignored"
        r = client.post("/optimize-energy", json=body)
        assert r.status_code == 200, f"request {i}: HTTP {r.status_code} {r.text[:200]}"
