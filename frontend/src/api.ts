import { SAMPLES } from './samples'
import type { OptimizeResponse, Scenario } from './types'

// Set VITE_MOCK=1 (frontend/.env.local) to run the console with no backend: responses come
// from the public case pack. Any scenario whose id matches a sample returns that sample's
// expected_output after a short delay; anything else returns a no_op plan built from the input.
const MOCK = import.meta.env.VITE_MOCK === '1'
const REQUEST_TIMEOUT_MS = 35_000 // judge limit is 30 s; give the server a little slack

export class ApiError extends Error {
  status: number
  /** Field-level messages from Pydantic (422/400) keyed by dotted path, when present. */
  fields: Record<string, string>
  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

export async function checkHealth(): Promise<boolean> {
  if (MOCK) return true
  try {
    const r = await fetch('/health', { signal: AbortSignal.timeout(5_000) })
    if (!r.ok) return false
    const body = (await r.json()) as { status?: string }
    return body.status === 'ok'
  } catch {
    return false
  }
}

export async function optimize(scenario: Scenario, signal?: AbortSignal): Promise<OptimizeResponse> {
  if (MOCK) return mockOptimize(scenario)

  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout

  let r: Response
  try {
    r = await fetch('/optimize-energy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(scenario),
      signal: combined,
    })
  } catch {
    if (signal?.aborted) throw new ApiError(0, 'Cancelled')
    if (timeout.aborted) throw new ApiError(0, 'The server did not answer within 35 seconds.')
    throw new ApiError(0, 'Could not reach the server. Is the API running?')
  }

  if (!r.ok) throw await toApiError(r)
  return (await r.json()) as OptimizeResponse
}

async function toApiError(r: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await r.json()
  } catch {
    /* non-JSON error body */
  }
  // FastAPI validation errors: {detail: [{loc: [...], msg: "..."}]}
  if (body && typeof body === 'object' && Array.isArray((body as { detail?: unknown }).detail)) {
    const fields: Record<string, string> = {}
    for (const item of (body as { detail: Array<{ loc?: unknown[]; msg?: string }> }).detail) {
      const path = (item.loc ?? []).filter((p) => p !== 'body').join('.')
      fields[path] = item.msg ?? 'invalid'
    }
    return new ApiError(r.status, 'The request was rejected. Fix the highlighted fields.', fields)
  }
  const detail =
    body && typeof body === 'object' && typeof (body as { detail?: unknown }).detail === 'string'
      ? (body as { detail: string }).detail
      : body && typeof body === 'object' && typeof (body as { error?: unknown }).error === 'string'
        ? (body as { error: string }).error
        : `Server returned HTTP ${r.status}`
  return new ApiError(r.status, detail)
}

// ---------- mock ----------

async function mockOptimize(scenario: Scenario): Promise<OptimizeResponse> {
  await new Promise((res) => setTimeout(res, 1800))
  const hit = SAMPLES.find((c) => c.id === scenario.scenario_id)
  if (hit && JSON.stringify(hit.input.operator_notes) === JSON.stringify(scenario.operator_notes)) {
    return structuredClone(hit.expected_output)
  }
  if (hit) {
    // notes were edited: keep the reference plan but re-label the interpretation so the
    // paraphrase panel has something to diff against in mock mode
    const out = structuredClone(hit.expected_output)
    out.directive_interpretation = out.directive_interpretation.map((d) => ({
      ...d,
      explanation: `(mock) ${d.explanation}`,
    }))
    return out
  }
  return noOpPlan(scenario)
}

/** A trivially valid plan: grid covers everything, battery idle all day. */
function noOpPlan(s: Scenario): OptimizeResponse {
  const hourly_plan = s.hours.map((h) => {
    const solar_used_kwh = Math.min(h.solar_kwh, h.demand_kwh)
    return {
      hour: h.hour,
      grid_kwh: round(h.demand_kwh - solar_used_kwh),
      solar_used_kwh: round(solar_used_kwh),
      battery_action: 'idle' as const,
      battery_kwh: 0,
      battery_energy_after_kwh: s.battery.initial_energy_kwh,
    }
  })
  const total_grid_kwh = round(hourly_plan.reduce((a, p) => a + p.grid_kwh, 0))
  const total_cost_bdt = round(
    hourly_plan.reduce((a, p, i) => a + p.grid_kwh * s.hours[i].tariff_bdt_per_kwh, 0),
  )
  return {
    scenario_id: s.scenario_id,
    directive_interpretation: s.operator_notes.map((_, i) => ({
      note_index: i,
      applies: false,
      directive_type: 'no_op',
      structured_adjustment: null,
      explanation: '(mock) Interpreter not available.',
    })),
    hourly_plan,
    total_grid_kwh,
    total_cost_bdt,
    peak_grid_kwh: Math.max(...hourly_plan.map((p) => p.grid_kwh)),
    plan_summary: '(mock) Grid supplies all demand; battery idle.',
  }
}

function round(n: number): number {
  return Math.round(n * 10000) / 10000
}
