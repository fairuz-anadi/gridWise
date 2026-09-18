import type { ApiError } from '../api'
import { Icon } from './Icon'

const FIELD_NAMES: Record<string, string> = {
  scenario_id: 'Scenario name',
  operator_notes: 'Operator instructions',
  hours: '24-hour data',
  'battery.capacity_kwh': 'Battery capacity',
  'battery.initial_energy_kwh': 'Battery initial energy',
  'battery.minimum_energy_kwh': 'Battery minimum reserve',
  'battery.max_charge_kwh_per_hour': 'Battery max charge rate',
  'battery.max_discharge_kwh_per_hour': 'Battery max discharge rate',
}

function fieldName(path: string): string {
  if (FIELD_NAMES[path]) return FIELD_NAMES[path]
  const m = /^operator_notes\.(\d+)$/.exec(path)
  if (m) return `Instruction ${Number(m[1]) + 1}`
  const h = /^hours\.(\d+)\.(\w+)$/.exec(path)
  if (h) {
    const col = { demand_kwh: 'demand', solar_kwh: 'solar', tariff_bdt_per_kwh: 'grid price', hour: 'hour' }[h[2]] ?? h[2]
    return `Hour ${String(h[1]).padStart(2, '0')}:00 ${col}`
  }
  return path
}

interface Props {
  error: ApiError
  onRetry: () => void
  onEditScenario: () => void
}

export function ErrorState({ error, onRetry, onEditScenario }: Props) {
  const fields = Object.entries(error.fields)
  const isValidation = error.status === 400 || error.status === 422
  return (
    <div className={`banner ${isValidation ? 'warn' : 'bad'}`} role="alert">
      <span className={`icon-wrap ${isValidation ? 'plug' : 'alert'}`}>
        <Icon name="alert" />
      </span>
      <div>
        <div className="title">{isValidation ? 'Some scenario information needs attention' : 'We couldn’t generate the plan'}</div>
        <div className="text">
          {isValidation
            ? fields.length
              ? 'Fix the items below and try again. Your scenario has been preserved.'
              : error.message
            : `${error.message} Your scenario has been preserved.`}
        </div>
        {fields.length > 0 && (
          <ul>
            {fields.map(([k, v]) => (
              <li key={k}>
                <b>{fieldName(k)}</b> — {v}
              </li>
            ))}
          </ul>
        )}
        {error.status > 0 && (
          <details style={{ marginTop: 8 }}>
            <summary className="small dim" style={{ cursor: 'pointer' }}>
              Technical details
            </summary>
            <code className="small">
              HTTP {error.status}: {error.message}
            </code>
          </details>
        )}
      </div>
      <div style={{ display: 'grid', gap: 8 }}>
        {isValidation && (
          <button className="btn sm" onClick={onEditScenario}>
            Edit scenario
          </button>
        )}
        <button className="btn primary sm" onClick={onRetry}>
          Try again
        </button>
      </div>
    </div>
  )
}
