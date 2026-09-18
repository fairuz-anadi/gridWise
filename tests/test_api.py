"""API contract: endpoint names, status codes, response shape."""
import copy

import pytest
from fastapi.testclient import TestClient

import app.main
from conftest import PUBLIC_CASES

client = TestClient(app.main.app, raise_server_exceptions=False)
VALID = PUBLIC_CASES[5]["input"]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_valid_request_returns_full_response():
    r = client.post("/optimize-energy", json=VALID)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"scenario_id", "directive_interpretation", "hourly_plan", "total_grid_kwh",
                         "total_cost_bdt", "peak_grid_kwh", "plan_summary"}
    assert body["scenario_id"] == VALID["scenario_id"]
    assert [d["note_index"] for d in body["directive_interpretation"]] == [0, 1, 2]
    assert [p["hour"] for p in body["hourly_plan"]] == list(range(24))


def _broken(fn):
    body = copy.deepcopy(VALID)
    fn(body)
    return body


BAD_REQUESTS = {
    "23 hours": _broken(lambda b: b["hours"].pop()),
    "duplicate hour": _broken(lambda b: b["hours"][5].update(hour=4)),
    "no notes": _broken(lambda b: b.update(operator_notes=[])),
    "4 notes": _broken(lambda b: b.update(operator_notes=["a", "b", "c", "d"])),
    "blank note": _broken(lambda b: b.update(operator_notes=["  "])),
    "negative demand": _broken(lambda b: b["hours"][3].update(demand_kwh=-5)),
    "initial above capacity": _broken(lambda b: b["battery"].update(initial_energy_kwh=10_000)),
    "missing battery": _broken(lambda b: b.pop("battery")),
}


@pytest.mark.parametrize("name", BAD_REQUESTS)
def test_invalid_request_is_400(name):
    r = client.post("/optimize-energy", json=BAD_REQUESTS[name])
    assert r.status_code == 400
    assert r.json()["detail"]


def test_malformed_json_is_400():
    r = client.post("/optimize-energy", content="{bad", headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_internal_error_is_controlled(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("sk-ant-should-never-appear")
    monkeypatch.setattr(app.main, "optimize", boom)
    r = client.post("/optimize-energy", json=VALID)
    assert r.status_code == 500
    assert "sk-ant" not in r.text and set(r.json()) == {"error", "request_id"}
