import type { Battery, Directive, DirectiveType } from './types'

/** 0 → "12 AM", 13 → "1 PM", 24 → "12 AM" (end of day). */
export function hourLabel(h: number): string {
  const x = ((h % 24) + 24) % 24
  if (x === 0) return '12 AM'
  if (x === 12) return '12 PM'
  return x < 12 ? `${x} AM` : `${x - 12} PM`
}

/** Contiguous hour runs as [from, toExclusive] pairs. */
export function hourBlocks(hours: number[]): [number, number][] {
  const hs = [...new Set(hours)].sort((a, b) => a - b)
  const out: [number, number][] = []
  for (const h of hs) {
    const last = out[out.length - 1]
    if (last && last[1] === h) last[1] = h + 1
    else out.push([h, h + 1])
  }
  return out
}

/** "10 AM – 12 PM", or "2 PM – 4 PM, 6 PM – 9 PM" for split windows. */
export function rangeLabel(hours: number[]): string {
  return hourBlocks(hours)
    .map(([a, b]) => `${hourLabel(a)} – ${hourLabel(b)}`)
    .join(', ')
}

export type IconName = 'sun' | 'plug' | 'battery' | 'shield' | 'grid' | 'dot' | 'bolt' | 'check' | 'alert'

export interface HumanDirective {
  icon: IconName
  title: string
  /** e.g. "10 AM – 12 PM"; null for notes with no effect */
  range: string | null
  /** short factual line derived from the structured adjustment */
  detail: string
  muted: boolean
}

const TITLES: Record<DirectiveType, string> = {
  solar_reduction: 'Solar output reduced',
  minimum_battery_reserve: 'Battery reserve required',
  no_charge_window: 'Battery charging unavailable',
  no_discharge_window: 'Battery discharging unavailable',
  max_grid_window: 'Grid import capped',
  no_op: 'Not relevant to today’s schedule',
}

const ICONS: Record<DirectiveType, IconName> = {
  solar_reduction: 'sun',
  minimum_battery_reserve: 'shield',
  no_charge_window: 'plug',
  no_discharge_window: 'battery',
  max_grid_window: 'grid',
  no_op: 'dot',
}

/** Translate a machine-checkable directive into operator language. Values come only from the directive itself. */
export function describeDirective(d: Directive, battery?: Battery): HumanDirective {
  const a = d.structured_adjustment
  const base: HumanDirective = { icon: ICONS[d.directive_type], title: TITLES[d.directive_type], range: null, detail: '', muted: false }
  if (d.directive_type === 'no_op' || !d.applies || !a) {
    return { ...base, icon: 'dot', title: TITLES.no_op, detail: 'This instruction does not affect today’s energy plan.', muted: true }
  }
  const range = rangeLabel(a.hours)
  switch (d.directive_type) {
    case 'solar_reduction': {
      const pct = a.factor !== undefined ? Math.round(a.factor * 100) : undefined
      return { ...base, range, detail: pct !== undefined ? `Usable solar is limited to about ${pct}% of the forecast.` : 'Usable solar is reduced.' }
    }
    case 'minimum_battery_reserve': {
      const kwh = a.minimum_energy_kwh
      const pct = kwh !== undefined && battery && battery.capacity_kwh > 0 ? Math.round((kwh / battery.capacity_kwh) * 100) : undefined
      return { ...base, range, detail: kwh !== undefined ? `Keep at least ${fmt(kwh)} kWh stored${pct !== undefined ? ` (${pct}% of capacity)` : ''}.` : 'Keep a higher reserve.' }
    }
    case 'no_charge_window':
      return { ...base, range, detail: 'The battery will not be charged during this window.' }
    case 'no_discharge_window':
      return { ...base, range, detail: 'The battery will not be discharged during this window.' }
    case 'max_grid_window':
      return { ...base, range, detail: a.max_grid_kwh !== undefined ? `Grid import stays at or below ${fmt(a.max_grid_kwh)} kWh per hour.` : 'Grid import is limited.' }
    default:
      return base
  }
}

/** Compact value summary used by the paraphrase comparison. */
export function directiveValue(d: Directive): string {
  const a = d.structured_adjustment
  if (!a) return '—'
  if (a.factor !== undefined) return `${Math.round(a.factor * 100)}% usable solar`
  if (a.minimum_energy_kwh !== undefined) return `${fmt(a.minimum_energy_kwh)} kWh reserve`
  if (a.max_grid_kwh !== undefined) return `${fmt(a.max_grid_kwh)} kWh cap`
  return '—'
}

export function sameDirective(a: Directive, b: Directive) {
  const ah = a.structured_adjustment?.hours ?? []
  const bh = b.structured_adjustment?.hours ?? []
  const type = a.directive_type === b.directive_type && a.applies === b.applies
  const hours = ah.length === bh.length && ah.every((h, i) => h === bh[i])
  const value = directiveValue(a) === directiveValue(b)
  return { type, hours, value, all: type && hours && value }
}

export function fmt(n: number, maxFrac = 1): string {
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString(undefined, { maximumFractionDigits: Number.isInteger(n) ? 0 : maxFrac })
}

export function greeting(d = new Date()): string {
  const h = d.getHours()
  if (h < 5) return 'Good night'
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

/** Marker the backend uses when the language model could not process a note (contract with app/directives.py). */
export function isDegraded(d: Directive): boolean {
  return d.directive_type === 'no_op' && /\binterpreter\b/i.test(d.explanation)
}
