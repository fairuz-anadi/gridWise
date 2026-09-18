// Mirrors app/schemas.py exactly. Field names are judged byte-for-byte; do not rename.

export interface HourInput {
  hour: number
  demand_kwh: number
  solar_kwh: number
  tariff_bdt_per_kwh: number
}

export interface Battery {
  capacity_kwh: number
  initial_energy_kwh: number
  minimum_energy_kwh: number
  max_charge_kwh_per_hour: number
  max_discharge_kwh_per_hour: number
}

export interface Scenario {
  scenario_id: string
  operator_notes: string[]
  hours: HourInput[]
  battery: Battery
}

export type DirectiveType =
  | 'solar_reduction'
  | 'minimum_battery_reserve'
  | 'no_charge_window'
  | 'no_discharge_window'
  | 'max_grid_window'
  | 'no_op'

export interface StructuredAdjustment {
  hours: number[]
  factor?: number
  minimum_energy_kwh?: number
  max_grid_kwh?: number
}

export interface Directive {
  note_index: number
  applies: boolean
  directive_type: DirectiveType
  structured_adjustment: StructuredAdjustment | null
  explanation: string
}

export type BatteryAction = 'charge' | 'discharge' | 'idle'

export interface HourPlan {
  hour: number
  grid_kwh: number
  solar_used_kwh: number
  battery_action: BatteryAction
  battery_kwh: number
  battery_energy_after_kwh: number
}

export interface OptimizeResponse {
  scenario_id: string
  directive_interpretation: Directive[]
  hourly_plan: HourPlan[]
  total_grid_kwh: number
  total_cost_bdt: number
  peak_grid_kwh: number
  plan_summary: string
}

export interface SampleCase {
  id: string
  label: string
  input: Scenario
  expected_output: OptimizeResponse
  rationale: string
}

export const DIRECTIVE_LABEL: Record<DirectiveType, string> = {
  solar_reduction: 'Solar reduction',
  minimum_battery_reserve: 'Battery reserve',
  no_charge_window: 'No charging',
  no_discharge_window: 'No discharging',
  max_grid_window: 'Grid cap',
  no_op: 'No effect',
}
