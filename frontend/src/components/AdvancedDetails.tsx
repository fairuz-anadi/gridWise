import { useState } from 'react'
import type { OptimizeResponse, Scenario } from '../types'
import { Chevron } from './Icon'

interface Props {
  request: Scenario
  response?: OptimizeResponse
  elapsedMs?: number
  mock: boolean
}

/** Developer view: the exact JSON exchanged with the judged endpoint. Never part of the operator flow. */
export function AdvancedDetails({ request, response, elapsedMs, mock }: Props) {
  const [toast, setToast] = useState<string | null>(null)
  const copy = async (label: string, obj: unknown) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(obj, null, 2))
      setToast(`${label} copied`)
    } catch {
      setToast('Copy failed — select the text manually')
    }
    setTimeout(() => setToast(null), 1600)
  }
  return (
    <details className="disclosure">
      <summary>
        Advanced · developer details
        <span className="hint">
          <code>POST /optimize-energy</code>
          {elapsedMs !== undefined && ` · ${(elapsedMs / 1000).toFixed(2)} s round trip`}
          {mock && ' · mock response'}
        </span>
        <Chevron />
      </summary>
      <div className="content">
        <div className="row-between">
          <h3>Request body</h3>
          <button className="btn ghost sm" onClick={() => void copy('Request', request)}>
            Copy
          </button>
        </div>
        <pre>{JSON.stringify(request, null, 2)}</pre>
        {response && (
          <>
            <div className="row-between">
              <h3>Raw response</h3>
              <button className="btn ghost sm" onClick={() => void copy('Response', response)}>
                Copy
              </button>
            </div>
            <pre>{JSON.stringify(response, null, 2)}</pre>
          </>
        )}
        <div className="small dim">
          Field names follow the Problem Statement byte-for-byte. Directive hours are start-inclusive, end-exclusive; <code>factor</code> is the usable fraction of forecast solar.
        </div>
      </div>
      {toast && <div className="toast">{toast}</div>}
    </details>
  )
}
