import { fmt, greeting, hourLabel } from '../humanize'
import { scenarioTotals } from '../plan'
import { SAMPLES } from '../samples'
import type { Directive, Scenario } from '../types'
import { ScenarioEnergyChart } from '../components/EnergyChart'
import type { Comparison } from '../components/InstructionCard'
import { MetricCard, Ring } from '../components/MetricCard'
import { OperatorInstructions } from '../components/OperatorInstructions'

interface Props {
  scenario: Scenario
  errors: Record<string, string>
  busy: boolean
  directives?: Directive[]
  comparisons?: (Comparison | undefined)[]
  planReady: boolean
  stale: boolean
  planCost?: number
  onLoadSample: (id: string) => void
  onChangeNotes: (notes: string[]) => void
  onRephrase: (i: number, text: string) => void
  onGenerate: () => void
  onEditScenario: () => void
  onViewPlan: () => void
}

export function OverviewView(p: Props) {
  const { scenario, errors, busy } = p
  const errorCount = Object.keys(errors).length
  const b = scenario.battery
  const t = scenarioTotals(scenario)
  const sample = SAMPLES.find((c) => c.id === scenario.scenario_id)
  const soc = b.capacity_kwh > 0 ? b.initial_energy_kwh / b.capacity_kwh : 0

  return (
    <>
      <section className="hero">
        <div>
          <div className="eyebrow">Overview</div>
          <h1 style={{ marginTop: 8 }}>
            {greeting()}.
            <br />
            Let’s plan today’s energy.
          </h1>
          <p className="lead">
            GridWise reads your operator instructions, then schedules the grid, solar and battery hour by hour for the lowest cost — without breaking a safety limit.
          </p>
        </div>
        <div className="side">
          <label className="sample-select">
            <span className="sr-only">Load a sample scenario</span>
            <select id="sample" value={sample ? sample.id : ''} onChange={(e) => e.target.value && p.onLoadSample(e.target.value)} disabled={busy}>
              <option value="">Custom scenario</option>
              {SAMPLES.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id} · {c.label}
                </option>
              ))}
            </select>
          </label>
          <button className="btn primary" onClick={p.onGenerate} disabled={busy || errorCount > 0}>
            {p.planReady && !p.stale ? 'Generate plan again' : 'Generate energy plan'}
          </button>
          <button className="btn ghost sm" onClick={p.onEditScenario} disabled={busy}>
            Edit scenario details
          </button>
        </div>
      </section>

      <section className="grid-3">
        <MetricCard
          label="Battery"
          value={fmt(b.initial_energy_kwh, 0)}
          unit={`/ ${fmt(b.capacity_kwh, 0)} kWh`}
          sub={
            <>
              Minimum reserve <b>{fmt(b.minimum_energy_kwh)} kWh</b>
            </>
          }
          aside={<Ring pct={soc} label={`Battery ${Math.round(soc * 100)} percent charged`} />}
        />
        <MetricCard
          label="Expected demand"
          value={fmt(t.demand, 0)}
          unit="kWh"
          sub={
            <>
              Solar forecast <b>{fmt(t.solar, 0)} kWh</b> · price peaks at <b>{hourLabel(t.peakHour)}</b>
            </>
          }
        />
        {errorCount > 0 ? (
          <MetricCard
            label="Plan status"
            value="Needs attention" text
            sub={
              <>
                {errorCount} field{errorCount > 1 ? 's' : ''} to fix ·{' '}
                <button className="btn ghost sm" style={{ padding: '0 4px' }} onClick={p.onEditScenario}>
                  open scenario
                </button>
              </>
            }
          />
        ) : busy ? (
          <MetricCard label="Plan status" value="Generating" text sub="Reading instructions and building the schedule…" />
        ) : p.planReady && !p.stale ? (
          <MetricCard
            label="Plan status"
            value="Ready" text
            accent
            sub={
              <>
                Estimated cost <b>{fmt(p.planCost ?? 0, 0)} BDT</b> ·{' '}
                <button className="btn ghost sm" style={{ padding: '0 4px' }} onClick={p.onViewPlan}>
                  view plan
                </button>
              </>
            }
          />
        ) : p.planReady && p.stale ? (
          <MetricCard label="Plan status" value="Out of date" text sub="The scenario changed — generate the plan again." />
        ) : (
          <MetricCard
            label="Plan status"
            value="Ready to optimize" text
            sub={
              <>
                <b>{scenario.operator_notes.length}</b> operator instruction{scenario.operator_notes.length === 1 ? '' : 's'} · <b>24</b> hours of data
              </>
            }
          />
        )}
      </section>

      <section className="grid-8-4">
        <ScenarioEnergyChart scenario={scenario} directives={p.directives ?? []} />
        <OperatorInstructions
          notes={scenario.operator_notes}
          directives={p.directives}
          battery={b}
          busy={busy}
          errors={errors}
          comparisons={p.comparisons}
          onChangeNotes={p.onChangeNotes}
          onRephrase={p.onRephrase}
          onGenerate={p.onGenerate}
        />
      </section>
    </>
  )
}
