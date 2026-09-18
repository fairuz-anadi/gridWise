import type { Scenario } from './types'

/**
 * Client-side mirror of the structural rules in Problem Statement §07, so the console can
 * point at the exact field before a request is sent. The server remains the authority.
 * Keys are dotted paths matching what FastAPI/Pydantic returns in `detail[].loc`.
 */
export function validateScenario(s: Scenario): Record<string, string> {
  const errs: Record<string, string> = {}

  if (!s.scenario_id.trim()) errs['scenario_id'] = 'Required'

  if (s.operator_notes.length < 1 || s.operator_notes.length > 3) {
    errs['operator_notes'] = 'Provide 1 to 3 notes'
  }
  s.operator_notes.forEach((n, i) => {
    if (!n.trim()) errs[`operator_notes.${i}`] = 'Note cannot be empty'
  })

  if (s.hours.length !== 24) errs['hours'] = `Need exactly 24 hours, have ${s.hours.length}`
  const seen = new Set<number>()
  s.hours.forEach((h, i) => {
    if (!Number.isInteger(h.hour) || h.hour < 0 || h.hour > 23) errs[`hours.${i}.hour`] = '0–23'
    if (seen.has(h.hour)) errs[`hours.${i}.hour`] = 'Duplicate hour'
    seen.add(h.hour)
    for (const k of ['demand_kwh', 'solar_kwh', 'tariff_bdt_per_kwh'] as const) {
      const v = h[k]
      if (!Number.isFinite(v) || v < 0) errs[`hours.${i}.${k}`] = 'Must be ≥ 0'
    }
  })

  const b = s.battery
  for (const k of Object.keys(b) as (keyof typeof b)[]) {
    if (!Number.isFinite(b[k]) || b[k] < 0) errs[`battery.${k}`] = 'Must be ≥ 0'
  }
  if (b.minimum_energy_kwh > b.capacity_kwh) errs['battery.minimum_energy_kwh'] = 'Exceeds capacity'
  if (b.initial_energy_kwh > b.capacity_kwh) errs['battery.initial_energy_kwh'] = 'Exceeds capacity'
  if (b.initial_energy_kwh < b.minimum_energy_kwh) errs['battery.initial_energy_kwh'] = 'Below minimum reserve'

  return errs
}
