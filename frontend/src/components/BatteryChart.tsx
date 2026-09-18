import { Area, CartesianGrid, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmt, hourLabel } from '../humanize'
import { requiredReserve, reserveMargin } from '../plan'
import type { OptimizeResponse, Scenario } from '../types'

const AXIS = { fontFamily: 'Manrope, sans-serif', fontSize: 12, fill: 'var(--dim)' } as const
const hh = (h: number) => String(h).padStart(2, '0')

interface TipProps {
  active?: boolean
  label?: string | number
  payload?: Array<{ payload?: Record<string, number> }>
}

function Tip({ active, label, payload }: TipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload ?? {}
  const h = Number(label)
  const flow = d.flow ?? 0
  return (
    <div className="chart-tip">
      <div className="h">
        {hourLabel(h)} – {hourLabel(h + 1)}
      </div>
      <div className="row">
        <span>
          <i style={{ '--c': 'var(--mint)' } as React.CSSProperties} />
          Battery level
        </span>
        <b>{fmt(d.energy ?? 0)} kWh</b>
      </div>
      <div className="row">
        <span>
          <i style={{ '--c': 'var(--red)' } as React.CSSProperties} />
          Required minimum
        </span>
        <b>{fmt(d.reserve ?? 0)} kWh</b>
      </div>
      {flow !== 0 && (
        <div className="row">
          <span>
            <i style={{ '--c': flow > 0 ? 'var(--plum)' : 'var(--lime)' } as React.CSSProperties} />
            {flow > 0 ? 'Charging' : 'Discharging'}
          </span>
          <b>{fmt(Math.abs(flow))} kWh</b>
        </div>
      )}
    </div>
  )
}

export function BatteryChart({ scenario, result, height = 260 }: { scenario: Scenario; result: OptimizeResponse; height?: number }) {
  const b = scenario.battery
  const reserve = requiredReserve(scenario, result.directive_interpretation)
  const data = result.hourly_plan.map((p, i) => ({
    hour: p.hour,
    energy: p.battery_energy_after_kwh,
    reserve: reserve[i],
    flow: p.battery_action === 'charge' ? p.battery_kwh : p.battery_action === 'discharge' ? -p.battery_kwh : 0,
  }))
  const { margin, lowest } = reserveMargin(scenario, result)

  return (
    <div className="card chart-card">
      <div className="card-head">
        <div>
          <h3>Battery forecast</h3>
          <div className="small muted">
            Lowest level today <b style={{ color: 'var(--text)' }}>{fmt(lowest)} kWh</b> —{' '}
            {margin >= -0.011 ? 'never below the required reserve' : <span style={{ color: 'var(--red)' }}>breaches the required reserve</span>}
          </div>
        </div>
        <div className="legend">
          <span>
            <i style={{ '--c': 'var(--mint)' } as React.CSSProperties} />
            level
          </span>
          <span>
            <i style={{ '--c': 'rgba(239,111,98,0.5)' } as React.CSSProperties} />
            reserve
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 10, right: 6, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="battFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--mint)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--mint)" stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="hour" type="category" tickFormatter={(h) => hh(Number(h))} interval={2} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--border)' }} />
          <YAxis yAxisId="kwh" domain={[0, b.capacity_kwh]} tick={AXIS} tickLine={false} axisLine={false} width={44} />
          <Tooltip content={<Tip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
          <ReferenceLine yAxisId="kwh" y={b.capacity_kwh} stroke="var(--border-strong)" strokeDasharray="3 4" label={{ value: 'capacity', ...AXIS, position: 'insideTopRight' }} />
          <ReferenceLine yAxisId="kwh" y={b.initial_energy_kwh} stroke="var(--border-strong)" strokeDasharray="2 5" label={{ value: 'start & end level', ...AXIS, position: 'insideBottomRight' }} />
          <Area yAxisId="kwh" type="stepAfter" dataKey="reserve" stroke="rgba(239,111,98,0.7)" strokeDasharray="4 3" strokeWidth={1.5} fill="rgba(239,111,98,0.12)" isAnimationActive={false} />
          <Area yAxisId="kwh" type="monotone" dataKey="energy" stroke="var(--mint)" strokeWidth={2.4} fill="url(#battFill)" dot={{ r: 2.5, fill: 'var(--mint)', strokeWidth: 0 }} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
