"""GridWise API entry point. Owner: Anadi.

Run locally:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.directives import interpret_and_validate
from app.optimizer import optimize
from app.schemas import Directive, OptimizeResponse, Plan, Scenario
from app.validator import replay_check

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("gridwise")

app = FastAPI(title="GridWise")


class PlanRejected(Exception):
    """Our own replay check found violations in the optimizer's plan."""


@app.exception_handler(RequestValidationError)
async def _bad_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Spec §6.1: malformed JSON or structurally invalid request -> 400 (FastAPI's default is 422).
    details = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=400, content={"error": "invalid_request", "details": details})


@app.exception_handler(Exception)
async def _internal_error(request: Request, exc: Exception) -> JSONResponse:
    # Controlled 500: no stack trace or exception text in the response or the logs.
    request_id = uuid.uuid4().hex[:12]
    log.error("internal_error request_id=%s type=%s", request_id, type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": "internal_error", "request_id": request_id})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy(scenario: Scenario) -> OptimizeResponse:
    start = time.perf_counter()
    directives = await interpret_and_validate(scenario.operator_notes, scenario.battery)
    llm_ms = (time.perf_counter() - start) * 1000

    plan = optimize(scenario, directives)
    violations = replay_check(scenario, directives, plan)
    if violations:
        # TODO(Anadi, P1): soft-constraint re-solve before giving up.
        log.error("replay_failed scenario_id=%s violations=%s", scenario.scenario_id, violations[:5])
        raise PlanRejected()

    log.info("optimized scenario_id=%s notes=%d llm_ms=%.0f total_ms=%.0f cost=%.2f",
             scenario.scenario_id, len(scenario.operator_notes), llm_ms,
             (time.perf_counter() - start) * 1000, plan.total_cost_bdt)
    return OptimizeResponse(
        scenario_id=scenario.scenario_id,
        directive_interpretation=directives,
        hourly_plan=plan.hourly_plan,
        total_grid_kwh=plan.total_grid_kwh,
        total_cost_bdt=plan.total_cost_bdt,
        peak_grid_kwh=plan.peak_grid_kwh,
        plan_summary=_summary(directives, plan),
    )


def _summary(directives: list[Directive], plan: Plan) -> str:
    applied = [d.directive_type.value for d in directives if d.applies]
    ignored = len(directives) - len(applied)
    rules = ", ".join(applied) if applied else "no operator directives"
    return (f"Applied {rules}; ignored {ignored} unrelated note(s). "
            f"Battery shifts grid purchases toward cheaper hours and returns to its starting level; "
            f"total grid cost {plan.total_cost_bdt:.2f} BDT.")
