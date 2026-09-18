import { Area, Bar, CartesianGrid, ComposedChart, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { hourBlocks, hourLabel } from '../humanize'
import { effectiveSolar } from '../plan'
import type { Directive, OptimizeResponse, Scenario } from '../types'

const AXIS = { fontFamily: 'Inter Tight, sans-serif', fontSize: 12, fill: 'var(--chart-axis)' } as const
const hh = (h: number) => String(h).padStart(2, '0')

interface TipRow {
  key: string
  label: string
  color: string
  unit: string
}

interface TipProps {
  active?: boolean
  label?: string | number
  payload?: Array<{ payload?: Record<string, number | string> }>
  rows: TipRow[]
}

/** Tooltip that speaks operator language: "Grid import 130 kWh" rather than a dataKey. */
function Tip({ active, label, payload, rows }: TipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload ?? {}
  const h = Number(label)
  return (
    <div className="chart-tip">
      <div className="h">
        {hourLabel(h)} – {hourLabel(h + 1)}
      </div>
      {rows.map((r) => {
        const v = d[r.key]
        if (typeof v !== 'number' || (v === 0 && r.key !== 'tariff' && r.key !== 'demand')) return null
        return (
          <div className="row" key={r.key}>
            <span>
              <i style={{ '--c': r.color } as React.CSSProperties} />
              {r.label}
            </span>
            <b>
              {v.toLocaleString(undefined, { maximumFractionDigits: 1 })} {r.unit}
            </b>
          </div>
        )
      })}
    </div>
  )
}

function DirectiveBands({ directives, yAxisId }: { directives: Directive[]; yAxisId: string }) {
  const bands: { from: number; to: number; color: string }[] = []
  for (const d of directives) {
    if (!d.applies || !d.structured_adjustment) continue
    // Event windows are pre-tinted tokens (color + opacity) so each theme tunes its own strength.
    const color =
      d.directive_type === 'solar_reduction'
        ? 'var(--chart-event-solar)'
        : d.directive_type === 'max_grid_window'
          ? 'var(--chart-event-grid)'
          : d.directive_type === 'minimum_battery_reserve'
            ? 'var(--chart-event-reserve)'
            : 'var(--chart-event-battery)'
    for (const [a, b] of hourBlocks(d.structured_adjustment.hours)) bands.push({ from: a, to: b - 1, color })
  }
  return (
    <>
      {bands.map((b, i) => (
        <ReferenceArea key={i} x1={b.from} x2={b.to} yAxisId={yAxisId} fill={b.color} fillOpacity={1} ifOverflow="extendDomain" />
      ))}
    </>
  )
}

/** Input-side view: what the day looks like before any plan — demand, forecast solar, tariff. */
export function ScenarioEnergyChart({ scenario, directives = [] }: { scenario: Scenario; directives?: Directive[] }) {
  const eff = effectiveSolar(scenario, directives)
  const data = scenario.hours.map((h, i) => ({
    hour: h.hour,
    demand: fin(h.demand_kwh),
    solar: fin(eff[i]),
    tariff: fin(h.tariff_bdt_per_kwh),
  }))
  const rows: TipRow[] = [
    { key: 'demand', label: 'Expected demand', color: 'var(--chart-demand)', unit: 'kWh' },
    { key: 'solar', label: 'Solar available', color: 'var(--chart-solar)', unit: 'kWh' },
    { key: 'tariff', label: 'Grid price', color: 'var(--chart-price)', unit: 'BDT/kWh' },
  ]
  return (
    <div className="card chart-card">
      <div className="card-head">
        <div>
          <h3>Today’s energy</h3>
          <div className="small muted">Hourly demand, available solar and grid price</div>
        </div>
        <div className="legend">
          <span>
            <i className="line" style={{ '--c': 'var(--chart-demand)' } as React.CSSProperties} />
            demand
          </span>
          <span>
            <i style={{ '--c': 'var(--chart-solar)' } as React.CSSProperties} />
            solar
          </span>
          <span>
            <i className="dash" style={{ '--c': 'var(--chart-price)' } as React.CSSProperties} />
            price
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 10, right: 6, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="solarFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-solar-fill-top)" />
              <stop offset="100%" stopColor="var(--chart-solar-fill-bottom)" />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--chart-gridline)" vertical={false} />
          <DirectiveBands directives={directives} yAxisId="kwh" />
          <XAxis dataKey="hour" type="number" domain={[0, 23]} ticks={[0, 3, 6, 9, 12, 15, 18, 21]} tickFormatter={(h) => hh(Number(h))} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--chart-gridline)' }} />
          <YAxis yAxisId="kwh" tick={AXIS} tickLine={false} axisLine={false} width={44} />
          <YAxis yAxisId="bdt" orientation="right" tick={{ ...AXIS, fill: 'var(--chart-price)' }} tickLine={false} axisLine={false} width={40} />
          <Tooltip content={<Tip rows={rows} />} cursor={{ stroke: 'var(--chart-axis)' }} />
          <Area yAxisId="kwh" type="monotone" dataKey="solar" stroke="var(--chart-solar)" strokeWidth={1.5} fill="url(#solarFill)" isAnimationActive={false} />
          <Line yAxisId="kwh" type="monotone" dataKey="demand" stroke="var(--chart-demand)" strokeWidth={2.2} dot={false} isAnimationActive={false} />
          <Line yAxisId="bdt" type="monotone" dataKey="tariff" stroke="var(--chart-price)" strokeWidth={1.8} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Result view: how each hour is supplied under the optimized plan. */
export function PlanEnergyChart({ scenario, result }: { scenario: Scenario; result: OptimizeResponse }) {
  const data = result.hourly_plan.map((p, i) => ({
    hour: p.hour,
    grid: p.grid_kwh,
    solar: p.solar_used_kwh,
    discharge: p.battery_action === 'discharge' ? p.battery_kwh : 0,
    charge: p.battery_action === 'charge' ? p.battery_kwh : 0,
    demand: scenario.hours[i]?.demand_kwh ?? 0,
    tariff: scenario.hours[i]?.tariff_bdt_per_kwh ?? 0,
  }))
  const rows: TipRow[] = [
    { key: 'demand', label: 'Demand', color: 'var(--chart-demand)', unit: 'kWh' },
    { key: 'grid', label: 'Grid import', color: 'var(--chart-grid)', unit: 'kWh' },
    { key: 'solar', label: 'Solar used', color: 'var(--chart-solar)', unit: 'kWh' },
    { key: 'discharge', label: 'From battery', color: 'var(--chart-battery)', unit: 'kWh' },
    { key: 'charge', label: 'Into battery', color: 'var(--chart-charge)', unit: 'kWh' },
    { key: 'tariff', label: 'Grid price', color: 'var(--chart-price)', unit: 'BDT/kWh' },
  ]
  return (
    <div className="card chart-card">
      <div className="card-head">
        <div>
          <h3>Today’s optimized energy plan</h3>
          <div className="small muted">Where each hour’s energy comes from. Bars above the demand line are energy stored into the battery.</div>
        </div>
        <div className="legend">
          <span>
            <i style={{ '--c': 'var(--chart-grid)' } as React.CSSProperties} />
            grid
          </span>
          <span>
            <i style={{ '--c': 'var(--chart-solar)' } as React.CSSProperties} />
            solar
          </span>
          <span>
            <i style={{ '--c': 'var(--chart-battery)' } as React.CSSProperties} />
            battery
          </span>
          <span>
            <i className="line" style={{ '--c': 'var(--chart-demand)' } as React.CSSProperties} />
            demand
          </span>
          <span>
            <i className="dash" style={{ '--c': 'var(--chart-price)' } as React.CSSProperties} />
            price
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={data} margin={{ top: 10, right: 6, left: 0, bottom: 0 }} barCategoryGap="22%">
          <CartesianGrid stroke="var(--chart-gridline)" vertical={false} />
          <DirectiveBands directives={result.directive_interpretation} yAxisId="kwh" />
          <XAxis dataKey="hour" type="category" tickFormatter={(h) => hh(Number(h))} interval={2} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--chart-gridline)' }} />
          <YAxis yAxisId="kwh" tick={AXIS} tickLine={false} axisLine={false} width={44} />
          <YAxis yAxisId="bdt" orientation="right" tick={{ ...AXIS, fill: 'var(--chart-price)' }} tickLine={false} axisLine={false} width={40} />
          <Tooltip content={<Tip rows={rows} />} cursor={{ fill: 'var(--chart-cursor)' }} />
          <Bar yAxisId="kwh" dataKey="grid" stackId="s" fill="var(--chart-grid)" isAnimationActive={false} />
          <Bar yAxisId="kwh" dataKey="solar" stackId="s" fill="var(--chart-solar)" isAnimationActive={false} />
          <Bar yAxisId="kwh" dataKey="discharge" stackId="s" fill="var(--chart-battery)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Line yAxisId="kwh" type="stepAfter" dataKey="demand" stroke="var(--chart-demand)" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line yAxisId="bdt" type="monotone" dataKey="tariff" stroke="var(--chart-price)" strokeWidth={1.8} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function fin(n: number): number {
  return Number.isFinite(n) ? n : 0
}
