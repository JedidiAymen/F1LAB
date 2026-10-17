import { useEffect, useState } from 'react'
import './WhatIfLab.css'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BranchLap {
  lap: number
  compound: string
  stint_lap: number
  lap_time_s: number
  cumulative_race_time_s: number
  pitted_this_lap: boolean
  pit_loss_s: number
  estimation: 'historical' | 'simulated'
  is_fork_lap: boolean
}

interface BranchResult {
  session_slug: string
  driver_number: number
  fork_lap: number
  actual_strategy_label: string
  counterfactual_strategy_label: string
  actual_total_race_time_s: number
  counterfactual_total_race_time_s: number
  delta_counterfactual_vs_actual_s: number
  counterfactual_is_faster: boolean
  actual_laps: BranchLap[]
  counterfactual_laps: BranchLap[]
  simulation_limits: string[]
}

interface StrategyInfo {
  scheduled_laps: number
  available_compounds: { compound: string }[]
}

interface PitStopEntry {
  lap: number
  compound: string
}

interface StrategyDef {
  start_compound: string
  pit_stops: PitStopEntry[]
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(3)
  return `${m}:${sec.padStart(6, '0')}`
}

// ---------------------------------------------------------------------------
// Lap timeline chart (SVG bar chart)
// ---------------------------------------------------------------------------

function LapTimeline({ actual, counterfactual, forkLap }: {
  actual: BranchLap[]
  counterfactual: BranchLap[]
  forkLap: number
}) {
  if (!actual.length) return null
  const maxTime = Math.max(...actual.map(l => l.lap_time_s), ...counterfactual.map(l => l.lap_time_s))
  const minTime = Math.min(...actual.map(l => l.lap_time_s), ...counterfactual.map(l => l.lap_time_s))
  const range = maxTime - minTime || 1
  const W = 800
  const H = 120
  const barW = Math.max(2, (W - 20) / actual.length - 1)

  return (
    <div className="whatif-timeline">
      <h4 className="whatif-section-title">Lap-time comparison</h4>
      <svg viewBox={`0 0 ${W} ${H}`} className="whatif-svg" role="img" aria-label="Lap time comparison chart">
        {actual.map((lap, i) => {
          const x = 10 + i * (barW + 1)
          const hA = ((lap.lap_time_s - minTime) / range) * (H - 20) + 4
          const cfLap = counterfactual[i]
          const hCF = cfLap ? ((cfLap.lap_time_s - minTime) / range) * (H - 20) + 4 : 0
          const isHist = lap.estimation === 'historical'
          return (
            <g key={lap.lap}>
              {/* Actual bar */}
              <rect
                x={x}
                y={H - hA}
                width={barW * 0.48}
                height={hA}
                fill={isHist ? '#4488cc' : '#2255aa'}
                opacity={0.85}
              />
              {/* Counterfactual bar */}
              {cfLap && (
                <rect
                  x={x + barW * 0.52}
                  y={H - hCF}
                  width={barW * 0.48}
                  height={hCF}
                  fill={cfLap.estimation === 'historical' ? '#cc8844' : '#aa5522'}
                  opacity={0.85}
                />
              )}
              {/* Fork marker */}
              {lap.is_fork_lap && (
                <line
                  x1={x + barW / 2} y1={0}
                  x2={x + barW / 2} y2={H}
                  stroke="#fff" strokeWidth={1} strokeDasharray="3,2" opacity={0.5}
                />
              )}
            </g>
          )
        })}
      </svg>
      <div className="whatif-timeline-legend">
        <span><span className="whatif-legend-swatch" style={{ background: '#4488cc' }} /> Actual (historical)</span>
        <span><span className="whatif-legend-swatch" style={{ background: '#2255aa' }} /> Actual (simulated)</span>
        <span><span className="whatif-legend-swatch" style={{ background: '#cc8844' }} /> What-if (historical)</span>
        <span><span className="whatif-legend-swatch" style={{ background: '#aa5522' }} /> What-if (simulated)</span>
        <span style={{ color: '#aaa' }}>| Fork at lap {forkLap}</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Delta chart (cumulative time gap)
// ---------------------------------------------------------------------------

function DeltaChart({ actual, counterfactual }: {
  actual: BranchLap[]
  counterfactual: BranchLap[]
}) {
  if (!actual.length || !counterfactual.length) return null
  const deltas = actual.map((l, i) => {
    const cf = counterfactual[i]
    return cf ? cf.cumulative_race_time_s - l.cumulative_race_time_s : 0
  })
  const maxAbs = Math.max(...deltas.map(Math.abs), 1)
  const W = 800
  const H = 80
  const barW = Math.max(2, (W - 20) / deltas.length - 1)
  const midY = H / 2

  return (
    <div className="whatif-delta">
      <h4 className="whatif-section-title">Cumulative gap: what-if − actual (s)</h4>
      <svg viewBox={`0 0 ${W} ${H}`} className="whatif-svg" role="img" aria-label="Cumulative gap chart">
        <line x1={10} y1={midY} x2={W - 10} y2={midY} stroke="#444" strokeWidth={1} />
        {deltas.map((d, i) => {
          const x = 10 + i * (barW + 1)
          const h = Math.abs(d) / maxAbs * (midY - 4)
          const y = d >= 0 ? midY - h : midY
          const isFork = actual[i]?.is_fork_lap
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={Math.max(h, 1)}
                fill={d < 0 ? '#6f6' : '#f66'} opacity={0.8} />
              {isFork && (
                <line x1={x} y1={0} x2={x} y2={H}
                  stroke="#fff" strokeWidth={1} strokeDasharray="3,2" opacity={0.4} />
              )}
            </g>
          )
        })}
      </svg>
      <div className="whatif-timeline-legend">
        <span><span className="whatif-legend-swatch" style={{ background: '#6f6' }} /> What-if faster</span>
        <span><span className="whatif-legend-swatch" style={{ background: '#f66' }} /> What-if slower</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Strategy editor (simplified, reusing StrategyLab pattern)
// ---------------------------------------------------------------------------

function StrategyEditorInline({ label, value, onChange, compounds, scheduledLaps }: {
  label: string
  value: StrategyDef
  onChange: (v: StrategyDef) => void
  compounds: string[]
  scheduledLaps: number
}) {
  return (
    <div className="whatif-strategy-editor">
      <h4>{label}</h4>
      <label>
        Start compound
        <select value={value.start_compound}
          onChange={e => onChange({ ...value, start_compound: e.target.value })}>
          {compounds.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      {value.pit_stops.map((s, i) => (
        <div key={i} className="whatif-pit-row">
          <label>
            Pit lap
            <input type="number" min={1} max={scheduledLaps - 1} value={s.lap}
              onChange={e => {
                const stops = value.pit_stops.map((p, j) =>
                  j === i ? { ...p, lap: Number(e.target.value) } : p)
                onChange({ ...value, pit_stops: stops })
              }} />
          </label>
          <label>
            Compound
            <select value={s.compound}
              onChange={e => {
                const stops = value.pit_stops.map((p, j) =>
                  j === i ? { ...p, compound: e.target.value } : p)
                onChange({ ...value, pit_stops: stops })
              }}>
              {compounds.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <button className="whatif-remove" title="Remove"
            onClick={() => onChange({ ...value, pit_stops: value.pit_stops.filter((_, j) => j !== i) })}>
            ✕
          </button>
        </div>
      ))}
      {value.pit_stops.length < 3 && (
        <button className="whatif-add-pit"
          onClick={() => onChange({
            ...value,
            pit_stops: [...value.pit_stops, {
              lap: Math.round(scheduledLaps / 2),
              compound: compounds[0]
            }]
          })}>
          + pit stop
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface WhatIfLabProps {
  sessionSlug: string
  baseUrl: string
}

export default function WhatIfLab({ sessionSlug, baseUrl }: WhatIfLabProps) {
  const [info, setInfo] = useState<StrategyInfo | null>(null)
  const [infoError, setInfoError] = useState<string | null>(null)
  const [forkLap, setForkLap] = useState(30)
  const [driverNumber, setDriverNumber] = useState(1)
  const [actual, setActual] = useState<StrategyDef>({
    start_compound: 'MEDIUM', pit_stops: [{ lap: 37, compound: 'HARD' }]
  })
  const [counterfactual, setCounterfactual] = useState<StrategyDef>({
    start_compound: 'MEDIUM', pit_stops: [{ lap: 25, compound: 'HARD' }]
  })
  const [result, setResult] = useState<BranchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setInfo(null)
    setInfoError(null)
    setResult(null)
    const ctrl = new AbortController()
    fetch(`${baseUrl}/api/v1/strategy/${sessionSlug}/info`, { signal: ctrl.signal })
      .then(r => r.ok ? r.json() : r.json().then((e: { detail: string }) => Promise.reject(e.detail)))
      .then((d: StrategyInfo) => {
        setInfo(d)
        setForkLap(Math.round(d.scheduled_laps * 0.55))
        const avail = d.available_compounds.map(c => c.compound)
        const med = avail.includes('MEDIUM') ? 'MEDIUM' : avail[0]
        const hard = avail.includes('HARD') ? 'HARD' : avail[avail.length - 1]
        setActual({ start_compound: med, pit_stops: [{ lap: Math.round(d.scheduled_laps * 0.70), compound: hard }] })
        setCounterfactual({ start_compound: med, pit_stops: [{ lap: Math.round(d.scheduled_laps * 0.47), compound: hard }] })
      })
      .catch((e: unknown) => { if (!ctrl.signal.aborted) setInfoError(String(e)) })
    return () => ctrl.abort()
  }, [sessionSlug, baseUrl])

  function runBranch() {
    if (!info) return
    setLoading(true)
    setError(null)
    setResult(null)
    fetch(`${baseUrl}/api/v1/strategy/${sessionSlug}/whatif`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ driver_number: driverNumber, fork_lap: forkLap, actual_strategy: actual, counterfactual_strategy: counterfactual }),
    })
      .then(r => r.ok ? r.json() : r.json().then((e: { detail: string }) => Promise.reject(e.detail)))
      .then((d: BranchResult) => { setResult(d); setLoading(false) })
      .catch((e: unknown) => { setError(String(e)); setLoading(false) })
  }

  if (infoError) return (
    <div className="whatif-lab whatif-lab--error">
      <p>What-If Lab unavailable: {infoError}</p>
    </div>
  )
  if (!info) return <div className="whatif-lab whatif-lab--loading"><p>Loading…</p></div>

  const compounds = info.available_compounds.map(c => c.compound)

  return (
    <div className="whatif-lab" data-session={sessionSlug}>
      <header className="whatif-header">
        <h2>What-If Lab</h2>
        <span className="whatif-meta">{sessionSlug}</span>
      </header>

      <p className="whatif-explainer">
        Fork the real race at a chosen lap. Laps 1–{forkLap} use measured times from the replay pack;
        the remaining laps are simulated under each strategy. The fork lap is marked{' '}
        <code>is_fork_lap=true</code> in the output.
      </p>

      <div className="whatif-controls">
        <label>
          Fork lap
          <input type="number" min={1} max={info.scheduled_laps - 1} value={forkLap}
            onChange={e => setForkLap(Number(e.target.value))} />
          <span className="whatif-fork-note">Historical: 1–{forkLap} · Simulated: {forkLap + 1}–{info.scheduled_laps}</span>
        </label>
        <label>
          Driver #
          <input type="number" min={1} max={99} value={driverNumber}
            onChange={e => setDriverNumber(Number(e.target.value))} />
        </label>
      </div>

      <div className="whatif-strategy-grid">
        <StrategyEditorInline
          label="Actual strategy (what happened)"
          value={actual}
          onChange={setActual}
          compounds={compounds}
          scheduledLaps={info.scheduled_laps}
        />
        <StrategyEditorInline
          label="What-if strategy (counterfactual)"
          value={counterfactual}
          onChange={setCounterfactual}
          compounds={compounds}
          scheduledLaps={info.scheduled_laps}
        />
      </div>

      <button className="whatif-run" onClick={runBranch} disabled={loading}>
        {loading ? 'Branching…' : 'Run what-if'}
      </button>

      {error && <p className="whatif-error">{error}</p>}

      {result && (
        <div className="whatif-result">
          <div className="whatif-summary">
            <div className="whatif-summary-card">
              <span className="whatif-summary-label">Actual</span>
              <span className="whatif-summary-label-sub">{result.actual_strategy_label}</span>
              <span className="whatif-summary-time">{fmtTime(result.actual_total_race_time_s)}</span>
            </div>
            <div className={`whatif-summary-delta ${result.counterfactual_is_faster ? 'whatif-delta--faster' : 'whatif-delta--slower'}`}>
              {result.delta_counterfactual_vs_actual_s > 0 ? '+' : ''}
              {result.delta_counterfactual_vs_actual_s.toFixed(3)}s
              <span className="whatif-delta-label">
                {result.counterfactual_is_faster ? '← what-if faster' : '← what-if slower'}
              </span>
            </div>
            <div className="whatif-summary-card">
              <span className="whatif-summary-label">What-if</span>
              <span className="whatif-summary-label-sub">{result.counterfactual_strategy_label}</span>
              <span className="whatif-summary-time">{fmtTime(result.counterfactual_total_race_time_s)}</span>
            </div>
          </div>

          <LapTimeline
            actual={result.actual_laps}
            counterfactual={result.counterfactual_laps}
            forkLap={result.fork_lap}
          />

          <DeltaChart
            actual={result.actual_laps}
            counterfactual={result.counterfactual_laps}
          />

          <details className="whatif-limits">
            <summary>Simulation limits</summary>
            <ul>{result.simulation_limits.map((l, i) => <li key={i}>{l}</li>)}</ul>
          </details>

          <p className="whatif-note">
            Laps 1–{result.fork_lap} are <strong>historical</strong> (measured, both timelines identical);
            laps {result.fork_lap + 1}– are <strong>simulated</strong>.
            Simulated times use model-calibrated coefficients, not the actual driver's pace on this day.
          </p>
        </div>
      )}
    </div>
  )
}
