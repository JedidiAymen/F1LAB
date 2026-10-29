import { useEffect, useMemo, useState } from 'react'
import './ForecastPanel.css'

type SummaryRow = {
  model: string; year: number; events: number; position_mae: number
  spearman: number; pole_hit_rate: number; top3_overlap: number
}
type BootRow = {
  window: string; model: string; mean_delta: number; ci_low: number; ci_high: number; events: number
}
type ReliabilityRow = { target: string; n: number; mean_predicted: number; observed: number }
type WeekendRef = { year: number; round: number; event: string }
type Manifest = {
  experiment: {
    warmup_events: number; mc_draws: number; seed: number; features: string[]
    audit: {
      events: number; driver_rows: number
      brier_pole: number; brier_pole_uniform: number
      brier_top3: number; brier_top3_uniform: number
      rank_interval_nominal: number; rank_interval_coverage: number
    }
  }
  summary: SummaryRow[]
  bootstrap: BootRow[]
  reliability: ReliabilityRow[]
  events: WeekendRef[]
}
type DriverForecast = {
  driver: string
  predicted_rank: Record<string, number>
  actual_rank: number
  p_pole: number | null
  p_top3: number | null
  expected_rank: number | null
  rank_p10: number | null
  rank_p90: number | null
}
type EventForecast = {
  year: number; round: number; event: string; probabilistic: boolean; drivers: DriverForecast[]
}

const pct = (value: number | null | undefined, digits = 0) =>
  value == null ? '—' : `${(value * 100).toFixed(digits)}%`
const fixed = (value: number | null | undefined, digits = 2) =>
  value == null || !Number.isFinite(value) ? '—' : value.toFixed(digits)
const key = (event: WeekendRef) => `${event.year}:${event.round}`

function Reliability({ rows, target }: { rows: ReliabilityRow[]; target: 'pole' | 'top3' }) {
  const size = 150
  const pad = 22
  const scale = (value: number) => pad + value * (size - pad * 1.4)
  const flip = (value: number) => size - scale(value)
  const points = rows.filter((row) => row.target === target)
  return (
    <figure className="reliability">
      <svg viewBox={`0 0 ${size} ${size}`} role="img"
        aria-label={`${target} reliability: forecast probability versus observed frequency`}>
        <line className="axis" x1={pad} y1={flip(0)} x2={scale(1)} y2={flip(0)} />
        <line className="axis" x1={pad} y1={flip(0)} x2={pad} y2={flip(1)} />
        <line className="ideal" x1={scale(0)} y1={flip(0)} x2={scale(1)} y2={flip(1)} />
        {points.map((row) => (
          <circle key={`${row.mean_predicted}`} cx={scale(row.mean_predicted)} cy={flip(row.observed)}
            r={2.5 + Math.min(5, Math.sqrt(row.n) / 3)}>
            <title>{`${row.n} drivers · forecast ${pct(row.mean_predicted)} · observed ${pct(row.observed)}`}</title>
          </circle>
        ))}
        <text x={scale(0.5)} y={size - 3} textAnchor="middle">forecast</text>
        <text x={7} y={flip(0.5)} textAnchor="middle" transform={`rotate(-90 7 ${flip(0.5)})`}>observed</text>
      </svg>
      <figcaption>P({target === 'pole' ? 'pole' : 'top 3'}) reliability · dashed = perfect</figcaption>
    </figure>
  )
}

export function ForecastPanel() {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [selected, setSelected] = useState('')
  const [event, setEvent] = useState<EventForecast | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/predictions/qualifying/walkforward', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json()).detail ?? 'unavailable')
        return response.json() as Promise<Manifest>
      })
      .then((data) => {
        setManifest(data)
        const last = data.events.at(-1)
        if (last) setSelected(key(last))
      })
      .catch((cause) => { if (cause.name !== 'AbortError') setError(String(cause.message ?? cause)) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!selected) return
    const [year, round] = selected.split(':')
    const controller = new AbortController()
    fetch(`/api/v1/predictions/qualifying/walkforward/event?year=${year}&round=${round}`, { signal: controller.signal })
      .then((response) => response.json() as Promise<EventForecast>)
      .then(setEvent)
      .catch((cause) => { if (cause.name !== 'AbortError') setError(String(cause.message ?? cause)) })
    return () => controller.abort()
  }, [selected])

  const headline = useMemo(() => {
    if (!manifest) return null
    const ensemble = manifest.bootstrap.find((row) => row.model === 'ensemble' && row.window === '2024-2025')
    const mae = (model: string) => {
      const rows = manifest.summary.filter((row) => row.model === model)
      const events = rows.reduce((sum, row) => sum + row.events, 0)
      return rows.reduce((sum, row) => sum + row.position_mae * row.events, 0) / Math.max(events, 1)
    }
    return { ensemble, ensembleMae: mae('ensemble'), baselineMae: mae('latest_practice') }
  }, [manifest])

  if (error && !manifest) {
    return <section className="forecast panel" aria-label="Walk-forward forecast">
      <span className="eyebrow">WALK-FORWARD FORECAST</span>
      <p className="forecast-note">Unavailable: {error}</p>
    </section>
  }
  if (!manifest || !headline) return null

  const audit = manifest.experiment.audit
  const drivers = event?.drivers ?? []
  const maxRank = Math.max(20, ...drivers.map((driver) => driver.actual_rank))
  const x = (rank: number) => `${((rank - 1) / (maxRank - 1)) * 100}%`
  const lift = headline.ensemble

  return (
    <section className="forecast panel" aria-label="Walk-forward probabilistic forecast">
      <div className="forecast-heading">
        <div>
          <span className="eyebrow">WALK-FORWARD · PROBABILISTIC · 2024–2025</span>
          <h2>Ensemble forecast with rank probabilities</h2>
          <p>Every event is scored by models fitted only on earlier weekends. Ridge + LightGBM + LambdaRank are
            averaged; noise scale and width are learned from earlier events' errors, then simulated {manifest.experiment.mc_draws.toLocaleString()} times.</p>
        </div>
        <label className="forecast-select">
          <span className="eyebrow">GRAND PRIX</span>
          <select aria-label="Walk-forward Grand Prix" value={selected} onChange={(e) => { setEvent(null); setSelected(e.target.value) }}>
            {manifest.events.map((item) => (
              <option key={key(item)} value={key(item)}>{item.year} · R{String(item.round).padStart(2, '0')} · {item.event}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="forecast-evidence">
        <div>
          <span>Position MAE vs latest practice</span>
          <strong>{fixed(headline.ensembleMae)} <small>vs {fixed(headline.baselineMae)}</small></strong>
          <em>{lift ? `Δ ${fixed(lift.mean_delta, 2)} [${fixed(lift.ci_low, 2)}, ${fixed(lift.ci_high, 2)}] · ${lift.events} events` : ''}</em>
        </div>
        <div>
          <span>Pole Brier (lower better)</span>
          <strong>{fixed(audit.brier_pole, 4)} <small>vs {fixed(audit.brier_pole_uniform, 4)} uniform</small></strong>
          <em>{audit.driver_rows} driver forecasts</em>
        </div>
        <div>
          <span>Top-3 Brier</span>
          <strong>{fixed(audit.brier_top3, 4)} <small>vs {fixed(audit.brier_top3_uniform, 4)} uniform</small></strong>
          <em>Calibration via reliability plots</em>
        </div>
        <div>
          <span>P10–P90 rank interval coverage</span>
          <strong>{pct(audit.rank_interval_coverage, 1)} <small>nominal {pct(audit.rank_interval_nominal)}</small></strong>
          <em>{audit.rank_interval_coverage > audit.rank_interval_nominal + 0.05 ? 'Conservative: intervals wider than needed' : 'Close to nominal'}</em>
        </div>
      </div>

      <div className="forecast-body">
        <div className="forecast-table-wrap">
          <table className="forecast-table">
            <thead>
              <tr><th>#</th><th>DRIVER</th><th>P(POLE)</th><th>P(TOP 3)</th><th className="rank-col">RANK RANGE (P10–P90)</th><th>ACTUAL</th></tr>
            </thead>
            <tbody>
              {drivers.map((driver, index) => {
                const hit = driver.rank_p10 != null && driver.rank_p90 != null
                  && driver.actual_rank >= driver.rank_p10 && driver.actual_rank <= driver.rank_p90
                return (
                  <tr key={driver.driver}>
                    <td className="forecast-order">{String(index + 1).padStart(2, '0')}</td>
                    <td className="forecast-driver">{driver.driver}</td>
                    <td><span className="bar-cell"><i className="bar pole" style={{ width: pct(driver.p_pole) }} />{pct(driver.p_pole)}</span></td>
                    <td><span className="bar-cell"><i className="bar top3" style={{ width: pct(driver.p_top3) }} />{pct(driver.p_top3)}</span></td>
                    <td className="rank-col">
                      <div className="rank-track" aria-label={`Rank ${fixed(driver.rank_p10, 0)} to ${fixed(driver.rank_p90, 0)}, actual ${driver.actual_rank}`}>
                        {driver.rank_p10 != null && driver.rank_p90 != null && (
                          <span className="rank-range" style={{ left: x(driver.rank_p10), width: `calc(${x(driver.rank_p90)} - ${x(driver.rank_p10)})` }} />
                        )}
                        {driver.expected_rank != null && <span className="rank-mean" style={{ left: x(driver.expected_rank) }} />}
                        <span className={`rank-actual ${hit ? 'hit' : 'miss'}`} style={{ left: x(driver.actual_rank) }} title={`Actual eligible rank ${driver.actual_rank}`} />
                      </div>
                    </td>
                    <td className="forecast-actual">{driver.actual_rank}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="forecast-legend">
            <i className="bar pole" /> probability · <span className="rank-mean inline" /> expected rank ·
            <span className="rank-actual hit inline" /> actual inside range · <span className="rank-actual miss inline" /> outside range.
            Actual rank is retrospective scoring among eligible drivers.
          </p>
        </div>
        <aside className="forecast-reliability">
          <Reliability rows={manifest.reliability} target="pole" />
          <Reliability rows={manifest.reliability} target="top3" />
        </aside>
      </div>
      <p className="forecast-note">
        Features are practice-only or from strictly earlier weekends. Probabilities treat drivers as independent
        (teammate correlation ignored). Scheduled practice end is not provider publication time; no live forecast is made.
      </p>
    </section>
  )
}
