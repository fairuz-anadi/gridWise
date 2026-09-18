import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, checkHealth, optimize } from './api'
import { AppShell, type View } from './components/AppShell'
import type { Comparison } from './components/InstructionCard'
import { clientReplay } from './plan'
import { DEFAULT_SAMPLE_ID, findSample } from './samples'
import type { ResultState, Run } from './state'
import type { Scenario } from './types'
import { useTheme } from './theme'
import { validateScenario } from './validate'
import { OverviewView } from './views/OverviewView'
import { ScenarioView } from './views/ScenarioView'
import { ScheduleView } from './views/ScheduleView'

const MOCK = import.meta.env.VITE_MOCK === '1'

export default function App() {
  const [view, setView] = useState<View>('overview')
  const [scenario, setScenario] = useState<Scenario>(() => structuredClone(findSample(DEFAULT_SAMPLE_ID)!.input))
  const [result, setResult] = useState<ResultState>({ status: 'idle' })
  const [lastRun, setLastRun] = useState<Run | null>(null)
  const [previous, setPrevious] = useState<Run | null>(null)
  const [health, setHealth] = useState<'unknown' | 'ok' | 'down'>('unknown')
  const [, isDark, toggleTheme] = useTheme()
  const abortRef = useRef<AbortController | null>(null)
  // Mirror of lastRun for run(), which must snapshot it before the result switches to "loading".
  const lastRunRef = useRef<Run | null>(null)

  const errors = useMemo(() => validateScenario(scenario), [scenario])
  const busy = result.status === 'loading'

  useEffect(() => {
    let alive = true
    const ping = async () => {
      const ok = await checkHealth()
      if (alive) setHealth(ok ? 'ok' : 'down')
    }
    void ping()
    const t = setInterval(ping, 30_000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  // After a wording comparison, land on the instructions card rather than the top of the page.
  const focusInstructionsRef = useRef(false)

  const viewRef = useRef<View>('overview')
  const go = useCallback((v: View) => {
    if (viewRef.current !== v) window.scrollTo({ top: 0 })
    viewRef.current = v
    setView(v)
  }, [])

  useEffect(() => {
    if (result.status === 'success' && focusInstructionsRef.current) {
      focusInstructionsRef.current = false
      requestAnimationFrame(() => document.getElementById('instructions')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    }
  }, [result])

  const run = useCallback(
    async (s: Scenario) => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      const startedAt = Date.now()
      const before = lastRunRef.current
      setResult({ status: 'loading', startedAt })
      go('schedule')
      try {
        const data = await optimize(s, ctrl.signal)
        if (ctrl.signal.aborted) return
        const next: Run = { scenario: structuredClone(s), data, elapsedMs: Date.now() - startedAt }
        lastRunRef.current = next
        setPrevious(before)
        setLastRun(next)
        setResult({ status: 'success', run: next })
      } catch (e) {
        if (ctrl.signal.aborted) return
        setResult({ status: 'error', error: e instanceof ApiError ? e : new ApiError(0, (e as Error).message) })
      }
    },
    [go],
  )

  const onGenerate = () => void run(scenario)
  const onLoadSample = (id: string) => {
    const s = findSample(id)
    if (s) setScenario(structuredClone(s.input))
  }
  const onChangeNotes = (notes: string[]) => setScenario((prev) => ({ ...prev, operator_notes: notes }))
  const onRephrase = (i: number, text: string) => {
    const next = { ...scenario, operator_notes: scenario.operator_notes.map((n, j) => (j === i ? text : n)) }
    setScenario(next)
    focusInstructionsRef.current = true
    void run(next)
  }

  // Interpretation is only shown against the exact wording it was produced from.
  const notesMatchRun = !!lastRun && JSON.stringify(lastRun.scenario.operator_notes) === JSON.stringify(scenario.operator_notes)
  const directives = notesMatchRun ? lastRun!.data.directive_interpretation : undefined
  const stale = !!lastRun && JSON.stringify(lastRun.scenario) !== JSON.stringify(scenario)
  const issues = useMemo(() => (lastRun ? clientReplay(lastRun.scenario, lastRun.data) : []), [lastRun])
  const comparisons = useMemo<(Comparison | undefined)[] | undefined>(() => {
    if (!lastRun || !previous) return undefined
    return lastRun.scenario.operator_notes.map((note, i) => {
      const prevNote = previous.scenario.operator_notes[i]
      const prevDir = previous.data.directive_interpretation[i]
      return prevNote !== undefined && prevDir && prevNote !== note ? { previousNote: prevNote, previousDirective: prevDir } : undefined
    })
  }, [lastRun, previous])
  const sample = lastRun ? findSample(lastRun.scenario.scenario_id) : undefined
  const referenceCost =
    sample && JSON.stringify(sample.input) === JSON.stringify(lastRun?.scenario) ? sample.expected_output.total_cost_bdt : undefined

  return (
    <AppShell view={view} onView={go} health={health} mock={MOCK} isDark={isDark} onToggleTheme={toggleTheme}>
      {view === 'overview' && (
        <OverviewView
          scenario={scenario}
          errors={errors}
          busy={busy}
          directives={directives}
          comparisons={notesMatchRun ? comparisons : undefined}
          planReady={!!lastRun}
          stale={stale}
          planCost={lastRun?.data.total_cost_bdt}
          onLoadSample={onLoadSample}
          onChangeNotes={onChangeNotes}
          onRephrase={onRephrase}
          onGenerate={onGenerate}
          onEditScenario={() => go('scenario')}
          onViewPlan={() => go('schedule')}
        />
      )}
      {view === 'scenario' && (
        <ScenarioView
          scenario={scenario}
          errors={errors}
          busy={busy}
          directives={directives}
          comparisons={notesMatchRun ? comparisons : undefined}
          onChange={setScenario}
          onRephrase={onRephrase}
          onGenerate={onGenerate}
        />
      )}
      {view === 'schedule' && (
        <ScheduleView
          scenario={scenario}
          result={result}
          lastRun={lastRun}
          issues={issues}
          comparisons={comparisons}
          referenceCost={referenceCost}
          stale={stale}
          mock={MOCK}
          busy={busy}
          errors={errors}
          onGenerate={onGenerate}
          onEditScenario={() => go('scenario')}
          onChangeNotes={onChangeNotes}
          onRephrase={onRephrase}
        />
      )}
    </AppShell>
  )
}
