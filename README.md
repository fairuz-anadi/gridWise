# GridWise — Smart Campus Energy Optimization Service

[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.14-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

GridWise is an automated, LLM-assisted HTTP API service developed for the **BUP CSE Fest 2026 Hackathon (Online Preliminary Round)**. It ingests 24-hour campus energy demand, rooftop solar generation, fluctuating grid electricity tariffs, and battery storage constraints alongside 1–3 unstructured natural language operator notes. 

The service deterministically extracts operational constraints, solves a cost-minimizing Linear Program (LP), verifies the schedule against strict physical and operational guardrails, and returns a verified 24-hour dispatch plan.

---

## 1. System Architecture

The GridWise pipeline follows a strict, defense-in-depth architecture:

```
                  Unstructured Input
      [24h Energy Data + 1-3 Operator Notes]
                        │
                        ▼
            ┌───────────────────────┐
            │  Stage 1: LLM Engine  │  Groq LPU / OpenAI (gpt-4o-mini)
            └───────────┬───────────┘
                        │ Raw JSON Directives
                        ▼
            ┌───────────────────────┐
            │ Stage 2: Guardrail    │  Enforces 0..23 hours, numeric bounds,
            │    & Normalization    │  time conventions, safe fallback to no_op
            └───────────┬───────────┘
                        │ Machine-Checkable Directives
                        ▼
            ┌───────────────────────┐
            │   Stage 3: HiGHS LP   │  Exact Linear Program (scipy linprog)
            │       Optimizer       │  Global minimum grid purchase cost
            └───────────┬───────────┘
                        │ 24h Dispatch Schedule
                        ▼
            ┌───────────────────────┐
            │ Stage 4: Independent  │  Validates §11 energy balance, solar caps,
            │   Replay Validator    │  rate limits, bounds, and EOD neutrality
            └───────────┬───────────┘
                        │ Verified Schedule
                        ▼
            ┌───────────────────────┐
            │ Stage 5: HTTP Output  │  Exact Problem Statement §10 Schema
            └───────────────────────┘
```

### Core Pipeline Components
1. **Stage 1 — LLM Semantic Interpreter**:
   - Parses natural language notes into structured directive types.
   - Accurately converts colloquial time expressions (`"1 PM to 3 PM"` $\to$ `[13, 14]`, `"noon until 2 PM"` $\to$ `[12, 13]`, `"from 6 PM until 9 PM"` $\to$ `[18, 19, 20]`).
   - Normalizes reduction factors (e.g., an 80% reduction means `factor = 0.2` usable remaining solar).
   - Computes percentage-based reserve requests relative to battery capacity.
   - Classifies irrelevant campus notices (menus, library hours, sports notices) as `no_op`.
2. **Stage 2 — Deterministic Guardrails (`app/directives.py`)**:
   - Validates that every note receives exactly one interpretation in strict `note_index` order `0..N-1`.
   - Restricts directive types to the 6 canonical types (`solar_reduction`, `minimum_battery_reserve`, `no_charge_window`, `no_discharge_window`, `max_grid_window`, `no_op`).
   - Guarantees `no_op` has `applies = false` and `structured_adjustment = null`, while all other directives have `applies = true`.
   - Normalizes and bounds hours (unique, ascending, integers $\in [0, 23]$), factor $\in [0, 1]$, reserve $\in [0, \text{capacity}]$, and non-negative grid caps.
   - **Safe Failure Guarantee**: Malformed LLM outputs automatically default to a safe `no_op` without taking down the service.
3. **Stage 3 — Mathematical Optimizer (`app/optimizer.py`)**:
   - Formulates the 24-hour dispatch problem as a Linear Program solved via `scipy.optimize.linprog(method="highs")`.
   - Solves for hourly grid imports $g_h$, solar usage $s_h$, battery charging $c_h$, discharging $d_h$, and state-of-charge $e_h$.
   - Incorporates battery state transitions ($e_h = e_{h-1} + c_h - d_h$), rate limits, end-of-day neutrality ($e_{23} = e_{\text{init}}$), and hourly energy balance.
   - Introduces a minor regularization term ($10^{-6}$) on battery cycling to strictly resolve degeneracy and prevent simultaneous charging and discharging.
4. **Stage 4 — Independent Replay Validator (`app/validator.py`)**:
   - Re-simulates the resulting plan hour-by-hour against ground-truth energy balance and active directives.
   - Asserts tolerance within $0.01\text{ kWh}$ / $0.01\text{ BDT}$.

---

## 2. Model & Provider Configuration

GridWise includes built-in multi-model failover for high availability and low latency:

| Provider | Supported Models | Primary Advantage |
|---|---|---|
| **Groq LPU** (Default) | `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b` | Sub-second inference latency ($< 100\text{ ms}$), achieving top marks on the $p95 \le 5\text{s}$ criterion. |
| **OpenAI** (Fallback) | `gpt-4o-mini` | High rate-limit headroom ($10{,}000\text{ RPM}$) with native structured JSON mode. |

The active provider can be configured via the `LLM_PROVIDER` environment variable (`groq` or `openai`). If a provider encounters a rate limit or connection issue, the system automatically falls over to the alternate provider and models.

---

## 3. Local Quickstart (Clean Environment)

Follow these copy-paste instructions to run the service locally:

### Step 1: Clone Repository
```bash
git clone https://github.com/fairuz-anadi/gridWise.git
cd gridWise
```

### Step 2: Configure Environment Variables
Copy the example environment file and add your API keys:
```bash
cp .env.example .env
```
Edit `.env` and configure your keys:
```env
GROQ_API_KEY=your_groq_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
LLM_PROVIDER=groq
PORT=8000
HOST=0.0.0.0
```
*(Never commit `.env` to version control; it is ignored in `.gitignore`)*

### Step 3: Set Up Virtual Environment & Dependencies
```bash
# Create virtual environment with Python 3.11, 3.12, or 3.14
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 4: Run the API Service
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
The API is now running and reachable at `http://0.0.0.0:8000`.

---

## 4. API Endpoints & Usage

### 1. Readiness Probe: `GET /health`
```bash
curl -X GET http://localhost:8000/health
```
**Response (200 OK)**:
```json
{
  "status": "ok"
}
```

### 2. Main Optimization: `POST /optimize-energy`
```bash
curl -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "SAMPLE-01",
    "operator_notes": [
      "Facilities will wash the rooftop solar panels from noon until 2 PM. During cleaning, usable solar should be treated as roughly 25% of the forecast.",
      "The sports office moved next months registration deadline."
    ],
    "hours": [
      {"hour": 0, "demand_kwh": 90, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 1, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 2, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 3, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 4, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 5, "demand_kwh": 95, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 6, "demand_kwh": 110, "solar_kwh": 5, "tariff_bdt_per_kwh": 8},
      {"hour": 7, "demand_kwh": 130, "solar_kwh": 20, "tariff_bdt_per_kwh": 10},
      {"hour": 8, "demand_kwh": 150, "solar_kwh": 50, "tariff_bdt_per_kwh": 12},
      {"hour": 9, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14},
      {"hour": 10, "demand_kwh": 175, "solar_kwh": 130, "tariff_bdt_per_kwh": 16},
      {"hour": 11, "demand_kwh": 180, "solar_kwh": 160, "tariff_bdt_per_kwh": 16},
      {"hour": 12, "demand_kwh": 185, "solar_kwh": 180, "tariff_bdt_per_kwh": 15},
      {"hour": 13, "demand_kwh": 180, "solar_kwh": 170, "tariff_bdt_per_kwh": 14},
      {"hour": 14, "demand_kwh": 170, "solar_kwh": 140, "tariff_bdt_per_kwh": 13},
      {"hour": 15, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14},
      {"hour": 16, "demand_kwh": 170, "solar_kwh": 45, "tariff_bdt_per_kwh": 18},
      {"hour": 17, "demand_kwh": 185, "solar_kwh": 10, "tariff_bdt_per_kwh": 22},
      {"hour": 18, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 28},
      {"hour": 19, "demand_kwh": 215, "solar_kwh": 0, "tariff_bdt_per_kwh": 30},
      {"hour": 20, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 26},
      {"hour": 21, "demand_kwh": 175, "solar_kwh": 0, "tariff_bdt_per_kwh": 18},
      {"hour": 22, "demand_kwh": 135, "solar_kwh": 0, "tariff_bdt_per_kwh": 10},
      {"hour": 23, "demand_kwh": 105, "solar_kwh": 0, "tariff_bdt_per_kwh": 7}
    ],
    "battery": {
      "capacity_kwh": 220,
      "initial_energy_kwh": 110,
      "minimum_energy_kwh": 40,
      "max_charge_kwh_per_hour": 50,
      "max_discharge_kwh_per_hour": 50
    }
  }'
```

**Expected Response**:
```json
{
  "scenario_id": "SAMPLE-01",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {
        "hours": [12, 13],
        "factor": 0.25
      },
      "explanation": "Solar output is reduced to 25% of forecast while panels are cleaned from noon to 2 PM."
    },
    {
      "note_index": 1,
      "applies": false,
      "directive_type": "no_op",
      "structured_adjustment": null,
      "explanation": "The note about sports office registration deadline does not affect today's energy schedule."
    }
  ],
  "hourly_plan": [ ... 24 entries ... ],
  "total_grid_kwh": 2692.5,
  "total_cost_bdt": 38365.0,
  "peak_grid_kwh": 175.0,
  "plan_summary": "Scheduled 24-hour campus energy plan with active directives: solar_reduction. Total grid import: 2692.50 kWh, peak grid: 175.00 kWh, total cost: 38365.00 BDT."
}
```

---

## 5. Docker Fallback Deployment

A production-ready `Dockerfile` is provided that binds to `0.0.0.0:8000` and runs under an unprivileged user.

### Build the Image
```bash
docker build -t gridwise:latest .
```

### Run the Container
Pass environment variables into the container without baking secrets into the image:
```bash
docker run -d \
  --name gridwise-service \
  -p 8000:8000 \
  --env-file .env \
  gridwise:latest
```

### Verify Container Health
```bash
curl -X GET http://localhost:8000/health
```

---

## 6. Running Tests

Run the complete test suite containing API unit tests, schema validation, and public case replays:
```bash
pytest tests/ -v
```

This verifies:
- `GET /health` returns HTTP 200 `{"status": "ok"}`
- Invalid requests (e.g. non-24 hours, malformed JSON, out-of-bounds battery values) return HTTP 400
- All 10 public reference scenarios solve to exact optimal costs within $0.01\text{ BDT}$
- Replay validator checks 100% of energy balance, battery rate limits, bounds, and end-of-day neutrality

---

## 7. Environment Variables Reference

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `GROQ_API_KEY` | API Key for Groq LPU inference | Yes (if using Groq) | None | `gsk_...` |
| `OPENAI_API_KEY` | API Key for OpenAI inference | Yes (if using OpenAI) | None | `sk-proj-...` |
| `LLM_PROVIDER` | Preferred LLM provider (`groq` or `openai`) | No | `groq` | `groq` |
| `PORT` | Service listening port | No | `8000` | `8000` |
| `HOST` | Network interface binding | No | `0.0.0.0` | `0.0.0.0` |

---

## 8. Dependencies & Credits

- **FastAPI** (`0.141.1`) & **Uvicorn** (`0.53.0`): High-performance async ASGI web framework.
- **Pydantic** (`2.13.5`): Schema validation and JSON serialization.
- **SciPy** (`1.18.1`): `scipy.optimize.linprog` with the HiGHS simplex/interior-point solver.
- **NumPy** (`2.5.3`): Numerical array operations for constraint matrices.
- **HTTPX** (`0.28.1`): Asynchronous HTTP client for LLM communication.
- **Pytest** (`9.1.1`): Automated test harness.

---

## 9. Known Limitations & Safe Operation

- **Infeasible Scenarios**: If contradictory hard physical constraints are submitted (e.g., zero grid allowed with demand exceeding solar and battery limits combined), the optimizer raises `Infeasible`, which the API handles gracefully by returning an HTTP 422 with diagnostic details.
- **Secret Safety**: Secrets and raw tracebacks are never exposed in log outputs or HTTP error responses.
