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
  isDark: boolean
  onToggleTheme: () => void
  children: ReactNode
}

export function AppShell({ view, onView, health, mock, isDark, onToggleTheme, children }: Props) {
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
              <span className="chip status ok">Demo ready</span>
            ) : health === 'ok' ? (
              <span className="chip status ok">System ready</span>
            ) : health === 'down' ? (
              <span className="chip bad">System offline</span>
            ) : (
              <span className="chip status">Checking system</span>
            )}
            <button className="theme-btn" onClick={onToggleTheme} aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'} title={isDark ? 'Light mode' : 'Dark mode'}>
              {isDark ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </header>
      <main className="page">{children}</main>
    </div>
  )
}
