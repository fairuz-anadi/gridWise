import { fmt } from '../humanize'
import { reserveMargin } from '../plan'
import type { OptimizeResponse, Scenario } from '../types'
import { Icon } from './Icon'
import { MetricCard } from './MetricCard'

interface Props {
  scenario: Scenario
  data: OptimizeResponse
  issues: string[]
  referenceCost?: number
  stale: boolean
  busy: boolean
  onRerun: () => void
  onAdjust: () => void
}

/** Result header: verdict, then the numbers an operator actually asks about. All values come from the response. */
export function PlanSummary({ scenario, data, issues, referenceCost, stale, busy, onRerun, onAdjust }: Props) {
  const valid = issues.length === 0
  const { margin, lowest, floorMax } = reserveMargin(scenario, data)
  const raised = floorMax > scenario.battery.minimum_energy_kwh + 0.011
  const matchesRef = referenceCost !== undefined && Math.abs(referenceCost - data.total_cost_bdt) <= 0.01
  const solarUsed = data.hourly_plan.reduce((a, p) => a + p.solar_used_kwh, 0)
  const demand = scenario.hours.reduce((a, h) => a + h.demand_kwh, 0)

  return (
    <div className="stack">
      <div className="card result-head">
        <div>
          <div className="eyebrow">Result</div>
          <h1 style={{ marginTop: 6 }}>{valid ? 'Your energy plan is ready' : 'This plan needs review'}</h1>
          <div className="checks">
            {valid ? (
              <span className="chip ok">All required checks passed</span>
            ) : (
              <span className="chip bad">
                {issues.length} check{issues.length > 1 ? 's' : ''} failed
              </span>
            )}
            {matchesRef && <span className="chip ok plain">Matches the reference optimum</span>}
            {stale && <span className="chip warn">Scenario changed since this plan</span>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button className="btn" onClick={onAdjust} disabled={busy}>
            Adjust scenario
          </button>
          <button className="btn primary" onClick={onRerun} disabled={busy}>
            {stale ? 'Regenerate plan' : 'Generate again'}
          </button>
        </div>
      </div>

      {!valid && (
        <div className="banner bad" role="alert">
          <span className="icon-wrap alert">
            <Icon name="alert" />
          </span>
          <div>
            <div className="title">The returned schedule breaks {issues.length === 1 ? 'a rule' : `${issues.length} rules`}</div>
            <div className="text">Independent re-check of the plan against the energy and battery rules. The server should not have returned this — report it to the backend owner.</div>
            <ul>
              {issues.slice(0, 8).map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          </div>
          <span />
        </div>
      )}

      <div className="grid-4">
        <MetricCard label="Estimated cost" value={fmt(data.total_cost_bdt, 0)} unit="BDT" accent sub={<>Grid electricity for the day</>} />
        <MetricCard label="Grid energy" value={fmt(data.total_grid_kwh, 0)} unit="kWh" sub={<>Peak hour <b>{fmt(data.peak_grid_kwh)} kWh</b></>} />
        <MetricCard
          label={margin >= -0.011 ? 'Reserve protected' : 'Reserve breached'}
          value={fmt(lowest, 0)}
          unit="kWh"
          sub={
            margin >= -0.011 ? (
              <>
                Lowest level today · never below the required minimum{raised ? <> (up to <b>{fmt(floorMax)} kWh</b> in the instructed window)</> : <> of <b>{fmt(floorMax)} kWh</b></>}
              </>
            ) : (
              <span style={{ color: 'var(--red)' }}>Drops {fmt(-margin)} kWh below the required reserve</span>
            )
          }
        />
        <MetricCard label="Solar used" value={fmt(solarUsed, 0)} unit="kWh" sub={<>{demand > 0 ? `${Math.round((solarUsed / demand) * 100)}% of today’s demand` : '24 hours scheduled'}</>} />
      </div>
    </div>
  )
}
