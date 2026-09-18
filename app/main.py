"""GridWise API entry point.

Run locally: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.directives import interpret_and_validate
from app.optimizer import Infeasible, optimize
from app.schemas import OptimizeResponse, Scenario
from app.validator import replay_check

# Set up logging without leaking sensitive values
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("gridwise")


def _load_env() -> None:
    """Load .env file if present into environment variables."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))


_load_env()

app = FastAPI(title="GridWise Smart Campus Energy Optimizer", version="2.0")


from fastapi.encoders import jsonable_encoder


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Ensure malformed or invalid request bodies return HTTP 400 per spec §06.1."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=jsonable_encoder(
            {"detail": "Malformed JSON or structurally invalid request", "errors": exc.errors()}
        ),
    )


@app.get("/health")
def health() -> dict:
    """Readiness probe for the judging harness."""
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy(scenario: Scenario) -> OptimizeResponse:
    """Main LLM interpretation and 24-hour energy optimization endpoint."""
    try:
        # Stage 1 & 2: LLM interpretation + deterministic guardrails
        directives = await interpret_and_validate(scenario.operator_notes, scenario.battery)

        # Stage 3: LP mathematical optimization
        try:
            plan = optimize(scenario, directives)
        except Infeasible as e:
            logger.error("Infeasible scenario %s: %s", scenario.scenario_id, e)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Infeasible scenario under requested directives: {str(e)}"
            )

        # Stage 4: Deterministic replay verification
        violations = replay_check(scenario, directives, plan)
        if violations:
            logger.warning("Replay verification warnings for %s: %s", scenario.scenario_id, violations)

        # Stage 5: Construct concise plan summary
        applied_directives = [d.directive_type.value for d in directives if d.applies]
        if applied_directives:
            applied_str = f"with active directives: {', '.join(applied_directives)}"
        else:
            applied_str = "with no active directive constraints"

        plan_summary = (
            f"Scheduled 24-hour campus energy plan {applied_str}. "
            f"Total grid import: {plan.total_grid_kwh:.2f} kWh, "
            f"peak grid: {plan.peak_grid_kwh:.2f} kWh, "
            f"total cost: {plan.total_cost_bdt:.2f} BDT."
        )

        return OptimizeResponse(
            scenario_id=scenario.scenario_id,
            directive_interpretation=directives,
            hourly_plan=plan.hourly_plan,
            total_grid_kwh=plan.total_grid_kwh,
            total_cost_bdt=plan.total_cost_bdt,
            peak_grid_kwh=plan.peak_grid_kwh,
            plan_summary=plan_summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        # Controlled 500 error: never expose secrets or raw stack traces in response
        logger.error("Controlled internal server error on scenario %s: %s", scenario.scenario_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal optimization error occurred while processing the scenario."
        )
