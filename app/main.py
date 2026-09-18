"""GridWise API entry point.

Run locally: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import logging
import os
from pathlib import Path
import time
import uuid

# Load local .env if present (or python-dotenv if installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.directives import interpret_and_validate
from app.optimizer import Infeasible, optimize
from app.schemas import Directive, OptimizeResponse, Plan, Scenario
from app.validator import replay_check

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("gridwise")

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(title="GridWise Smart Campus Energy Optimizer", version="2.0")


class PlanRejected(Exception):
    """Even the soft re-solve produced a plan that breaks a base GridWise rule."""


@app.exception_handler(RequestValidationError)
async def _bad_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Spec §6.1: malformed JSON or structurally invalid request -> 400 (FastAPI default is 422)
    detail = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=400, content={"error": "invalid_request", "detail": detail})


@app.exception_handler(Exception)
async def _internal_error(request: Request, exc: Exception) -> JSONResponse:
    # Controlled 500: no stack trace or sensitive credential in the response or logs
    request_id = uuid.uuid4().hex[:12]
    log.error("internal_error request_id=%s type=%s", request_id, type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": "internal_error", "request_id": request_id})


@app.api_route("/health", methods=["GET", "HEAD"])
def health() -> dict:
    """Readiness probe for the judging harness."""
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy(request: Request) -> OptimizeResponse:
    # Parse the body as JSON whatever Content-Type the client sends (none, text/plain, curl -d's form
    # default); FastAPI's own body binding would reject those with 400 even when the JSON is valid.
    try:
        scenario = Scenario.model_validate_json(await request.body())
    except ValidationError as e:
        raise RequestValidationError(e.errors(include_url=False, include_context=False))
    start = time.perf_counter()
    directives = await interpret_and_validate(scenario.operator_notes, scenario.battery)
    llm_ms = (time.perf_counter() - start) * 1000

    plan = _solve(scenario, directives)

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


def _solve(scenario: Scenario, directives: list[Directive]) -> Plan:
    """Hard LP + replay check; if either fails, soft re-solve that still obeys every base rule."""
    sid = scenario.scenario_id
    try:
        plan = optimize(scenario, directives)
        violations = replay_check(scenario, directives, plan)
        if not violations:
            return plan
        log.error("replay_failed scenario_id=%s violations=%s", sid, violations[:5])
    except Infeasible:
        log.warning("infeasible scenario_id=%s, re-solving with soft directives", sid)

    plan = optimize(scenario, directives, soft=True)
    base_violations = replay_check(scenario, [], plan)
    if base_violations:
        log.error("soft_replay_failed scenario_id=%s violations=%s", sid, base_violations[:5])
        raise PlanRejected()
    log.warning("relaxed scenario_id=%s directives=%s", sid, replay_check(scenario, directives, plan)[:5])
    return plan


def _summary(directives: list[Directive], plan: Plan) -> str:
    applied = [d.directive_type.value for d in directives if d.applies]
    ignored = len(directives) - len(applied)
    rules = ", ".join(applied) if applied else "no operator directives"
    return (f"Applied {rules}; ignored {ignored} unrelated note(s). "
            f"Battery shifts grid purchases toward cheaper hours and returns to its starting level; "
            f"total grid cost {plan.total_cost_bdt:.2f} BDT.")


# Operator console (Samprity's build). Mounted last so it can never shadow the judged routes.
if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="console")
