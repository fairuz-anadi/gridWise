import type { ReactNode } from 'react'

interface Props {
  label: string
  value: string
  unit?: string
  sub?: ReactNode
  accent?: boolean
  aside?: ReactNode
  /** A phrase rather than a number: rendered smaller so it never wraps awkwardly. */
  text?: boolean
}

export function MetricCard({ label, value, unit, sub, accent, aside, text }: Props) {
  return (
    <div className={`card metric ${accent ? 'accent' : ''}`}>
      <div>
        <div className="label">{label}</div>
        <div className={`value ${text ? 'text' : ''}`}>
          {value}
          {unit && <small>{unit}</small>}
        </div>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {aside}
    </div>
  )
}

/** Circular gauge for the battery state of charge. `pct` in [0, 1]. */
export function Ring({ pct, label }: { pct: number; label: string }) {
  const r = 36
  const c = 2 * Math.PI * r
  const p = Math.max(0, Math.min(1, pct))
  return (
    <svg className="ring" viewBox="0 0 86 86" role="img" aria-label={label}>
      <circle cx="43" cy="43" r={r} fill="none" stroke="var(--surface-3)" strokeWidth="8" />
      <circle
        cx="43"
        cy="43"
        r={r}
        fill="none"
        stroke="var(--mint)"
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={`${c * p} ${c * (1 - p)}`}
        transform="rotate(-90 43 43)"
      />
      <text x="43" y="49" textAnchor="middle">
        {Math.round(p * 100)}%
      </text>
    </svg>
  )
}
