import { useEffect, useState } from 'react'

type ErrorStats = { mae: number; median_ae: number; rmse: number }
type Horizon = { rows: number; races: number; models: Record<string, ErrorStats>; paired_lightgbm_vs_last_observed: { mean_delta: number; ci_low: number; ci_high: number }; interval: { coverage: number; mean_width_raw: number; crossings: number; pinball_q10: number; pinball_q90: number }; by_year: Record<string, { n: number; lightgbm_mae: number; last_observed_mae: number }> }
type Study = { summary: { population: Record<string, { decision_rows: number; missing_target: number; target_present_missing_intermediate: number; scored_eligible: number }>; horizons: Record<string, Horizon> }; source_sha256: string }

export function MultiHorizonStudy() {
  const [study, setStudy] = useState<Study | null>(null)
  const [missing, setMissing] = useState(false)
  const [horizon, setHorizon] = useState('1')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/research/pace-multihorizon', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('Unavailable')
      return response.json() as Promise<Study>
    }).then(setStudy).catch(cause => { if (cause.name !== 'AbortError') setMissing(true) })
    return () => controller.abort()
  }, [])
  const result = study?.summary.horizons[horizon]
  const population = study?.summary.population[horizon]
  const points = study ? ['1', '3', '5'].map(key => ({ key, model: study.summary.horizons[key].models.lightgbm.mae, baseline: study.summary.horizons[key].models.last_observed.mae })) : []
  const maximum = Math.max(0.01, ...points.flatMap(point => [point.model, point.baseline])) * 1.15
  const x = (index: number) => 60 + index * 160
  const y = (value: number) => 150 - (value / maximum) * 120
  return <section className="research-panel" aria-label="Multi-horizon pace study">
    <h2>How does forecast error change with horizon?</h2>
    <p>Direct lap-time forecasts on previously inspected races. The inherited source requires a recorded next lap; later horizons additionally require recorded future laps. These results are conditional on survival and data availability, not an unconditional live forecast. Horizons have different scored cohorts, so differences also reflect selection.</p>
    {missing && <p role="status">The saved multi-horizon study is unavailable or invalid.</p>}
    {!missing && !study && <p role="status">Loading saved study…</p>}
    {result && population && <>
      <svg viewBox="0 0 440 180" role="img" aria-label="Mean absolute error by forecast horizon; turquoise is LightGBM and amber is the recent recorded lap" style={{ width: '100%', maxWidth: 640 }}>
        <line x1="60" y1="150" x2="380" y2="150" stroke="currentColor" opacity="0.5" />
        {(['baseline', 'model'] as const).map((name) => <polyline key={name} points={points.map((point, index) => `${x(index)},${y(point[name])}`).join(' ')} fill="none" stroke={name === 'model' ? '#70dec3' : '#e4b361'} strokeWidth="3" />)}
        {points.map((point, index) => <g key={point.key}><text x={x(index)} y="171" textAnchor="middle" fill="currentColor" fontSize="11">{point.key} lap{point.key === '1' ? '' : 's'}</text><circle cx={x(index)} cy={y(point.model)} r="4" fill="#70dec3"><title>LightGBM {point.model.toFixed(3)} seconds</title></circle><circle cx={x(index)} cy={y(point.baseline)} r="4" fill="#e4b361"><title>Recent lap {point.baseline.toFixed(3)} seconds</title></circle></g>)}
        <text x="5" y="25" fill="currentColor" fontSize="11">MAE (s)</text><text x="25" y="150" fill="currentColor" fontSize="10">0</text><text x="20" y="35" fill="currentColor" fontSize="10">{maximum.toFixed(1)}</text>
      </svg><p>Turquoise: LightGBM · amber: recent recorded lap. Exact values follow for the selected horizon.</p>
      <label>Forecast horizon <select aria-label="Pace forecast horizon" value={horizon} onChange={event => setHorizon(event.target.value)}>{['1', '3', '5'].map(value => <option key={value} value={value}>{value} {value === '1' ? 'lap' : 'laps'} ahead</option>)}</select></label>
      <p>{result.rows.toLocaleString()} out-of-fold forecasts across {result.races} races. From {population.decision_rows.toLocaleString()} inherited rows with at least two observed prior laps, {population.missing_target.toLocaleString()} lack a recorded target and {population.target_present_missing_intermediate.toLocaleString()} have an intermediate source gap.</p>
      <div className="research-table-scroll" role="region" aria-label="Scrollable horizon model comparison" tabIndex={0}><table aria-label="Horizon model errors"><thead><tr><th>Model</th><th>MAE</th><th>Median AE</th><th>RMSE</th></tr></thead><tbody>{[['anchor', 'Rolling median anchor'], ['last_observed', 'Recent recorded lap'], ['lightgbm', 'LightGBM']].map(([key, label]) => <tr key={key}><th scope="row">{label}</th><td>{result.models[key].mae.toFixed(3)} s</td><td>{result.models[key].median_ae.toFixed(3)} s</td><td>{result.models[key].rmse.toFixed(3)} s</td></tr>)}</tbody></table></div>
      <p>LightGBM minus recent-recorded-lap MAE: {result.paired_lightgbm_vs_last_observed.mean_delta.toFixed(3)} s; race-clustered 95% interval [{result.paired_lightgbm_vs_last_observed.ci_low.toFixed(3)}, {result.paired_lightgbm_vs_last_observed.ci_high.toFixed(3)}] s. Negative favours LightGBM.</p>
      <p>Raw 10–90% interval coverage {(result.interval.coverage * 100).toFixed(1)}%, width {result.interval.mean_width_raw.toFixed(3)} s, crossings {result.interval.crossings.toLocaleString()}; no coverage guarantee.</p>
      <div className="research-table-scroll" role="region" aria-label="Scrollable horizon season comparison" tabIndex={0}><table aria-label="Horizon errors by season"><thead><tr><th>Season</th><th>Forecasts</th><th>Recent lap MAE</th><th>LightGBM MAE</th></tr></thead><tbody>{Object.entries(result.by_year).map(([year, row]) => <tr key={year}><th scope="row">{year}</th><td>{row.n.toLocaleString()}</td><td>{row.last_observed_mae.toFixed(3)} s</td><td>{row.lightgbm_mae.toFixed(3)} s</td></tr>)}</tbody></table></div>
      <details><summary>Source provenance</summary><p>Input SHA-256 <code>{study?.source_sha256}</code>. OpenF1-derived, non-commercial; original source completeness and publication latency remain uncertain.</p></details>
    </>}
  </section>
}
