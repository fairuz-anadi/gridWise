import { useState } from 'react'
import { isDegraded } from '../humanize'
import type { Battery, Directive } from '../types'
import { InstructionCard, type Comparison } from './InstructionCard'

interface Props {
  notes: string[]
  /** Latest interpretation, only when it was produced from exactly these notes. */
  directives?: Directive[]
  battery: Battery
  busy: boolean
  errors: Record<string, string>
  comparisons?: (Comparison | undefined)[]
  onChangeNotes: (notes: string[]) => void
  onRephrase: (index: number, text: string) => void
  /** Start in editing mode (Scenario view). */
  editByDefault?: boolean
  onGenerate?: () => void
}

export function OperatorInstructions({ notes, directives, battery, busy, errors, comparisons, onChangeNotes, onRephrase, editByDefault = false, onGenerate }: Props) {
  const [editing, setEditing] = useState(editByDefault)
  const applied = directives?.filter((d) => d.applies).length ?? 0
  const irrelevant = directives?.filter((d) => !d.applies && !isDegraded(d)).length ?? 0
  const degraded = directives?.some(isDegraded) ?? false
  const set = (i: number, v: string) => onChangeNotes(notes.map((n, j) => (j === i ? v : n)))
  const remove = (i: number) => onChangeNotes(notes.filter((_, j) => j !== i))
  const add = () => onChangeNotes([...notes, ''])

  return (
    <div className="card" id="instructions">
      <div className="card-head">
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3>Operator instructions</h3>
          <div className="small muted">
            {directives
              ? `${applied} affecting today’s plan${irrelevant ? ` · ${irrelevant} not relevant` : ''}`
              : `${notes.length} instruction${notes.length === 1 ? '' : 's'} for today — interpreted by AI when you generate a plan`}
          </div>
        </div>
        <div className="actions">
          {!editing && (
            <button className="btn sm" onClick={() => setEditing(true)} disabled={busy}>
              Edit instructions
            </button>
          )}
          {editing && (
            <button className="btn sm" onClick={() => setEditing(false)} disabled={busy}>
              Done
            </button>
          )}
        </div>
      </div>

      {degraded && (
        <div className="banner warn" style={{ marginBottom: 14, padding: '12px 16px' }}>
          <span className="icon-wrap alert">!</span>
          <div>
            <div className="title" style={{ fontSize: 14 }}>
              AI interpretation is temporarily unavailable
            </div>
            <div className="text small">Some instructions could not be interpreted and were treated as having no effect. The plan is still valid under the base rules.</div>
          </div>
          <span />
        </div>
      )}

      {editing ? (
        <div className="notes-editor">
          {errors['operator_notes'] && <div className="field-error">{errors['operator_notes']}</div>}
          {notes.map((n, i) => (
            <div key={i}>
              <div className="note-row">
                <textarea
                  id={`note-${i}`}
                  rows={2}
                  value={n}
                  placeholder="e.g. Do not charge the battery between 2 PM and 4 PM."
                  aria-label={`Instruction ${i + 1}`}
                  aria-invalid={!!errors[`operator_notes.${i}`]}
                  onChange={(e) => set(i, e.target.value)}
                  disabled={busy}
                />
                <button className="btn danger-ghost sm" onClick={() => remove(i)} disabled={busy || notes.length <= 1} aria-label={`Remove instruction ${i + 1}`}>
                  Remove
                </button>
              </div>
              {errors[`operator_notes.${i}`] && <div className="field-error">{errors[`operator_notes.${i}`]}</div>}
            </div>
          ))}
          <div className="row-between">
            <button className="btn sm" onClick={add} disabled={busy || notes.length >= 3}>
              + Add instruction
            </button>
            <span className="small dim">{notes.length} of 3</span>
          </div>
        </div>
      ) : (
        <div className="instr-list">
          {notes.map((n, i) => (
            <InstructionCard key={i} index={i} note={n} directive={directives?.[i]} battery={battery} busy={busy} comparison={comparisons?.[i]} onRephrase={onRephrase} />
          ))}
          {!directives && onGenerate && (
            <div className="small muted" style={{ paddingTop: 4 }}>
              Generate a plan to see how each instruction is understood and applied.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
