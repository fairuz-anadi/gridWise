import { useState } from 'react'
import type { Battery, HourInput, Scenario } from '../types'
import { Chevron } from './Icon'

interface Props {
  scenario: Scenario
  errors: Record<string, string>
  busy: boolean
  onChange: (s: Scenario) => void
}

const BATTERY_FIELDS: { key: keyof Battery; label: string; hint: string }[] = [
  { key: 'capacity_kwh', label: 'Capacity', hint: 'kWh the battery can hold' },
  { key: 'initial_energy_kwh', label: 'Initial energy', hint: 'kWh stored at midnight' },
  { key: 'minimum_energy_kwh', label: 'Minimum reserve', hint: 'kWh that must always remain' },
  { key: 'max_charge_kwh_per_hour', label: 'Max charge rate', hint: 'kWh per hour' },
  { key: 'max_discharge_kwh_per_hour', label: 'Max discharge rate', hint: 'kWh per hour' },
]

const HOUR_COLS: { key: keyof HourInput; label: string }[] = [
  { key: 'demand_kwh', label: 'Demand kWh' },
  { key: 'solar_kwh', label: 'Solar kWh' },
  { key: 'tariff_bdt_per_kwh', label: 'Price BDT/kWh' },
]

/** Advanced configuration: battery parameters, the 24-hour table and the raw request JSON. */
export function ScenarioEditor({ scenario, errors, busy, onChange }: Props) {
  const b = scenario.battery
  return (
    <div className="stack">
      <div className="card">
        <div className="card-head">
          <div>
            <h3>Battery</h3>
            <div className="small muted">Physical limits the plan must respect</div>
          </div>
        </div>
        <div className="form-grid">
          {BATTERY_FIELDS.map(({ key, label, hint }) => (
            <label key={key}>
              {label}
              <input
                id={`battery-${key}`}
                type="number"
                min={0}
                step="any"
                value={Number.isFinite(b[key]) ? b[key] : ''}
                aria-invalid={!!errors[`battery.${key}`]}
                onChange={(e) => onChange({ ...scenario, battery: { ...b, [key]: numberOrNaN(e.target.value) } })}
                disabled={busy}
              />
              <span className="small dim" style={{ fontWeight: 500 }}>
                {errors[`battery.${key}`] ? <span className="field-error" style={{ marginTop: 0 }}>{errors[`battery.${key}`]}</span> : hint}
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div>
            <h3>24-hour data</h3>
            <div className="small muted">Expected demand, forecast solar and grid price for each hour</div>
          </div>
          <div className="actions">
            <label className="field" style={{ fontWeight: 500 }}>
              <span className="sr-only">Scenario name</span>
              <input
                id="scenario_id"
                value={scenario.scenario_id}
                aria-invalid={!!errors['scenario_id']}
                placeholder="Scenario name"
                onChange={(e) => onChange({ ...scenario, scenario_id: e.target.value })}
                disabled={busy}
                style={{ width: 180 }}
              />
            </label>
          </div>
        </div>
        {errors['hours'] && <div className="field-error" style={{ marginBottom: 8 }}>{errors['hours']}</div>}
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Hour</th>
                {HOUR_COLS.map((c) => (
                  <th key={c.key}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {scenario.hours.map((h, i) => (
                <tr key={i}>
                  <td>{String(h.hour).padStart(2, '0')}:00</td>
                  {HOUR_COLS.map((c) => (
                    <td key={c.key}>
                      <input
                        id={`hour-${i}-${c.key}`}
                        type="number"
                        min={0}
                        step="any"
                        value={Number.isFinite(h[c.key]) ? h[c.key] : ''}
                        aria-label={`Hour ${h.hour} ${c.label}`}
                        aria-invalid={!!errors[`hours.${i}.${c.key}`]}
                        title={errors[`hours.${i}.${c.key}`]}
                        onChange={(e) =>
                          onChange({ ...scenario, hours: scenario.hours.map((row, j) => (j === i ? { ...row, [c.key]: numberOrNaN(e.target.value) } : row)) })
                        }
                        disabled={busy}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <RawJson scenario={scenario} onChange={onChange} busy={busy} />
    </div>
  )
}

function RawJson({ scenario, onChange, busy }: { scenario: Scenario; onChange: (s: Scenario) => void; busy: boolean }) {
  const [text, setText] = useState(() => JSON.stringify(scenario, null, 2))
  const [err, setErr] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const apply = () => {
    try {
      const parsed = JSON.parse(text) as Scenario
      if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.hours) || !Array.isArray(parsed.operator_notes) || typeof parsed.battery !== 'object') {
        throw new Error('Expected an object with scenario_id, operator_notes, hours and battery')
      }
      onChange(parsed)
      setErr(null)
      setDirty(false)
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <details className="disclosure">
      <summary>
        Raw request JSON
        <span className="hint">Paste a full scenario or copy the current one</span>
        <Chevron />
      </summary>
      <div className="content">
        <textarea
          id="raw-json"
          className="mono"
          rows={22}
          style={{ width: '100%', fontSize: 12.5 }}
          value={text}
          aria-invalid={!!err}
          onChange={(e) => {
            setText(e.target.value)
            setDirty(true)
          }}
          disabled={busy}
          spellCheck={false}
        />
        {err && <div className="field-error">{err}</div>}
        <div className="row-between">
          <span className="small dim">{dirty && !err ? 'Unapplied edits' : 'In sync with the form'}</span>
          <span style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn ghost sm"
              onClick={() => {
                setText(JSON.stringify(scenario, null, 2))
                setDirty(false)
                setErr(null)
              }}
              disabled={busy}
            >
              Reload from form
            </button>
            <button className="btn sm" onClick={apply} disabled={busy || !dirty}>
              Apply JSON
            </button>
          </span>
        </div>
      </div>
    </details>
  )
}

function numberOrNaN(v: string): number {
  return v.trim() === '' ? NaN : Number(v)
}
