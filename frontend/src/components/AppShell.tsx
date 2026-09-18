import type { ReactNode } from 'react'

export type View = 'overview' | 'scenario' | 'schedule'

const VIEWS: { id: View; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'scenario', label: 'Scenario' },
  { id: 'schedule', label: 'Schedule' },
]

interface Props {
  view: View
  onView: (v: View) => void
  health: 'unknown' | 'ok' | 'down'
  mock: boolean
  children: ReactNode
}

export function AppShell({ view, onView, health, mock, children }: Props) {
  return (
    <div className="shell">
      <header className="topnav">
        <div className="inner">
          <div className="brand">
            <span className="mark" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z" />
              </svg>
            </span>
            <span className="name">GridWise</span>
            <span className="tag">AI-assisted energy scheduling</span>
          </div>
          <nav className="nav" aria-label="Sections">
            {VIEWS.map((v) => (
              <button key={v.id} aria-current={view === v.id ? 'page' : undefined} onClick={() => onView(v.id)}>
                {v.label}
              </button>
            ))}
          </nav>
          <div className="status-area">
            {mock && <span className="sub">Sample data · no backend</span>}
            {mock ? (
              <span className="chip ok">Demo ready</span>
            ) : health === 'ok' ? (
              <span className="chip ok">System ready</span>
            ) : health === 'down' ? (
              <span className="chip bad">System offline</span>
            ) : (
              <span className="chip">Checking system</span>
            )}
          </div>
        </div>
      </header>
      <main className="page">{children}</main>
    </div>
  )
}
