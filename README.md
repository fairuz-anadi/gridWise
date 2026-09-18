# GridWise — Smart Campus Energy Optimization Service

LLM-assisted HTTP API for the **BUP CSE Fest 2026 Hackathon (online preliminary)**. It receives a
24-hour campus scenario (hourly demand, rooftop solar, grid tariff, battery limits) plus 1–3 natural-language
operator notes, interprets the notes with a language model, validates the interpretation
deterministically, solves a cost-minimizing linear program, replays the result against every energy
and battery rule, and returns a verified 24-hour schedule.

**Live deployment:** https://gridwise-hampton.onrender.com
(`GET https://gridwise-hampton.onrender.com/health` · `POST https://gridwise-hampton.onrender.com/optimize-energy`;
the operator console is at the root URL). Check all ten public cases against it:
`python scripts/run_public_cases.py --url https://gridwise-hampton.onrender.com` → `10/10 passed`.

Endpoints: `GET /health` · `POST /optimize-energy` (contract in §4). Team: Anadi (API, optimizer,
validator, deployment), Turjo (LLM interpretation and guardrails), Samprity (operator console, docs).

---

## 1. System Architecture

The GridWise pipeline follows a strict, defense-in-depth architecture:

```
                  Unstructured Input
      [24h Energy Data + 1-3 Operator Notes]
                        │
                        ▼
            ┌───────────────────────┐
            │  Stage 1: LLM Engine  │  OpenAI gpt-4o-mini / Groq (windows + typed values)
            └───────────┬───────────┘
                        │ Schema-constrained JSON
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
   - Returns whole-hour windows (`"1 PM to 3 PM"` → start 13, end 15 exclusive) and a typed value; the `hours` array and kWh figures are derived in code, never by the model.
   - Normalizes reduction factors (e.g., an 80% reduction means `factor = 0.2` usable remaining solar).
   - Flags percentage-based reserves (`reserve_percent_of_capacity`) so the guardrail converts them using the request's battery capacity.
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
   - Collapses each hour to a single net battery action after solving and recomputes grid import from the rounded terms, so the energy balance is exact to the returned precision.
4. **Stage 4 — Independent Replay Validator (`app/validator.py`)**:
   - Re-simulates the resulting plan hour-by-hour against ground-truth energy balance and active directives.
   - Asserts tolerance within $0.01\text{ kWh}$ / $0.01\text{ BDT}$.

---


## 2. Language model: role, provider, guardrails

**Role.** The model is on the mandatory path: it reads `operator_notes` and produces the structured
interpretation that the optimizer consumes. It is *only* asked to do language: for each note it returns
a directive type, one or more whole-hour windows (`start_hour`, `end_hour_exclusive`) and a typed value
(`usable_solar_fraction`, `reserve_kwh`, `reserve_percent_of_capacity`, `max_grid_kwh`, or `none`).
Deterministic code (`app/directives.py`) expands windows into the `hours` array, converts a percentage
reserve into kWh using the request's battery capacity, clamps and range-checks every number, and
emits the exact `structured_adjustment` shape from the Problem Statement. Nothing the judge checks
numerically is computed by the model.

**Output is schema-constrained.** Requests use `response_format: json_schema` (strict) where the
provider supports it and fall back to `json_object`; a malformed or truncated answer can therefore not
reach the optimizer. Anything that still fails validation degrades *that note* to `no_op` — the service
never invents a directive type and never returns 5xx because of model output.

**Providers and latency.** OpenAI-compatible chat endpoints; the provider named by `LLM_PROVIDER` is tried
first, the other configured one is the fallback. Each note is interpreted in its own concurrent request
(notes are independent by specification), and every request is *hedged*: if an attempt is silent for
`LLM_HEDGE_AFTER_S` (2.5 s) a second attempt starts in parallel and the first valid answer wins. One overall
deadline (`LLM_TIMEOUT_S`, 20 s) bounds everything, so a slow provider can never push a request past the
judge's 30 s limit.

| `LLM_PROVIDER` | Model(s) | Notes |
|---|---|---|
| `openai` (**judging primary**) | `OPENAI_MODEL`, default **`gpt-4o-mini`** | 100 % on every measured run (below). Strict JSON schema mode. |
| `groq` (**hedge / fallback**) | `GROQ_MODELS`, default `openai/gpt-oss-120b,openai/gpt-oss-20b,llama-3.3-70b-versatile` | gpt-oss-120b answers in 0.7–1.4 s but scored 44/45 on the paraphrase eval (read a "last month" maintenance note as today's) and returned HTTP 429 under four concurrent calls, so it backs OpenAI rather than leading. Tried in order; `reasoning_effort: low`. |

Configure **both** keys for judging: OpenAI answers first; if it is silent for 2.5 s or fails, the same
note is re-asked on Groq in parallel and the first valid answer wins. Measured with both keys set,
`LLM_PROVIDER=openai`: public cases 10/10 and 10/10 (p95 2.1 s), paraphrase eval 45/45 (p95 2.9 s),
every note answered by the primary on its first attempt.

**Measured with `gpt-4o-mini`** (this machine, one request per scenario, cache off):

| Check | Result |
|---|---|
| 10 public sample cases through the live API (`scripts/run_public_cases.py --directives=live`), two runs | **10/10** and **10/10**, p95 1.8 s / 2.2 s |
| 45-note paraphrase eval, 1 note per request (`scripts/run_eval.py`) | **45/45** exact on applies / type / hours / value, p95 2.0 s |
| 45-note paraphrase eval, 3 notes per request, two shuffles (`--batch 3`) | **45/45** and **45/45**, p95 2.0 s / 3.9 s |

Repeated scenarios (same notes and battery capacity) are served from an in-memory interpretation cache
without a model call. Outages are never cached.

---

## 3. Local quickstart (clean environment)

Requires Python 3.12+ and one LLM API key. Node is only needed if you want to rebuild the operator console.

```bash
git clone https://github.com/fairuz-anadi/gridWise.git
cd gridWise

python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env         # then put ONE real key in .env (never commit it; it is gitignored)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`.env` is read at startup. Minimum content for judging:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=<your key>
```

### Verify

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -s -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  --data @examples/sample-06.request.json
```

Expected: HTTP 200 with three `directive_interpretation` entries —
`solar_reduction {hours:[10,11], factor:0.5}`, `no_charge_window {hours:[14,15]}`, `no_op` —
and `total_cost_bdt` **34090.0**. The organizers' reference output is in
`examples/sample-06.expected.json` (equivalent optimal schedules are accepted; the cost and the
interpretation are what to compare).

Without an API key in `.env` the service still starts and answers 200, but every note comes back as
`no_op` ("Interpreter unavailable") and the cost is **31630.0** (no directives applied). That is the
designed safe failure, not a bug; add a key and restart to get the result above.

### Run all ten public sample cases against the running server

```bash
python scripts/run_public_cases.py --url http://localhost:8000
```

Expected last line: `10/10 passed, p95 <n> ms`. Each case is checked for HTTP 200, `scenario_id` echo,
interpretation equal to the reference (hours exact, numbers within 0.01), an independent replay of every
energy/battery rule against the *reference* directives (what the judge does), and cost equal to the
reference optimum within 0.01 BDT.

Other useful modes:

```bash
python scripts/run_public_cases.py --directives=reference   # optimizer + validator only, no model call
python scripts/run_eval.py --batch 3                        # paraphrase robustness eval (needs a key)
pytest -q                                                   # 91 offline tests (no key needed)
```

The operator console is served at `http://localhost:8000/` when `frontend/dist` exists (the Docker
image builds it; locally run `cd frontend && npm ci && npm run build`). It is not part of the judged
API — see `frontend/README.md`.

---

## 4. API contract

`GET /health` → `200 {"status": "ok"}` (ready within ~1 s of process start).

`POST /optimize-energy` accepts the Problem Statement §07 request and returns the §10 response,
field names exact. Status codes: **200** success · **400** malformed JSON or structurally invalid request
(`{"error": "invalid_request", "detail": [{"loc": [...], "msg": "..."}]}`) · **500** controlled internal
error (`{"error": "internal_error", "request_id": "..."}`, no stack trace, no secrets).

Request validation (all → 400): exactly 24 unique hours 0–23; 1–3 non-empty notes; all numbers finite
and ≥ 0; `minimum_energy_kwh ≤ initial_energy_kwh ≤ capacity_kwh` (otherwise no schedule can exist).

Pipeline per request: interpret notes (LLM → guardrails) → LP with directives applied → replay check
→ if the hard problem is infeasible or the replay fails, re-solve with directive constraints as soft
penalties while every base GridWise rule stays hard → replay check again → respond. The final plan
always satisfies energy balance, effective solar, battery bounds/rates and end-of-day neutrality.

---

## 5. Docker fallback

The image builds the console (Node stage) and the API (Python 3.12 slim), runs as a non-root user,
binds `0.0.0.0` on `$PORT` (default 8000) and contains no secrets — keys are passed at run time.

```bash
# Build locally
docker build -t gridwise:latest .

# Run (keys from your local .env, which is never copied into the image)
docker run --rm -p 8000:8000 --env-file .env gridwise:latest

curl http://localhost:8000/health
```

**Registry image (submission):** public on GitHub Container Registry, no login needed. Exposed port: 8000.

```bash
docker pull ghcr.io/fairuz-anadi/gridwise@sha256:d03732b87e6f604ac7ddd5f132b07ea13db0e3083394cb2e8b15d5117b8d9418
docker run --rm -p 8000:8000 -e LLM_PROVIDER=openai -e OPENAI_API_KEY=<key> ghcr.io/fairuz-anadi/gridwise@sha256:d03732b87e6f604ac7ddd5f132b07ea13db0e3083394cb2e8b15d5117b8d9418
curl http://localhost:8000/health
```

---

## 6. Environment variables

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `OPENAI_API_KEY` | one of the two keys | — | OpenAI key |
| `GROQ_API_KEY` | one of the two keys | — | Groq key |
| `LLM_PROVIDER` | no | `groq` | Which configured provider to try first (`openai` or `groq`); the other is the fallback |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | OpenAI model id |
| `GROQ_MODELS` | no | `openai/gpt-oss-120b,openai/gpt-oss-20b,llama-3.3-70b-versatile` | Groq models, tried in order |
| `LLM_TIMEOUT_S` | no | `20` | Overall deadline for the whole provider chain per request |
| `LLM_ATTEMPT_TIMEOUT_S` | no | `12` | Deadline for a single model call |
| `LLM_HEDGE_AFTER_S` | no | `2.5` | Start a parallel second attempt if the first is silent this long |
| `LLM_CACHE` | no | `1` | `0` disables the interpretation cache (used by the eval script) |
| `PORT` | no | `8000` | Listening port (hosting platforms inject it) |

Secret handling: keys are read from the environment or a local `.env`; `.env*` is gitignored and
dockerignored; error responses and logs never include request bodies, model prompts or key material.

---

## 7. Tests

```bash
pytest -q
```

91 tests, no network: request validation and status codes (`tests/test_api.py`), the LP against all ten
reference optima and directive application (`tests/test_optimizer.py`), the replay validator catching
each rule violation (`tests/test_validator.py`), and the guardrail layer against every malformed model
output shape — bad hours, midnight-crossing windows, NaN/∞, unknown types, missing or duplicate
indices, provider outage, cache behaviour (`tests/test_guardrails.py`).

---

## 8. Dependencies and credits

Runtime: FastAPI 0.141, Uvicorn 0.53, Pydantic 2.13, SciPy 1.18 (`linprog`, HiGHS), NumPy 2.5,
httpx 0.28, python-dotenv. Tests: pytest, pytest-asyncio. Console: React 19, TypeScript, Vite 8,
Recharts 3. Language models: OpenAI `gpt-4o-mini` (judging) with Groq gpt-oss / Llama as fallback.
Public sample cases © BUP CSE Fest 2026 organizers, used unchanged as test fixtures.
AI coding assistants (Claude Code) were used during development; the architecture, guardrail rules,
optimizer formulation and tests are the team's own work.

---

## 9. Known limitations

- The model can still misread a genuinely ambiguous note; the guardrails guarantee a *valid* plan in
  that case, not a *correct* interpretation. The eval set (`tests/eval/paraphrases.json`) is how we
  measure this — extend it when adding phrasing.
- If both providers are unreachable, every note degrades to `no_op` (explanation names the interpreter)
  and the plan is optimized under base rules only. The response is still 200 and valid.
- Overlapping `solar_reduction` notes multiply (never use more solar than any single note allows).
  Overlapping reserve / grid-cap notes take the stricter value.
- Notes with no time reference that clearly apply all day are interpreted as hours 0–23.
- The interpretation cache is per process and not shared across replicas.
