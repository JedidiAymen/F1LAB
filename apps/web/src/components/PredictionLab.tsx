import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ChevronDown, CircleAlert, FlaskConical } from 'lucide-react'
import './PredictionLab.css'

type Weekend = { year: number; round: number; event: string; split: 'validation' | 'test' }
type Metric = {
  model: string
  events: number
  position_mae: number
  spearman: number
  pole_hit_rate: number
  top3_overlap: number
}
type Feature = { name: string; unit: string; source_sessions: string[] }
type Manifest = {
  task: string
  selected_model: string
  feature_set: string
  features: string[]
  cutoff_audit: {
    prediction_cutoff: string
    features: Feature[]
    source_timestamp: { status: string; rows: number; minimum_utc: string | null; maximum_utc: string | null }
    feature_observed_at: string
    timestamp_limit: string
  }
  dataset_sha256: string
  predictions_sha256: string
  training: Record<string, number>
  summaries: Record<'validation' | 'test', Metric[]>
  uncertainty: Record<'validation' | 'test', Array<{
    model: string; baseline: string; mean_delta: number; ci_low: number; ci_high: number; events: number
  }>>
  events: Weekend[]
}
type Ranking = {
  driver: string
  predicted_rank: Record<'fp3' | 'ridge' | 'lightgbm', number>
  actual_rank: number
}
type EventResult = {
  year: number; round: number; event: string; split: 'validation' | 'test'
  rankings: Ranking[]; metrics: Metric[]
}

const modelNames = { fp3: 'FP3', ridge: 'Ridge', lightgbm: 'LightGBM' }
const displayMetric = (value: number | undefined, digits = 2) =>
  value == null || !Number.isFinite(value) ? '—' : value.toFixed(digits)

function eventKey(event: Weekend) {
  return `${event.year}:${event.round}:${event.split}`
}

export function PredictionLab({ onBack }: { onBack: () => void }) {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [result, setResult] = useState<EventResult | null>(null)
  const [selectedKey, setSelectedKey] = useState('')
  const [split, setSplit] = useState<'test' | 'validation'>('test')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/predictions/qualifying', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json()
          throw new Error(body.detail ?? 'Prediction artifacts unavailable')
        }
        return response.json() as Promise<Manifest>
      })
      .then((data) => {
        setManifest(data)
        const latest = data.events.filter((event) => event.split === 'test').at(-1)
        if (latest) setSelectedKey(eventKey(latest))
      })
      .catch((cause) => {
        if (cause.name !== 'AbortError') setError(String(cause.message ?? cause))
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  const events = useMemo(
    () => manifest?.events.filter((event) => event.split === split) ?? [],
    [manifest, split],
  )
  const selected = events.find((event) => eventKey(event) === selectedKey) ?? events.at(-1)
  const selectedEventUrl = selected
    ? `/api/v1/predictions/qualifying/event?year=${selected.year}&round=${selected.round}&split=${selected.split}`
    : ''
  const resultMatchesSelection = !!selected && result?.year === selected.year
    && result.round === selected.round && result.split === selected.split
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

  const summary = manifest?.summaries[split] ?? []
  const selectedBootstrap = manifest?.uncertainty[split].find(
    (row) => row.model === manifest.selected_model && row.baseline === 'fp3',
  )
  const selectedModelName = manifest
    ? modelNames[manifest.selected_model as keyof typeof modelNames] ?? manifest.selected_model
    : 'Selected model'

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
            <div className="eyebrow">QUALIFYING · EVENT-GROUPED BACKTEST</div>
            <h1>Prediction <span>Lab</span></h1>
            <p>Historical practice-only forecasts, scored against completed qualifying classifications.</p>
          </div>
          <div className="prediction-stamp"><span /> OFFLINE · HISTORICAL</div>
        </div>

        {loading && <div className="prediction-state">Loading the local experiment artifacts…</div>}
        {error && (
          <div className="prediction-error" role="alert">
            <CircleAlert size={18} />
            <div><strong>Prediction artifacts unavailable</strong><p>{error}</p></div>
          </div>
        )}

        {manifest && (
          <>
            <section className="prediction-contract panel" aria-label="Prediction cutoff contract">
              <div className="contract-icon"><FlaskConical size={17} /></div>
              <div>
                <span className="eyebrow">FORECAST MOMENT</span>
                <strong>Immediately before qualifying</strong>
                <p>Inputs are FP1, FP2 and FP3 practice pace features. The actual qualifying order below is retrospective scoring.</p>
              </div>
              <div className="contract-status">
                <span className="dot estimated" /> FEATURE TIMESTAMPS NOT RETAINED
              </div>
            </section>

            <section className="prediction-controls panel" aria-label="Prediction run selection">
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
                <article className={`prediction-metric panel ${metric.model === manifest.selected_model ? 'selected-model' : ''}`} key={metric.model}>
                  <div className="metric-title"><span>{modelNames[metric.model as keyof typeof modelNames] ?? metric.model}</span>
                    {metric.model === manifest.selected_model && <b>SELECTED ON 2024</b>}
                  </div>
                  <strong>{displayMetric(metric.position_mae)}</strong>
                  <span className="metric-label">EVENT MEAN POSITION MAE · LOWER IS BETTER</span>
                  <div className="metric-details">
                    <span>Spearman <b>{displayMetric(metric.spearman, 3)}</b></span>
                    <span>Top-three overlap <b>{displayMetric(metric.top3_overlap, 3)}</b></span>
                    <span>Pole hit <b>{displayMetric(metric.pole_hit_rate, 3)}</b></span>
                  </div>
                </article>
              ))}
            </section>

            <section className="prediction-results panel" aria-label="Weekend prediction rankings">
              <div className="prediction-results-heading">
                <div>
                  <span className="eyebrow">{split === 'test' ? 'UNTOUCHED HOLDOUT' : 'VALIDATION SET'} · {visibleResult?.year ?? selected?.year ?? '—'}</span>
                  <h2>{visibleResult?.event ?? selected?.event ?? 'Weekend rankings'}</h2>
                  <p>Rank order is generated from each model’s predicted Q1 pace. Actual rank is shown to evaluate this historical run.</p>
                </div>
                <span className="event-coverage">{visibleResult?.rankings.length ?? '—'} DRIVERS</span>
              </div>
              {eventLoading && <div className="prediction-table-loading">Loading event predictions…</div>}
              {visibleResult && !eventLoading && (
                <div className="prediction-table-wrap">
                  <table className="prediction-table">
                    <thead><tr><th>MODEL ORDER</th><th>DRIVER</th><th>FP3</th><th>RIDGE</th><th>LIGHTGBM</th><th>ACTUAL QUALI</th></tr></thead>
                    <tbody>{visibleResult.rankings.map((row) => (
                      <tr key={row.driver} className={row.predicted_rank[manifest.selected_model as keyof Ranking['predicted_rank']] === 1 ? 'selected-pole-row' : ''}>
                        <td className="predicted-order">{String(row.predicted_rank[manifest.selected_model as keyof Ranking['predicted_rank']]).padStart(2, '0')}</td>
                        <td className="prediction-driver">{row.driver}</td>
                        {(['fp3', 'ridge', 'lightgbm'] as const).map((model) => <td key={model} className={model === manifest.selected_model ? 'selected-rank' : ''}>
                          {row.predicted_rank[model]}
                        </td>)}
                        <td className="actual-rank">{row.actual_rank}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              {visibleResult && <div className="prediction-event-metrics">
                {visibleResult.metrics.map((metric) => <span key={metric.model}>{modelNames[metric.model as keyof typeof modelNames] ?? metric.model} MAE <b>{displayMetric(metric.position_mae)}</b></span>)}
              </div>}
            </section>

            <section className="prediction-limits panel" aria-label="Model evidence and limitations">
              <div className="limits-header"><div><span className="eyebrow">EVIDENCE & LIMITS</span><h2>What this run can tell us</h2></div>
                <span>{selectedModelName.toUpperCase()} · SELECTED USING 2024 ONLY</span></div>
              <div className="limits-grid">
                <div><span>2025 {selectedModelName.toUpperCase()} − FP3 MAE</span><strong>{selectedBootstrap ? `${displayMetric(selectedBootstrap.mean_delta, 3)} pos.` : '—'}</strong>
                  <small>{selectedBootstrap ? `95% event bootstrap: ${displayMetric(selectedBootstrap.ci_low, 3)} to ${displayMetric(selectedBootstrap.ci_high, 3)}` : 'No paired interval available'}</small>
                </div>
                <div><span>TRAINING WINDOW</span><strong>2022–2023</strong><small>{manifest.training.n_training_events} events · {manifest.training.n_training_rows} drivers</small></div>
                <div><span>VALIDATION / TEST</span><strong>2024 / 2025</strong><small>{manifest.training.n_validation_events} / {manifest.training.n_test_events} events</small></div>
              </div>
              <p className="prediction-caveat">The held-out paired interval crosses zero, so this run does not establish a reliable improvement over FP3. Q1 pace is the model target; final qualifying order is the evaluation label. No probability or confidence estimate is shown.</p>
            </section>

            <details className="feature-registry panel">
              <summary><span><span className="eyebrow">INPUT REGISTRY</span><strong>Eight common practice features</strong></span><ChevronDown size={17} /></summary>
              <div className="feature-registry-grid">{manifest.cutoff_audit.features.map((feature) => <div key={feature.name}>
                <code>{feature.name}</code><span>{feature.source_sessions.join(' + ')}</span><small>{feature.unit}</small>
              </div>)}</div>
              <p>{manifest.cutoff_audit.timestamp_limit}. Dataset SHA-256: <code>{manifest.dataset_sha256.slice(0, 16)}…</code></p>
            </details>
            <footer className="prediction-footer">SOURCE-CACHED EXPERIMENT · {manifest.cutoff_audit.source_timestamp.rows.toLocaleString()} ROW CUTOFF RECORDS · NO LIVE FORECAST</footer>
          </>
        )}
      </main>
    </div>
  )
}
