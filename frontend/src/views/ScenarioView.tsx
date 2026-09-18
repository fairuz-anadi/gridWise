import type { Directive, Scenario } from '../types'
import type { Comparison } from '../components/InstructionCard'
import { OperatorInstructions } from '../components/OperatorInstructions'
import { ScenarioEditor } from '../components/ScenarioEditor'

interface Props {
  scenario: Scenario
  errors: Record<string, string>
  busy: boolean
  directives?: Directive[]
  comparisons?: (Comparison | undefined)[]
  onChange: (s: Scenario) => void
  onRephrase: (i: number, text: string) => void
  onGenerate: () => void
}

export function ScenarioView({ scenario, errors, busy, directives, comparisons, onChange, onRephrase, onGenerate }: Props) {
  const errorCount = Object.keys(errors).length
  return (
    <>
      <section className="hero">
        <div>
          <div className="eyebrow">Scenario</div>
          <h1 style={{ marginTop: 8 }}>Scenario details</h1>
          <p className="lead">Operator instructions, battery limits and the 24-hour forecast the plan is built from.</p>
        </div>
        <div className="side">
          <button className="btn primary" onClick={onGenerate} disabled={busy || errorCount > 0}>
            Generate energy plan
          </button>
          {errorCount > 0 && (
            <span className="small" style={{ color: 'var(--amber)' }}>
              {errorCount} field{errorCount > 1 ? 's' : ''} need attention
            </span>
          )}
        </div>
      </section>
      <OperatorInstructions
        notes={scenario.operator_notes}
        directives={directives}
        battery={scenario.battery}
        busy={busy}
        errors={errors}
        comparisons={comparisons}
        onChangeNotes={(notes) => onChange({ ...scenario, operator_notes: notes })}
        onRephrase={onRephrase}
        editByDefault
      />
      <ScenarioEditor scenario={scenario} errors={errors} busy={busy} onChange={onChange} />
    </>
  )
}
