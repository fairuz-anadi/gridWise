import { describeDirective, fmt, hourLabel, type IconName } from '../humanize'
import { batteryBlocks } from '../plan'
import type { OptimizeResponse, Scenario } from '../types'
import { Icon } from './Icon'

interface Reco {
  icon: IconName
  title: string
  range: string
  detail: string
}

/**
 * Recommended actions are read straight off the returned plan and the interpreted directives —
 * nothing here is invented: charge/discharge windows come from hourly_plan, constraints from
 * directive_interpretation.
 */
function deriveRecommendations(scenario: Scenario, data: OptimizeResponse): Reco[] {
  const out: Reco[] = []
  const blocks = batteryBlocks(scenario, data.hourly_plan)
  const discharges = blocks.filter((b) => b.action === 'discharge').slice(0, 2)
  const charges = blocks.filter((b) => b.action === 'charge').slice(0, 2)
  for (const b of discharges) {
    out.push({
      icon: 'bolt',
      title: 'Use stored energy',
      range: `${hourLabel(b.from)} – ${hourLabel(b.to)}`,
      detail: `The battery supplies ${fmt(b.kwh, 0)} kWh while grid electricity costs about ${fmt(b.avgTariff)} BDT/kWh.`,
    })
  }
  for (const b of charges) {
    out.push({
      icon: 'battery',
      title: 'Charge the battery',
      range: `${hourLabel(b.from)} – ${hourLabel(b.to)}`,
      detail: `${fmt(b.kwh, 0)} kWh is stored while grid electricity costs about ${fmt(b.avgTariff)} BDT/kWh.`,
    })
  }
  for (const d of data.directive_interpretation) {
    if (!d.applies) continue
    const h = describeDirective(d, scenario.battery)
    out.push({ icon: h.icon, title: h.title, range: h.range ?? '', detail: h.detail })
  }
  return out
}

export function Recommendations({ scenario, data }: { scenario: Scenario; data: OptimizeResponse }) {
  const recos = deriveRecommendations(scenario, data)
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h3>Recommended actions</h3>
          <div className="small muted">What the plan does, and the operator constraints it honours</div>
        </div>
      </div>
      {recos.length === 0 ? (
        <p className="muted">The battery stays idle all day and demand is met from grid and solar.</p>
      ) : (
        <div>
          {recos.map((r, i) => (
            <div className="reco" key={i}>
              <span className={`icon-wrap ${r.icon}`}>
                <Icon name={r.icon} />
              </span>
              <div>
                <div className="title">
                  {r.title}
                  {r.range && <span className="range">{r.range}</span>}
                </div>
                <div className="detail">{r.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
