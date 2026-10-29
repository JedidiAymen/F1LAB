import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ChevronDown, CircleAlert, FlaskConical } from 'lucide-react'
import { ForecastPanel } from './ForecastPanel'
import './PredictionLab.css'

type Split = 'validation' | 'test'
type PhaseKey = 'after_fp1' | 'after_fp2' | 'pre_qualifying'
type Weekend = { year: number; round: number; event: string; split: Split; cutoff_at_utc: string }
type Metric = {
  model: string
  events: number
  position_mae: number
  spearman: number
  pole_hit_rate: number
  top3_overlap: number
}
type Feature = { name: string; unit: string; source_sessions: string[] }
type Phase = {
  key: PhaseKey
  label: string
  practice_session: string
  cutoff_status: string
  baseline: string
  features: Feature[]
  selected_model: string
  models: string[]
  training: Record<string, number | number[]>
  cutoff_coverage: { events: number; minimum_utc: string; maximum_utc: string }
  summaries: Record<Split, Metric[]>
  uncertainty: Record<Split, Array<{
    model: string; baseline: string; mean_delta: number; ci_low: number; ci_high: number; events: number
  }>>
  events: Weekend[]
}
type Manifest = {
  task: string
  source_provider: string
  source_years: number[]
  source_rows: number
  dataset_sha256: string
  schedule_sha256: string
  selection_year: number
  held_out_year: number
  cutoff_contract: string
  feature_observed_at: string
  timing_limit: string
  phases: Phase[]
}
type Ranking = {
  driver: string; predicted_rank: Record<string, number>; actual_rank: number; qualifying_position: number
}
type EventResult = {
  phase: PhaseKey; year: number; round: number; event: string; split: Split
  cutoff_at_utc: string; selected_model: string; models: string[]
  rankings: Ranking[]; metrics: Metric[]
}

const phaseKeys: PhaseKey[] = ['after_fp1', 'after_fp2', 'pre_qualifying']
const modelName = (model: string) => ({
  fp1: 'FP1 Baseline', fp2: 'FP2 Baseline', fp3: 'FP3 Baseline',
  ridge: 'Ridge', lightgbm: 'LightGBM',
}[model] ?? model)
const displayMetric = (value: number | undefined, digits = 2) =>
  value == null || !Number.isFinite(value) ? '—' : value.toFixed(digits)
const eventKey = (event: Weekend) => `${event.year}:${event.round}:${event.split}`

export function PredictionLab({ onBack }: { onBack: () => void }) {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [result, setResult] = useState<EventResult | null>(null)
  const [selectedKey, setSelectedKey] = useState('')
  const [phaseKey, setPhaseKey] = useState<PhaseKey>('pre_qualifying')
  const [split, setSplit] = useState<Split>('test')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/predictions/qualifying/phases', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json()
          throw new Error(body.detail ?? 'Phase-aware prediction artifacts unavailable')
        }
        return response.json() as Promise<Manifest>
      })
      .then((data) => {
        setManifest(data)
        const latest = data.phases.find((phase) => phase.key === 'pre_qualifying')
          ?.events.filter((event) => event.split === 'test').at(-1)
        if (latest) setSelectedKey(eventKey(latest))
      })
      .catch((cause) => {
        if (cause.name !== 'AbortError') setError(String(cause.message ?? cause))
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  const phase = manifest?.phases.find((item) => item.key === phaseKey) ?? manifest?.phases[0]
  const events = useMemo(
    () => phase?.events.filter((event) => event.split === split) ?? [],
    [phase, split],
  )
  const selected = events.find((event) => eventKey(event) === selectedKey) ?? events.at(-1)
  const selectedEventUrl = selected
    ? `/api/v1/predictions/qualifying/phases/event?phase=${phase?.key}&year=${selected.year}&round=${selected.round}&split=${selected.split}`
    : ''
  const resultMatchesSelection = !!selected && result?.phase === phase?.key
    && result?.year === selected.year && result?.round === selected.round && result?.split === selected.split
  const visibleResult = resultMatchesSelection ? result : null
  const eventLoading = !!selected && !visibleResult && !error

  useEffect(() => {
    if (!selectedEventUrl) return
    const controller = new AbortController()
    fetch(selectedEventUrl, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json()
          throw new Error(body.detail ?? 'Weekend prediction unavailable')
        }
        return response.json() as Promise<EventResult>
      })
      .then(setResult)
      .catch((cause) => {
        if (cause.name !== 'AbortError') setError(String(cause.message ?? cause))
      })
    return () => controller.abort()
  }, [selectedEventUrl])

  const summary = phase?.summaries[split] ?? []
  const selectedModelName = phase ? modelName(phase.selected_model) : 'Selected model'
  const comparisonBootstrap = phase?.uncertainty[split].find(
    (row) => row.model === phase.selected_model && row.baseline === phase.baseline,
  ) ?? phase?.uncertainty[split].find((row) => row.baseline === phase.baseline)
  const comparisonModelName = comparisonBootstrap ? modelName(comparisonBootstrap.model) : selectedModelName

  return (
    <div className="workstation prediction-workstation">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">F<span>1</span></div>
          <div className="brand-name">LAB <span>/ RACE INTELLIGENCE</span></div>
        </div>
        <div className="session-id prediction-top-id">
          <FlaskConical size={15} />
          <span>HISTORICAL PREDICTION LAB</span>
        </div>
        <button className="prediction-back" type="button" onClick={onBack}>
          <ArrowLeft size={15} /> Race Control
        </button>
      </header>

      <main className="prediction-main">
        <div className="prediction-heading">
          <div>
            <div className="eyebrow">QUALIFYING · PHASE-AWARE EVENT BACKTEST</div>
            <h1>Prediction <span>Lab</span></h1>
            <p>Historical practice-only forecasts, scored against completed qualifying classifications.</p>
          </div>
          <div className="prediction-stamp"><span /> OFFLINE · HISTORICAL</div>
        </div>

        <ForecastPanel />

        {loading && <div className="prediction-state">Loading the local experiment artifacts…</div>}
        {error && (
          <div className="prediction-error" role="alert">
            <CircleAlert size={18} />
            <div><strong>Prediction artifacts unavailable</strong><p>{error}</p></div>
          </div>
        )}

        {manifest && phase && (
          <>
            <section className="prediction-contract panel" aria-label="Prediction cutoff contract">
              <div className="contract-icon"><FlaskConical size={17} /></div>
              <div>
                <span className="eyebrow">FORECAST MOMENT</span>
                <strong>{phase.label} · {phase.practice_session} scheduled end</strong>
                <p>Uses only practice sessions through this phase. The qualifying order below is retrospective scoring.</p>
              </div>
              <div className="contract-status">
                <span className="dot estimated" /> SOURCE PUBLICATION TIME NOT RETAINED
              </div>
            </section>

            <section className="prediction-controls panel" aria-label="Prediction run selection">
              <div className="prediction-tabs" role="group" aria-label="Forecast moment">
                {phaseKeys.map((key) => {
                  const item = manifest.phases.find((candidate) => candidate.key === key)
                  return <button key={key} type="button" className={phaseKey === key ? 'active' : ''}
                    onClick={() => { setPhaseKey(key); setError(null); setResult(null) }}>
                    {item?.label ?? key}
                  </button>
                })}
              </div>
              <div className="prediction-tabs" role="group" aria-label="Evaluation split">
                <button type="button" className={split === 'test' ? 'active' : ''} onClick={() => {
                  setSplit('test'); setSelectedKey(''); setError(null); setResult(null)
                }}>2025 · HELD OUT</button>
                <button type="button" className={split === 'validation' ? 'active' : ''} onClick={() => {
                  setSplit('validation'); setSelectedKey(''); setError(null); setResult(null)
                }}>2024 · MODEL SELECTION</button>
              </div>
              <label className="prediction-weekend-select">
                <span className="eyebrow">GRAND PRIX</span>
                <span className="select-wrap">
                  <select
                    aria-label="Historical Grand Prix"
                    value={selected ? eventKey(selected) : ''}
                    onChange={(event) => { setSelectedKey(event.target.value); setError(null); setResult(null) }}
                  >
                    {events.map((event) => <option key={eventKey(event)} value={eventKey(event)}>
                      {event.year} · R{String(event.round).padStart(2, '0')} · {event.event}
                    </option>)}
                  </select>
                  <ChevronDown size={15} />
                </span>
              </label>
            </section>

            <section className="prediction-metrics" aria-label={`${split} model metrics`}>
              {summary.map((metric) => (
                <article className={`prediction-metric panel ${metric.model === phase.selected_model ? 'selected-model' : ''}`} key={metric.model}>
                  <div className="metric-title"><span>{modelName(metric.model)}</span>
                    {metric.model === phase.selected_model && <b>SELECTED ON 2024</b>}
                  </div>
                  <strong>{displayMetric(metric.position_mae)}</strong>
                  <span className="metric-label">EVENT MEAN POSITION MAE · LOWER IS BETTER</span>
                  <div className="metric-details">
                    <span>Spearman <b>{displayMetric(metric.spearman, 3)}</b></span>
                    <span>Eligible top-three <b>{displayMetric(metric.top3_overlap, 3)}</b></span>
                    <span>Eligible leader hit <b>{displayMetric(metric.pole_hit_rate, 3)}</b></span>
                  </div>
                </article>
              ))}
            </section>

            <section className="prediction-results panel" aria-label="Weekend prediction rankings">
              <div className="prediction-results-heading">
                <div>
                  <span className="eyebrow">{split === 'test' ? 'UNTOUCHED HOLDOUT' : 'VALIDATION SET'} · {visibleResult?.year ?? selected?.year ?? '—'}</span>
                  <h2>{visibleResult?.event ?? selected?.event ?? 'Weekend rankings'}</h2>
                  <p>{phase.label} forecast from source schedule cutoff {visibleResult?.cutoff_at_utc ?? selected?.cutoff_at_utc ?? '—'}.</p>
                  <p>Ranks and metrics cover drivers with a measured phase baseline and Q1 result. Official qualifying position is shown separately.</p>
                </div>
                <span className="event-coverage">{visibleResult?.rankings.length ?? '—'} DRIVERS</span>
              </div>
              {eventLoading && <div className="prediction-table-loading">Loading event predictions…</div>}
              {visibleResult && !eventLoading && (
                <div className="prediction-table-wrap">
                  <table className="prediction-table">
                    <thead><tr><th>MODEL ORDER</th><th>DRIVER</th>
                      {visibleResult.models.map((model) => <th key={model}>{modelName(model)}</th>)}
                      <th>ACTUAL ELIGIBLE RANK</th><th>Q CLASSIFICATION</th></tr></thead>
                    <tbody>{visibleResult.rankings.map((row) => (
                      <tr key={row.driver} className={row.predicted_rank[phase.selected_model] === 1 ? 'selected-pole-row' : ''}>
                        <td className="predicted-order">{String(row.predicted_rank[phase.selected_model]).padStart(2, '0')}</td>
                        <td className="prediction-driver">{row.driver}</td>
                        {visibleResult.models.map((model) => <td key={model} className={model === phase.selected_model ? 'selected-rank' : ''}>
                          {row.predicted_rank[model]}
                        </td>)}
                        <td className="actual-rank">{row.actual_rank}</td>
                        <td className="actual-rank">{row.qualifying_position}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              {visibleResult && <div className="prediction-event-metrics">
                {visibleResult.metrics.map((metric) => <span key={metric.model}>{modelName(metric.model)} MAE <b>{displayMetric(metric.position_mae)}</b></span>)}
              </div>}
            </section>

            <section className="prediction-limits panel" aria-label="Model evidence and limitations">
              <div className="limits-header"><div><span className="eyebrow">EVIDENCE & LIMITS</span><h2>What this run can tell us</h2></div>
                <span>{selectedModelName.toUpperCase()} · SELECTED USING 2024 ONLY</span></div>
              <div className="limits-grid">
                <div><span>{split === 'test' ? manifest.held_out_year : manifest.selection_year} {comparisonModelName.toUpperCase()} − {modelName(phase.baseline).toUpperCase()} MAE</span>
                  <strong>{comparisonBootstrap ? `${displayMetric(comparisonBootstrap.mean_delta, 3)} pos.` : '—'}</strong>
                  <small>{comparisonBootstrap ? `95% event bootstrap: ${displayMetric(comparisonBootstrap.ci_low, 3)} to ${displayMetric(comparisonBootstrap.ci_high, 3)}` : 'No paired interval available'}</small>
                </div>
                <div><span>TRAINING WINDOW</span><strong>2023</strong><small>{phase.training.n_training_events} events · {phase.training.n_training_rows} drivers</small></div>
                <div><span>VALIDATION / TEST</span><strong>2024 / 2025</strong><small>{phase.training.n_validation_events} / {phase.training.n_test_events} events</small></div>
              </div>
              <p className="prediction-caveat">Paired event bootstrap intervals describe historical spread and may cross zero. Q1 pace is the model target; final qualifying order is the evaluation label. Scheduled practice end does not prove result publication time. Phase-aware models below show ranks only; calibrated probabilities are in the walk-forward forecast above.</p>
            </section>

            <details className="feature-registry panel">
              <summary><span><span className="eyebrow">INPUT REGISTRY</span><strong>{phase.features.length} phase-legal practice features</strong></span><ChevronDown size={17} /></summary>
              <div className="feature-registry-grid">{phase.features.map((feature) => <div key={feature.name}>
                <code>{feature.name}</code><span>{feature.source_sessions.join(' + ')}</span><small>{feature.unit}</small>
              </div>)}</div>
              <p>{manifest.timing_limit}. Dataset SHA-256: <code>{manifest.dataset_sha256.slice(0, 16)}…</code></p>
            </details>
            <footer className="prediction-footer">OPENF1 · 2023–2025 · {phase.cutoff_coverage.events} SCHEDULED CUTOFFS · NO LIVE FORECAST</footer>
          </>
        )}
      </main>
    </div>
  )
}
