"""API and schema validation tests."""
from fastapi.testclient import TestClient
import pytest

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_malformed_json_returns_400():
    resp = client.post(
        "/optimize-energy",
        content="not-json",
        headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400


def test_missing_hours_returns_400():
    payload = {
        "scenario_id": "TEST-01",
        "operator_notes": ["Valid note"],
        "hours": [
            {"hour": 0, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}
            # Only 1 hour instead of 24
        ],
        "battery": {
            "capacity_kwh": 200,
            "initial_energy_kwh": 100,
            "minimum_energy_kwh": 20,
            "max_charge_kwh_per_hour": 50,
            "max_discharge_kwh_per_hour": 50
        }
    }
    resp = client.post("/optimize-energy", json=payload)
    assert resp.status_code == 400


def test_empty_notes_returns_400():
    payload = {
        "scenario_id": "TEST-02",
        "operator_notes": [],  # Must be 1..3
        "hours": [
            {"hour": h, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}
            for h in range(24)
        ],
        "battery": {
            "capacity_kwh": 200,
            "initial_energy_kwh": 100,
            "minimum_energy_kwh": 20,
            "max_charge_kwh_per_hour": 50,
            "max_discharge_kwh_per_hour": 50
        }
    }
    resp = client.post("/optimize-energy", json=payload)
    assert resp.status_code == 400


def test_too_many_notes_returns_400():
    payload = {
        "scenario_id": "TEST-03",
        "operator_notes": ["Note 1", "Note 2", "Note 3", "Note 4"],  # Max 3
        "hours": [
            {"hour": h, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}
            for h in range(24)
        ],
        "battery": {
            "capacity_kwh": 200,
            "initial_energy_kwh": 100,
            "minimum_energy_kwh": 20,
            "max_charge_kwh_per_hour": 50,
            "max_discharge_kwh_per_hour": 50
        }
    }
    resp = client.post("/optimize-energy", json=payload)
    assert resp.status_code == 400


def test_invalid_battery_capacity_returns_400():
    payload = {
        "scenario_id": "TEST-04",
        "operator_notes": ["Clean panels"],
        "hours": [
            {"hour": h, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}
            for h in range(24)
        ],
        "battery": {
            "capacity_kwh": -10,  # Invalid negative capacity
            "initial_energy_kwh": 100,
            "minimum_energy_kwh": 20,
            "max_charge_kwh_per_hour": 50,
            "max_discharge_kwh_per_hour": 50
        }
    }
    resp = client.post("/optimize-energy", json=payload)
    assert resp.status_code == 400


def test_end_to_end_optimize_energy():
    import json
    from pathlib import Path
    fixtures = Path(__file__).parent / "fixtures" / "public_cases.json"
    with open(fixtures, "r", encoding="utf-8") as f:
        case = json.load(f)["cases"][0]

    resp = client.post("/optimize-energy", json=case["input"])
    assert resp.status_code == 200
    data = resp.json()

    assert data["scenario_id"] == "SAMPLE-01"
    assert len(data["directive_interpretation"]) == 2
    assert len(data["hourly_plan"]) == 24
    assert abs(data["total_cost_bdt"] - case["expected_output"]["total_cost_bdt"]) <= 0.01
    assert abs(data["total_grid_kwh"] - case["expected_output"]["total_grid_kwh"]) <= 0.01
    assert abs(data["peak_grid_kwh"] - case["expected_output"]["peak_grid_kwh"]) <= 0.01

