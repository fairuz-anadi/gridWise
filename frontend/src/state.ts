import type { ApiError } from './api'
import type { OptimizeResponse, Scenario } from './types'

export interface Run {
  scenario: Scenario
  data: OptimizeResponse
  elapsedMs: number
}

export type ResultState =
  | { status: 'idle' }
  | { status: 'loading'; startedAt: number }
  | { status: 'error'; error: ApiError }
  | { status: 'success'; run: Run }
