import { useState } from 'react'
import './MlPaceOverlay.css'

type Row = { stint_lap: number; tyre_age: number; sim_seconds: number; ml_seconds: number; sim_rel: number; ml_rel: number }
type Overlay = {
  laps: Row[]
  summary: { sim_stint_seconds: number; ml_stint_seconds: number; mean_abs_shape_gap_seconds: number }
  assumed_context: Record<string, number>
  caveat: string
}

const W = 320
const H = 120
const PAD = 26

function Curves({ rows }: { rows: Row[] }) {
  const values = rows.flatMap((row) => [row.sim_rel, row.ml_rel])
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo || 1
  const x = (i: number) => PAD + (i / Math.max(rows.length - 1, 1)) * (W - PAD * 1.4)
  const y = (v: number) => H - PAD * 0.8 - ((v - lo) / span) * (H - PAD * 1.6)
  const path = (pick: (row: Row) => number) => rows.map((row, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(pick(row)).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Lap time relative to the first stint lap: simulator versus ML rollout">
      <line className="mlp-axis" x1={PAD} y1={y(0)} x2={W - 4} y2={y(0)} />
      <path className="mlp-sim" d={path((row) => row.sim_rel)} />
      <path className="mlp-ml" d={path((row) => row.ml_rel)} />
      <text x={3} y={y(hi) + 3}>{hi.toFixed(1)}s</text>
      <text x={3} y={y(lo) + 3}>{lo.toFixed(1)}s</text>
      <text x={W / 2} y={H - 2} textAnchor="middle">stint lap</text>
    </svg>
  )
}

export default function MlPaceOverlay({ sessionSlug, baseUrl, compounds, scheduledLaps }: {
  sessionSlug: string; baseUrl: string; compounds: string[]; scheduledLaps: number
}) {
  const [enabled, setEnabled] = useState(false)
  const [compound, setCompound] = useState(compounds[0] ?? 'MEDIUM')
  const [startLap, setStartLap] = useState(8)
  const [laps, setLaps] = useState(Math.min(25, scheduledLaps))
  const [result, setResult] = useState<Overlay | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const run = () => {
    setLoading(true)
    setError(null)
    fetch(`${baseUrl}/api/v1/strategy/${sessionSlug}/ml-pace`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ compound, start_lap: startLap, laps }),
    })
      .then(async (response) => {
        const body = await response.json()
        if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'request rejected')
        return body as Overlay
      })
      .then(setResult)
      .catch((cause) => { setResult(null); setError(String(cause.message ?? cause)) })
      .finally(() => setLoading(false))
  }

  return (
    <section className="mlp" aria-label="Experimental ML pace overlay">
      <label className="mlp-toggle">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
        <span>ML pace overlay <em>experimental · off by default · simulator stays the baseline</em></span>
      </label>
      {enabled && (
        <div className="mlp-body">
          <div className="mlp-controls">
            <label>Compound
              <select value={compound} onChange={(event) => setCompound(event.target.value)}>
                {compounds.map((name) => <option key={name}>{name}</option>)}
              </select>
            </label>
            <label>Start lap
              <input type="number" min={1} max={scheduledLaps} value={startLap}
                onChange={(event) => setStartLap(Math.max(1, Number(event.target.value) || 1))} />
            </label>
            <label>Stint laps
              <input type="number" min={2} max={60} value={laps}
                onChange={(event) => setLaps(Math.min(60, Math.max(2, Number(event.target.value) || 2)))} />
            </label>
            <button type="button" onClick={run} disabled={loading}>{loading ? 'Running…' : 'Roll model forward'}</button>
          </div>
          {error && <p className="mlp-error" role="alert">ML pace unavailable: {error}</p>}
          {result && (
            <div className="mlp-result">
              <Curves rows={result.laps} />
              <p className="mlp-legend">
                <i className="mlp-sim" /> simulator (deterministic baseline) · <i className="mlp-ml" /> ML rollout
                · mean shape gap {result.summary.mean_abs_shape_gap_seconds.toFixed(2)} s
              </p>
              <p className="mlp-caveat">{result.caveat}</p>
              <p className="mlp-caveat">Assumed context: {Object.entries(result.assumed_context).map(([k, v]) => `${k}=${v}`).join(', ')}</p>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
