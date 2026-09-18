import { fmt } from '../humanize'
import { effectiveSolar } from '../plan'
import type { OptimizeResponse, Scenario } from '../types'
import { Chevron } from './Icon'

export function ScheduleTable({ scenario, data }: { scenario: Scenario; data: OptimizeResponse }) {
  const eff = effectiveSolar(scenario, data.directive_interpretation)
  const inWindow = new Set<number>()
  for (const d of data.directive_interpretation) if (d.applies && d.structured_adjustment) d.structured_adjustment.hours.forEach((h) => inWindow.add(h))
  return (
    <details className="disclosure">
      <summary>
        View full 24-hour schedule
        <span className="hint">Hour-by-hour grid, solar and battery decisions</span>
        <Chevron />
      </summary>
      <div className="content">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Hour</th>
                <th>Demand</th>
                <th>Solar avail.</th>
                <th>Solar used</th>
                <th>Grid</th>
                <th>Price</th>
                <th>Cost</th>
                <th style={{ textAlign: 'left' }}>Battery</th>
                <th>kWh</th>
                <th>Level after</th>
              </tr>
            </thead>
            <tbody>
              {data.hourly_plan.map((p, i) => {
                const h = scenario.hours[i]
                return (
                  <tr key={p.hour} className={inWindow.has(p.hour) ? 'win' : ''}>
                    <td>{String(p.hour).padStart(2, '0')}:00</td>
                    <td>{fmt(h?.demand_kwh ?? 0)}</td>
                    <td className="muted">{fmt(eff[i] ?? 0)}</td>
                    <td>{fmt(p.solar_used_kwh)}</td>
                    <td>{fmt(p.grid_kwh)}</td>
                    <td className="muted">{fmt(h?.tariff_bdt_per_kwh ?? 0)}</td>
                    <td>{fmt(p.grid_kwh * (h?.tariff_bdt_per_kwh ?? 0))}</td>
                    <td className={`act-${p.battery_action}`} style={{ textAlign: 'left' }}>
                      {p.battery_action === 'idle' ? 'idle' : p.battery_action === 'charge' ? 'charging' : 'discharging'}
                    </td>
                    <td>{p.battery_action === 'idle' ? '' : fmt(p.battery_kwh)}</td>
                    <td>{fmt(p.battery_energy_after_kwh)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="small dim">All values in kWh; price and cost in BDT. Shaded rows fall inside an operator-instruction window.</div>
      </div>
    </details>
  )
}
