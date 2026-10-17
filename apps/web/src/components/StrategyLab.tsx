import { useEffect, useRef, useState } from 'react'
import './StrategyLab.css'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CompoundInfo {
  compound: string
  lap_time_offset_s: number
  linear_s_per_lap: number
}

interface StrategyInfo {
  session_slug: string
  scheduled_laps: number
  base_lap_time_s: number
  safety_car_laps: number[]
  available_compounds: CompoundInfo[]
  simulation_limits: string[]
}

interface RankedStrategy {
  rank?: number
  label: string
  stops: number
  total_race_time_s: number
  delta_vs_reference_s: number | null
  pit_laps: number[]
  compounds: string[]
  simulation_limits: string[]
}

interface MCRankedStrategy {
  rank: number
  strategy_label: string
  driver_number: number
  mean_race_time_s: number
  std_race_time_s: number
  p5_race_time_s: number
  p50_race_time_s: number
  p95_race_time_s: number
  mean_delta_vs_fastest_s: number
  win_fraction: number
  simulation_limits: string[]
}

interface PitStopEntry {
  lap: number
  compound: string
}

interface CustomStrategy {
  start_compound: string
  pit_stops: PitStopEntry[]
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: '#e8002d',
  MEDIUM: '#ffd700',
  HARD: '#f0f0f0',
  INTERMEDIATE: '#39b54a',
  WET: '#0067ff',
}

function CompoundBadge({ compound }: { compound: string }) {
  const color = COMPOUND_COLORS[compound] ?? '#888'
  return (
    <span
      className="strategy-compound-badge"
      style={{ backgroundColor: color, color: compound === 'HARD' ? '#000' : undefined }}
      title={compound}
    >
      {compound[0]}
    </span>
  )
}

function fmtRaceTime(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = (s % 60).toFixed(3)
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec.padStart(6, '0')}` : `${m}:${sec.padStart(6, '0')}`
}

function fmtDelta(d: number | null): string {
  if (d === null) return '—'
  if (d === 0) return 'fastest'
  return `+${d.toFixed(3)}s`
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface StrategyLabProps {
  sessionSlug: string
  baseUrl: string
}

export default function StrategyLab({ sessionSlug, baseUrl }: StrategyLabProps) {
  const [info, setInfo] = useState<StrategyInfo | null>(null)
  const [infoError, setInfoError] = useState<string | null>(null)

  // Best-strategies mode
  const [bestResults, setBestResults] = useState<RankedStrategy[] | null>(null)
  const [bestLoading, setBestLoading] = useState(false)
  const [bestError, setBestError] = useState<string | null>(null)
  const [maxStops, setMaxStops] = useState(1)
  const [topN, setTopN] = useState(8)
  const [pitStep, setPitStep] = useState(3)
  const [selectedCompounds, setSelectedCompounds] = useState<string[]>(['MEDIUM', 'HARD'])

  // Custom comparison mode
  const [customA, setCustomA] = useState<CustomStrategy>({ start_compound: 'MEDIUM', pit_stops: [{ lap: 30, compound: 'HARD' }] })
  const [customB, setCustomB] = useState<CustomStrategy>({ start_compound: 'MEDIUM', pit_stops: [{ lap: 25, compound: 'HARD' }] })
  const [compareResults, setCompareResults] = useState<RankedStrategy[] | null>(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareError, setCompareError] = useState<string | null>(null)

  // Monte Carlo mode
  const [mcResults, setMcResults] = useState<MCRankedStrategy[] | null>(null)
  const [mcLoading, setMcLoading] = useState(false)
  const [mcError, setMcError] = useState<string | null>(null)
  const [nWorlds, setNWorlds] = useState(200)

  const [activeTab, setActiveTab] = useState<'best' | 'compare' | 'mc'>('best')

  const abortRef = useRef<AbortController | null>(null)

  // Load info on session change
  useEffect(() => {
    setInfo(null)
    setInfoError(null)
    setBestResults(null)
    setCompareResults(null)
    setMcResults(null)
    const ctrl = new AbortController()
    fetch(`${baseUrl}/api/v1/strategy/${sessionSlug}/info`, { signal: ctrl.signal })
      .then(r => r.ok ? r.json() : r.json().then((e: { detail: string }) => Promise.reject(e.detail)))
      .then((d: StrategyInfo) => {
        setInfo(d)
        const avail = d.available_compounds.map(c => c.compound)
        setSelectedCompounds(avail.slice(0, 2))
        if (avail.includes('MEDIUM') && avail.includes('HARD')) {
          setSelectedCompounds(['MEDIUM', 'HARD'])
          setCustomA({ start_compound: 'MEDIUM', pit_stops: [{ lap: Math.round(d.scheduled_laps * 0.60), compound: 'HARD' }] })
          setCustomB({ start_compound: 'MEDIUM', pit_stops: [{ lap: Math.round(d.scheduled_laps * 0.45), compound: 'HARD' }] })
        }
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return
        setInfoError(String(e))
      })
    return () => ctrl.abort()
  }, [sessionSlug, baseUrl])

  function abort() {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    return abortRef.current.signal
  }

  function runBest() {
    if (!info) return
    setBestLoading(true)
    setBestError(null)
    setBestResults(null)
    const signal = abort()
    const params = new URLSearchParams({
      max_stops: String(maxStops),
      top_n: String(topN),
      pit_step: String(pitStep),
      compounds: selectedCompounds.join(','),
    })
    fetch(`${baseUrl}/api/v1/strategy/${sessionSlug}/best?${params}`, { signal })
      .then(r => r.ok ? r.json() : r.json().then((e: { detail: string }) => Promise.reject(e.detail)))
      .then((d: { ranked: RankedStrategy[] }) => { setBestResults(d.ranked); setBestLoading(false) })
      .catch((e: unknown) => {
        if ((e as Error)?.name === 'AbortError') return
        setBestError(String(e)); setBestLoading(false)
      })
  }

  function runCompare() {
    if (!info) return
    setCompareLoading(true)
    setCompareError(null)
    setCompareResults(null)
    const signal = abort()
    fetch(`${baseUrl}/api/v1/strategy/${sessionSlug}/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategies: [{ ...customA, driver_number: 1 }, { ...customB, driver_number: 1 }] }),
      signal,
    })
      .then(r => r.ok ? r.json() : r.json().then((e: { detail: string }) => Promise.reject(e.detail)))
      .then((d: { ranked: RankedStrategy[] }) => { setCompareResults(d.ranked); setCompareLoading(false) })
      .catch((e: unknown) => {
        if ((e as Error)?.name === 'AbortError') return
        setCompareError(String(e)); setCompareLoading(false)
      })
  }

  function runMC() {
    if (!info) return
    setMcLoading(true)
    setMcError(null)
    setMcResults(null)
    const signal = abort()
    fetch(`${baseUrl}/api/v1/strategy/${sessionSlug}/montecarlo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        strategies: [{ ...customA, driver_number: 1 }, { ...customB, driver_number: 1 }],
        n_worlds: nWorlds,
        seed: 42,
      }),
      signal,
    })
      .then(r => r.ok ? r.json() : r.json().then((e: { detail: string }) => Promise.reject(e.detail)))
      .then((d: { ranked: MCRankedStrategy[] }) => { setMcResults(d.ranked); setMcLoading(false) })
      .catch((e: unknown) => {
        if ((e as Error)?.name === 'AbortError') return
        setMcError(String(e)); setMcLoading(false)
      })
  }

  function toggleCompound(c: string) {
    setSelectedCompounds(prev =>
      prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]
    )
  }

  if (infoError) {
    return (
      <div className="strategy-lab strategy-lab--error">
        <p>Strategy Lab unavailable: {infoError}</p>
      </div>
    )
  }
  if (!info) {
    return <div className="strategy-lab strategy-lab--loading"><p>Loading strategy model…</p></div>
  }

  const limits = info.simulation_limits

  return (
    <div className="strategy-lab" data-session={sessionSlug}>
      <header className="strategy-lab-header">
        <h2>Strategy Lab</h2>
        <span className="strategy-lab-meta">
          {sessionSlug} · {info.scheduled_laps} laps · base {info.base_lap_time_s.toFixed(3)}s
          {info.safety_car_laps.length > 0 && ` · SC laps ${info.safety_car_laps.join(',')}`}
        </span>
      </header>

      <div className="strategy-lab-tabs" role="tablist">
        {(['best', 'compare', 'mc'] as const).map(t => (
          <button
            key={t}
            role="tab"
            aria-selected={activeTab === t}
            className={`strategy-lab-tab${activeTab === t ? ' strategy-lab-tab--active' : ''}`}
            onClick={() => setActiveTab(t)}
          >
            {t === 'best' ? 'Best Strategies' : t === 'compare' ? 'Custom Compare' : 'Monte Carlo'}
          </button>
        ))}
      </div>

      {/* ---- BEST STRATEGIES TAB ---- */}
      {activeTab === 'best' && (
        <div className="strategy-lab-panel" role="tabpanel">
          <div className="strategy-lab-controls">
            <label>
              Max stops
              <select value={maxStops} onChange={e => setMaxStops(Number(e.target.value))}>
                {[0, 1, 2, 3].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label>
              Top N
              <select value={topN} onChange={e => setTopN(Number(e.target.value))}>
                {[5, 8, 10, 15, 20].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label>
              Pit step
              <select value={pitStep} onChange={e => setPitStep(Number(e.target.value))}>
                {[1, 2, 3, 5].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <fieldset className="strategy-lab-compounds">
              <legend>Compounds</legend>
              {info.available_compounds.map(({ compound }) => (
                <label key={compound} className="strategy-lab-compound-check">
                  <input
                    type="checkbox"
                    checked={selectedCompounds.includes(compound)}
                    onChange={() => toggleCompound(compound)}
                  />
                  <CompoundBadge compound={compound} />
                  {compound}
                </label>
              ))}
            </fieldset>
            <button
              className="strategy-lab-run"
              onClick={runBest}
              disabled={bestLoading || selectedCompounds.length === 0}
            >
              {bestLoading ? 'Simulating…' : 'Find Best Strategies'}
            </button>
          </div>
          {bestError && <p className="strategy-lab-error">{bestError}</p>}
          {bestResults && <StrategyTable rows={bestResults} />}
        </div>
      )}

      {/* ---- CUSTOM COMPARE TAB ---- */}
      {activeTab === 'compare' && (
        <div className="strategy-lab-panel" role="tabpanel">
          <div className="strategy-lab-custom-grid">
            <StrategyEditor
              label="Strategy A"
              value={customA}
              onChange={setCustomA}
              compounds={info.available_compounds.map(c => c.compound)}
              scheduledLaps={info.scheduled_laps}
            />
            <StrategyEditor
              label="Strategy B"
              value={customB}
              onChange={setCustomB}
              compounds={info.available_compounds.map(c => c.compound)}
              scheduledLaps={info.scheduled_laps}
            />
          </div>
          <button
            className="strategy-lab-run"
            onClick={runCompare}
            disabled={compareLoading}
          >
            {compareLoading ? 'Simulating…' : 'Compare Strategies'}
          </button>
          {compareError && <p className="strategy-lab-error">{compareError}</p>}
          {compareResults && <StrategyTable rows={compareResults} />}
        </div>
      )}

      {/* ---- MONTE CARLO TAB ---- */}
      {activeTab === 'mc' && (
        <div className="strategy-lab-panel" role="tabpanel">
          <div className="strategy-lab-custom-grid">
            <StrategyEditor
              label="Strategy A"
              value={customA}
              onChange={setCustomA}
              compounds={info.available_compounds.map(c => c.compound)}
              scheduledLaps={info.scheduled_laps}
            />
            <StrategyEditor
              label="Strategy B"
              value={customB}
              onChange={setCustomB}
              compounds={info.available_compounds.map(c => c.compound)}
              scheduledLaps={info.scheduled_laps}
            />
          </div>
          <label className="strategy-lab-worlds">
            Worlds (noise draws)
            <select value={nWorlds} onChange={e => setNWorlds(Number(e.target.value))}>
              {[50, 100, 200, 500].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button
            className="strategy-lab-run"
            onClick={runMC}
            disabled={mcLoading}
          >
            {mcLoading ? `Running ${nWorlds} worlds…` : `Run Monte Carlo (${nWorlds} worlds)`}
          </button>
          {mcError && <p className="strategy-lab-error">{mcError}</p>}
          {mcResults && <MCTable rows={mcResults} />}
        </div>
      )}

      <details className="strategy-lab-limits">
        <summary>Simulation limits</summary>
        <ul>
          {limits.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </details>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Strategy editor
// ---------------------------------------------------------------------------

interface StrategyEditorProps {
  label: string
  value: CustomStrategy
  onChange: (v: CustomStrategy) => void
  compounds: string[]
  scheduledLaps: number
}

function StrategyEditor({ label, value, onChange, compounds, scheduledLaps }: StrategyEditorProps) {
  function setStartCompound(c: string) {
    onChange({ ...value, start_compound: c })
  }
  function addPit() {
    const lastLap = value.pit_stops.at(-1)?.lap ?? Math.round(scheduledLaps / 2)
    onChange({ ...value, pit_stops: [...value.pit_stops, { lap: lastLap + 5, compound: compounds[0] }] })
  }
  function removePit(i: number) {
    onChange({ ...value, pit_stops: value.pit_stops.filter((_, j) => j !== i) })
  }
  function updatePit(i: number, field: 'lap' | 'compound', v: string | number) {
    const stops = value.pit_stops.map((s, j) => j === i ? { ...s, [field]: v } : s)
    onChange({ ...value, pit_stops: stops })
  }

  return (
    <div className="strategy-editor">
      <h4>{label}</h4>
      <label>
        Start compound
        <select value={value.start_compound} onChange={e => setStartCompound(e.target.value)}>
          {compounds.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      {value.pit_stops.map((stop, i) => (
        <div key={i} className="strategy-editor-pit">
          <label>
            Pit lap
            <input type="number" min={1} max={scheduledLaps - 1} value={stop.lap}
              onChange={e => updatePit(i, 'lap', Number(e.target.value))} />
          </label>
          <label>
            New compound
            <select value={stop.compound} onChange={e => updatePit(i, 'compound', e.target.value)}>
              {compounds.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <button className="strategy-editor-remove" onClick={() => removePit(i)} title="Remove pit stop">✕</button>
        </div>
      ))}
      {value.pit_stops.length < 3 && (
        <button className="strategy-editor-add" onClick={addPit}>+ Add pit stop</button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Results tables
// ---------------------------------------------------------------------------

function StrategyTable({ rows }: { rows: RankedStrategy[] }) {
  return (
    <div className="strategy-table-wrap">
      <table className="strategy-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Label</th>
            <th>Stops</th>
            <th>Stints</th>
            <th>Race time</th>
            <th>Delta</th>
            <th>Pit laps</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.label} className={i === 0 ? 'strategy-table-best' : ''}>
              <td>{(r.rank ?? i + 1)}</td>
              <td className="strategy-table-label">{r.label}</td>
              <td>{r.stops}</td>
              <td className="strategy-table-stints">
                {r.compounds.map((c, j) => <CompoundBadge key={j} compound={c} />)}
              </td>
              <td className="strategy-table-time">{fmtRaceTime(r.total_race_time_s)}</td>
              <td className="strategy-table-delta">{fmtDelta(r.delta_vs_reference_s)}</td>
              <td>{r.pit_laps.join(', ') || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="strategy-table-note">All results are simulated estimates — not measured race times.</p>
    </div>
  )
}

function MCTable({ rows }: { rows: MCRankedStrategy[] }) {
  return (
    <div className="strategy-table-wrap">
      <table className="strategy-table strategy-table--mc">
        <thead>
          <tr>
            <th>#</th>
            <th>Label</th>
            <th>Mean</th>
            <th>±σ</th>
            <th>P5</th>
            <th>P95</th>
            <th>Win %</th>
            <th>vs fastest</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.strategy_label} className={i === 0 ? 'strategy-table-best' : ''}>
              <td>{r.rank}</td>
              <td className="strategy-table-label">{r.strategy_label}</td>
              <td className="strategy-table-time">{fmtRaceTime(r.mean_race_time_s)}</td>
              <td>{r.std_race_time_s.toFixed(2)}s</td>
              <td>{fmtRaceTime(r.p5_race_time_s)}</td>
              <td>{fmtRaceTime(r.p95_race_time_s)}</td>
              <td className="strategy-table-win">{(r.win_fraction * 100).toFixed(1)}%</td>
              <td className="strategy-table-delta">
                {r.mean_delta_vs_fastest_s === 0 ? 'fastest' : `+${r.mean_delta_vs_fastest_s.toFixed(3)}s`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="strategy-table-note">Monte Carlo (shared noise worlds). All results are simulated estimates.</p>
    </div>
  )
}
