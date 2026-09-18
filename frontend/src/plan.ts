import type { BatteryAction, Directive, HourPlan, OptimizeResponse, Scenario } from './types'

/** Effective solar per hour after solar_reduction directives, computed client-side for display. */
export function effectiveSolar(scenario: Scenario, directives: Directive[]): number[] {
  const solar = scenario.hours.map((h) => h.solar_kwh)
  for (const d of directives) {
    if (d.directive_type === 'solar_reduction' && d.applies && d.structured_adjustment?.factor !== undefined) {
      for (const h of d.structured_adjustment.hours) solar[h] *= d.structured_adjustment.factor
    }
  }
  return solar
}

/** Required minimum battery energy per hour: base reserve raised by any minimum_battery_reserve directive. */
export function requiredReserve(scenario: Scenario, directives: Directive[]): number[] {
  const out = scenario.hours.map(() => scenario.battery.minimum_energy_kwh)
  for (const d of directives) {
    if (d.directive_type === 'minimum_battery_reserve' && d.applies && d.structured_adjustment?.minimum_energy_kwh !== undefined) {
      for (const h of d.structured_adjustment.hours) out[h] = Math.max(out[h], d.structured_adjustment.minimum_energy_kwh)
    }
  }
  return out
}

/** Smallest gap between battery level and that hour's required reserve. Negative means a breach. */
export function reserveMargin(scenario: Scenario, response: OptimizeResponse): { margin: number; lowest: number; floorMax: number } {
  const reserve = requiredReserve(scenario, response.directive_interpretation)
  let margin = Infinity
  let lowest = Infinity
  response.hourly_plan.forEach((p, i) => {
    margin = Math.min(margin, p.battery_energy_after_kwh - (reserve[i] ?? 0))
    lowest = Math.min(lowest, p.battery_energy_after_kwh)
  })
  return { margin, lowest, floorMax: Math.max(...reserve) }
}

export interface BatteryBlock {
  action: Exclude<BatteryAction, 'idle'>
  from: number
  /** exclusive */
  to: number
  kwh: number
  /** average tariff over the block, BDT/kWh */
  avgTariff: number
}

/** Contiguous runs of charging / discharging in a returned plan, largest first. */
export function batteryBlocks(scenario: Scenario, plan: HourPlan[]): BatteryBlock[] {
  const blocks: BatteryBlock[] = []
  let cur: BatteryBlock | null = null
  let tariffSum = 0
  const flush = () => {
    if (cur) {
      cur.avgTariff = tariffSum / (cur.to - cur.from)
      blocks.push(cur)
    }
    cur = null
    tariffSum = 0
  }
  plan.forEach((p, i) => {
    const tariff = scenario.hours[i]?.tariff_bdt_per_kwh ?? 0
    if (p.battery_action === 'idle' || p.battery_kwh <= 0) {
      flush()
      return
    }
    if (cur && cur.action === p.battery_action && cur.to === p.hour) {
      cur.to = p.hour + 1
      cur.kwh += p.battery_kwh
      tariffSum += tariff
    } else {
      flush()
      cur = { action: p.battery_action, from: p.hour, to: p.hour + 1, kwh: p.battery_kwh, avgTariff: 0 }
      tariffSum = tariff
    }
  })
  flush()
  return blocks.sort((a, b) => b.kwh - a.kwh)
}

export function scenarioTotals(s: Scenario) {
  const demand = s.hours.reduce((a, h) => a + (Number.isFinite(h.demand_kwh) ? h.demand_kwh : 0), 0)
  const solar = s.hours.reduce((a, h) => a + (Number.isFinite(h.solar_kwh) ? h.solar_kwh : 0), 0)
  const tariffs = s.hours.map((h) => h.tariff_bdt_per_kwh).filter(Number.isFinite)
  const peakHour = s.hours.reduce((best, h) => (h.tariff_bdt_per_kwh > (best?.tariff_bdt_per_kwh ?? -1) ? h : best), s.hours[0])
  return { demand, solar, tariffMin: Math.min(...tariffs), tariffMax: Math.max(...tariffs), peakHour: peakHour?.hour ?? 0 }
}

/**
 * Client-side replay of Problem Statement §9/§11. The server's validator is authoritative; this
 * exists so a broken plan is visible during a demo rather than after it. Returns violation messages.
 */
export function clientReplay(s: Scenario, r: OptimizeResponse): string[] {
  const out: string[] = []
  const tol = 0.011
  const b = s.battery
  const eff = effectiveSolar(s, r.directive_interpretation)
  const reserve = requiredReserve(s, r.directive_interpretation)
  const noCharge = new Set<number>()
  const noDischarge = new Set<number>()
  const gridCap = new Map<number, number>()
  for (const d of r.directive_interpretation) {
    if (!d.applies || !d.structured_adjustment) continue
    const a = d.structured_adjustment
    for (const h of a.hours) {
      if (d.directive_type === 'no_charge_window') noCharge.add(h)
      if (d.directive_type === 'no_discharge_window') noDischarge.add(h)
      if (d.directive_type === 'max_grid_window' && a.max_grid_kwh !== undefined) gridCap.set(h, Math.min(gridCap.get(h) ?? Infinity, a.max_grid_kwh))
    }
  }
  if (r.hourly_plan.length !== 24) out.push(`Plan has ${r.hourly_plan.length} hours instead of 24`)
  let E = b.initial_energy_kwh
  let cost = 0
  let grid = 0
  let peak = 0
  r.hourly_plan.forEach((p, i) => {
    const h = s.hours[i]
    if (!h) return
    const ch = p.battery_action === 'charge' ? p.battery_kwh : 0
    const dis = p.battery_action === 'discharge' ? p.battery_kwh : 0
    const H = `${String(p.hour).padStart(2, '0')}:00`
    if (p.battery_action === 'idle' && p.battery_kwh !== 0) out.push(`${H}: idle but battery_kwh is ${p.battery_kwh}`)
    if (Math.abs(p.grid_kwh + p.solar_used_kwh + dis - h.demand_kwh - ch) > tol) out.push(`${H}: supply does not equal demand`)
    if (p.solar_used_kwh > eff[i] + tol) out.push(`${H}: uses ${p.solar_used_kwh} kWh solar but only ${eff[i].toFixed(1)} available`)
    if (ch > b.max_charge_kwh_per_hour + tol) out.push(`${H}: charges faster than the battery allows`)
    if (dis > b.max_discharge_kwh_per_hour + tol) out.push(`${H}: discharges faster than the battery allows`)
    if (noCharge.has(p.hour) && ch > tol) out.push(`${H}: charges during a no-charging window`)
    if (noDischarge.has(p.hour) && dis > tol) out.push(`${H}: discharges during a no-discharging window`)
    if (gridCap.has(p.hour) && p.grid_kwh > gridCap.get(p.hour)! + tol) out.push(`${H}: grid import ${p.grid_kwh} exceeds the ${gridCap.get(p.hour)} kWh cap`)
    E = E + ch - dis
    if (Math.abs(E - p.battery_energy_after_kwh) > tol) out.push(`${H}: battery level does not follow from the previous hour`)
    if (p.battery_energy_after_kwh < reserve[i] - tol) out.push(`${H}: battery below the required ${reserve[i]} kWh reserve`)
    if (p.battery_energy_after_kwh > b.capacity_kwh + tol) out.push(`${H}: battery above capacity`)
    if (p.grid_kwh < -tol || p.solar_used_kwh < -tol || p.battery_kwh < -tol) out.push(`${H}: negative energy value`)
    cost += p.grid_kwh * h.tariff_bdt_per_kwh
    grid += p.grid_kwh
    peak = Math.max(peak, p.grid_kwh)
  })
  const last = r.hourly_plan[r.hourly_plan.length - 1]
  if (last && Math.abs(last.battery_energy_after_kwh - b.initial_energy_kwh) > tol) out.push(`Battery ends the day at ${last.battery_energy_after_kwh} kWh instead of the starting ${b.initial_energy_kwh} kWh`)
  if (Math.abs(cost - r.total_cost_bdt) > tol) out.push(`Reported cost ${r.total_cost_bdt} differs from the recomputed ${cost.toFixed(2)}`)
  if (Math.abs(grid - r.total_grid_kwh) > tol) out.push(`Reported grid energy ${r.total_grid_kwh} differs from the recomputed ${grid.toFixed(2)}`)
  if (Math.abs(peak - r.peak_grid_kwh) > tol) out.push(`Reported peak ${r.peak_grid_kwh} differs from the recomputed ${peak}`)
  return out
}
