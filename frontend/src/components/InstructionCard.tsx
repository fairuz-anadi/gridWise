import { useState } from 'react'
import { describeDirective, directiveValue, rangeLabel, sameDirective } from '../humanize'
import type { Battery, Directive } from '../types'
import { Chevron, Icon } from './Icon'

export interface Comparison {
  previousNote: string
  previousDirective: Directive
}

interface Props {
  index: number
  note: string
  /** Interpretation from the latest run, if the run used this exact wording. */
  directive?: Directive
  battery: Battery
  busy: boolean
  comparison?: Comparison
  onRephrase: (index: number, text: string) => void
}

export function InstructionCard({ index, note, directive, battery, busy, comparison, onRephrase }: Props) {
  // A card that carries a fresh comparison opens itself: the verdict is the point of the demo.
  const [open, setOpen] = useState(!!comparison)
  const [testing, setTesting] = useState(false)
  const [draft, setDraft] = useState(note)
  const verdict = comparison && directive ? sameDirective(comparison.previousDirective, directive).all : undefined

  const human = directive ? describeDirective(directive, battery) : null
  const muted = human?.muted ?? false

  // Before a plan exists there is nothing to translate: show the note itself, nothing to expand.
  if (!human || !directive) {
    return (
      <div className="instr pending">
        <div className="row" style={{ cursor: 'default' }}>
          <span className="icon-wrap dot">
            <Icon name="dot" />
          </span>
          <span style={{ minWidth: 0 }}>
            <div className="title" style={{ fontWeight: 500 }}>
              “{note.trim() || 'Empty instruction'}”
            </div>
            <div className="range">Interpreted when you generate a plan</div>
          </span>
          <span />
        </div>
      </div>
    )
  }

  const title = human.title
  const range = human.range ?? (human.muted ? 'No effect on the plan' : '')
  const icon = human.icon

  return (
    <div className={`instr ${muted ? 'muted' : ''}`} data-open={open}>
      <button className="row" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className={`icon-wrap ${icon}`}>
          <Icon name={icon} />
        </span>
        <span style={{ minWidth: 0 }}>
          <div className="title">{title}</div>
          <div className="range">{range}</div>
          {verdict !== undefined && (
            <span className={`chip ${verdict ? 'ok' : 'warn'}`} style={{ marginTop: 6 }}>
              {verdict ? 'Interpretation unchanged' : 'Interpretation changed'}
            </span>
          )}
        </span>
        <Chevron />
      </button>
      {open && (
        <div className="body">
          <div className="quote">“{note}”</div>
          {human && <div className="detail">{human.detail}</div>}
          {directive && directive.explanation && !muted && <div className="detail small">{directive.explanation}</div>}
          {directive && (
            <div className="tech" aria-label="Technical interpretation">
              <code>{directive.directive_type}</code>
              {directive.structured_adjustment && <code>hours [{directive.structured_adjustment.hours.join(', ')}]</code>}
              {directive.structured_adjustment?.factor !== undefined && <code>factor {directive.structured_adjustment.factor}</code>}
              {directive.structured_adjustment?.minimum_energy_kwh !== undefined && <code>min {directive.structured_adjustment.minimum_energy_kwh} kWh</code>}
              {directive.structured_adjustment?.max_grid_kwh !== undefined && <code>cap {directive.structured_adjustment.max_grid_kwh} kWh</code>}
              <code>applies {String(directive.applies)}</code>
            </div>
          )}

          {comparison && directive && <ComparisonView comparison={comparison} current={directive} currentNote={note} battery={battery} />}

          {directive && !testing && (
            <div>
              <button
                className="btn sm"
                onClick={() => {
                  setDraft(note)
                  setTesting(true)
                }}
                disabled={busy}
              >
                Test different wording
              </button>
            </div>
          )}
          {testing && (
            <div className="rephrase">
              <label>
                Original instruction
                <span className="orig">“{note}”</span>
              </label>
              <label>
                Rephrased instruction
                <textarea id={`rephrase-${index}`} rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} disabled={busy} />
              </label>
              <div className="row-between">
                <span className="small muted">The plan is regenerated with the new wording so you can see whether the interpretation holds.</span>
                <span style={{ display: 'flex', gap: 8 }}>
                  <button className="btn ghost sm" onClick={() => setTesting(false)} disabled={busy}>
                    Cancel
                  </button>
                  <button
                    className="btn primary sm"
                    disabled={busy || !draft.trim() || draft.trim() === note.trim()}
                    onClick={() => {
                      setTesting(false)
                      onRephrase(index, draft.trim())
                    }}
                  >
                    Run comparison
                  </button>
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ComparisonView({ comparison, current, currentNote, battery }: { comparison: Comparison; current: Directive; currentNote: string; battery: Battery }) {
  const prev = comparison.previousDirective
  const same = sameDirective(prev, current)
  const ph = describeDirective(prev, battery)
  const ch = describeDirective(current, battery)
  return (
    <div className={`compare ${same.all ? 'same' : 'changed'}`} role="status">
      <div className="verdict">
        <Icon name={same.all ? 'check' : 'alert'} size={16} />
        {same.all ? 'Interpretation unchanged' : 'Interpretation changed'}
      </div>
      <div className="small muted">
        Previous wording: “{comparison.previousNote}” → Current wording: “{currentNote}”
      </div>
      <div className="rows">
        <span className="k">Meaning</span>
        <span className={`v ${same.type ? '' : 'diff'}`}>
          {ph.title} → {ch.title}
        </span>
        <span className="k">Time</span>
        <span className={`v ${same.hours ? '' : 'diff'}`}>
          {rangeOrDash(prev)} → {rangeOrDash(current)}
        </span>
        <span className="k">Value</span>
        <span className={`v ${same.value ? '' : 'diff'}`}>
          {directiveValue(prev)} → {directiveValue(current)}
        </span>
      </div>
    </div>
  )
}

function rangeOrDash(d: Directive): string {
  return d.structured_adjustment ? rangeLabel(d.structured_adjustment.hours) : '—'
}
