import pack from '../../tests/fixtures/public_cases.json'
import type { SampleCase } from './types'

// The public case pack is the single source of truth for both the backend tests and
// the console's sample picker / mock mode.
export const SAMPLES: SampleCase[] = (pack as { cases: SampleCase[] }).cases

export const DEFAULT_SAMPLE_ID = 'SAMPLE-06' // three notes incl. a distractor: the demo case

export function findSample(id: string): SampleCase | undefined {
  return SAMPLES.find((c) => c.id === id)
}
