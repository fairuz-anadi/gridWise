import { useEffect, useState } from 'react'

/**
 * Honest progress: the client validated the scenario before sending (step 1 is really done), the
 * request is in flight (step 2 — the server does not stream, so this is one step), and the
 * constraint check runs client-side once the plan arrives (step 3). Nothing here pretends to know
 * backend progress it cannot see.
 */
export function OptimizationProgress({ startedAt }: { startedAt: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 200)
    return () => clearInterval(t)
  }, [])
  const s = (now - startedAt) / 1000
  return (
    <div className="card progress" role="status" aria-live="polite">
      <div>
        <h2>Preparing your energy plan…</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          Reading the operator instructions and building a 24-hour schedule.
        </p>
      </div>
      <div className="steps">
        <div className="step done">
          <span className="dot" />
          <span>Scenario validated</span>
          <span className="t">done</span>
        </div>
        <div className="step active">
          <span className="dot" />
          <span>Understanding instructions and building the schedule</span>
          <span className="t">{s.toFixed(1)}s</span>
        </div>
        <div className="step">
          <span className="dot" />
          <span>Checking battery and grid constraints</span>
          <span className="t" />
        </div>
      </div>
      <p className="small dim">Usually a few seconds. The AI step is the slow one.</p>
    </div>
  )
}
