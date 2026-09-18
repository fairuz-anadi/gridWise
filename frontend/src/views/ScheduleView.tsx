import type { ApiError } from '../api'
import type { Scenario } from '../types'
import { AdvancedDetails } from '../components/AdvancedDetails'
import { BatteryChart } from '../components/BatteryChart'
import { PlanEnergyChart } from '../components/EnergyChart'
import { ErrorState } from '../components/ErrorState'
import type { Comparison } from '../components/InstructionCard'
import { OperatorInstructions } from '../components/OperatorInstructions'
import { OptimizationProgress } from '../components/OptimizationProgress'
import { PlanSummary } from '../components/PlanSummary'
import { Recommendations } from '../components/Recommendations'
import { ScheduleTable } from '../components/ScheduleTable'
import type { ResultState, Run } from '../state'

interface Props {
  scenario: Scenario
  result: ResultState
  lastRun: Run | null
  issues: string[]
  comparisons?: (Comparison | undefined)[]
  referenceCost?: number
  stale: boolean
  mock: boolean
  busy: boolean
  errors: Record<string, string>
  onGenerate: () => void
  onEditScenario: () => void
  onChangeNotes: (notes: string[]) => void
  onRephrase: (i: number, text: string) => void
}

export function ScheduleView(p: Props) {
  const { result, lastRun } = p

  if (result.status === 'loading') return <OptimizationProgress startedAt={result.startedAt} />

  if (result.status === 'idle' && !lastRun) {
    const errorCount = Object.keys(p.errors).length
    return (
      <div className="card empty">
        <h2>No plan yet</h2>
        <p style={{ maxWidth: '48ch' }}>Generate a plan to see how GridWise schedules the grid, solar and battery for the next 24 hours.</p>
        <button className="btn primary" onClick={p.onGenerate} disabled={p.busy || errorCount > 0}>
          Generate energy plan
        </button>
      </div>
    )
  }

  const run = lastRun
  return (
    <>
      {result.status === 'error' && <ErrorState error={result.error as ApiError} onRetry={p.onGenerate} onEditScenario={p.onEditScenario} />}
      {run && (
        <>
          {result.status === 'error' && <div className="small muted">Showing the previous plan.</div>}
          <PlanSummary scenario={run.scenario} data={run.data} issues={p.issues} referenceCost={p.referenceCost} stale={p.stale} busy={p.busy} onRerun={p.onGenerate} onAdjust={p.onEditScenario} />
          <PlanEnergyChart scenario={run.scenario} result={run.data} />
          <section className="grid-5-7">
            <Recommendations scenario={run.scenario} data={run.data} />
            <BatteryChart scenario={run.scenario} result={run.data} height={300} />
          </section>
          <OperatorInstructions
            notes={run.scenario.operator_notes}
            directives={run.data.directive_interpretation}
            battery={run.scenario.battery}
            busy={p.busy}
            errors={{}}
            comparisons={p.comparisons}
            onChangeNotes={p.onChangeNotes}
            onRephrase={p.onRephrase}
          />
          <ScheduleTable scenario={run.scenario} data={run.data} />
          <AdvancedDetails request={run.scenario} response={run.data} elapsedMs={run.elapsedMs} mock={p.mock} />
        </>
      )}
    </>
  )
}
