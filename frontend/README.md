# GridWise console (frontend)

React + TypeScript + Vite single-page console for the GridWise API. Owner: Samprity.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5174 — proxies /health and /optimize-energy to http://localhost:8000
npm run build      # -> frontend/dist, served by FastAPI at "/" in production
```

- `VITE_MOCK=1` in `frontend/.env.local` runs the console with no backend; responses come from
  `tests/fixtures/public_cases.json` (the same file the backend tests use).

## Structure

| Layer | Files | Role |
| --- | --- | --- |
| Contract | `src/types.ts`, `src/api.ts` | Mirrors `app/schemas.py` field-for-field; the only place that talks to the judged endpoints |
| Rules | `src/validate.ts`, `src/plan.ts` | Client-side mirror of the request rules and a replay of the Problem Statement energy/battery checks, so a broken plan is visible during a demo |
| Language | `src/humanize.ts` | Translates directives into operator language (`solar_reduction {hours:[10,11], factor:0.5}` → "Solar output reduced · 10 AM – 12 PM · about 50% of forecast") |
| Views | `src/views/*` | Overview (situation + instructions + CTA), Scenario (all editable inputs, raw JSON), Schedule (result, charts, recommendations, table, developer details) |
| Components | `src/components/*` | `AppShell`, `MetricCard`, `EnergyChart`, `BatteryChart`, `OperatorInstructions` / `InstructionCard` (incl. the wording-comparison demo), `OptimizationProgress`, `PlanSummary`, `Recommendations`, `ScheduleTable`, `AdvancedDetails`, `ErrorState`, `ScenarioEditor` |

Technical detail is never removed, only moved behind disclosure: each instruction card expands to the
raw directive, the schedule table and raw request/response JSON live under "View full 24-hour schedule"
and "Advanced · developer details".

## Contract notes for the backend

- A note the interpreter could not process must come back as `no_op` with an explanation containing the
  word "interpreter" — the console uses that to show the "AI interpretation temporarily unavailable" state.
- 400/422 bodies in FastAPI's `{detail: [{loc, msg}]}` shape are rendered as field-level messages.
