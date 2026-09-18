"""GridWise API entry point. Owner: Anadi.

Run locally:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import OptimizeResponse, Scenario

app = FastAPI(title="GridWise")


@app.exception_handler(RequestValidationError)
async def _bad_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Spec §6.1: malformed JSON or structurally invalid request -> 400 (FastAPI's default is 422).
    details = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=400, content={"error": "invalid_request", "details": details})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy(scenario: Scenario) -> OptimizeResponse:
    # TODO(Anadi, integration): interpret_and_validate -> optimize -> replay_check -> OptimizeResponse
    raise HTTPException(status_code=501, detail="not implemented yet")
