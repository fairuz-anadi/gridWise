"""GridWise API entry point. Owner: Anadi.

Run locally:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI, HTTPException

from app.schemas import OptimizeResponse, Scenario

app = FastAPI(title="GridWise")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy(scenario: Scenario) -> OptimizeResponse:
    # TODO(Anadi, integration): interpret_and_validate -> optimize -> replay_check -> OptimizeResponse
    raise HTTPException(status_code=501, detail="not implemented yet")
