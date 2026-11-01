import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

type Score = { mae_s: number; paired_mae_delta_s: number; conditional_cluster_bootstrap_95_s: number[] | null }
type Slice = { label: string; rows: number; clusters: number; models: Record<string, Score> }
type Report = { status: string; slices: Record<'retrospective_lap_change' | 'asof_prior_change', Slice[]>; limits: string[]; predictions_sha256: string }
const labels: Record<string, string> = { tcn_seed7: 'Standard TCN seed 7', tcn_no_context_seed42: 'TCN no head context, last-lap anchor', tcn_masked_seed42: 'Masked TCN seed 42' }

export function FutureFailureAnalysis() {
  const [data, setData] = useState<Report | null>(null)
  const [error, setError] = useState(false)
  const [cohort, setCohort] = useState<'retrospective_lap_change' | 'asof_prior_change'>('retrospective_lap_change')
  const [model, setModel] = useState('tcn_seed7')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/driver-dna/future-failures', { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error('Analysis unavailable')
      return response.json() as Promise<Report>
    }).then(setData).catch((cause) => { if (cause.name !== 'AbortError') setError(true) })
    return () => controller.abort()
  }, [])
  const rows = data?.slices[cohort] ?? []
  const chart = rows.map((row) => ({ label: row.label, persistence: row.models.last_completed_lap?.mae_s ?? null,
    selected: row.models[model]?.mae_s ?? null }))
  return <section className="future-failure-analysis" aria-label="Exploratory future forecast failure analysis">
    <h3>When do corrections help or hurt?</h3>
    <p>These 2026 events have already been inspected. Subgroup comparisons are exploratory, not fresh test evidence or causal diagnoses.</p>
    {error && <p role="status">Failure analysis is unavailable or failed its integrity check.</p>}
    {data && <>
      <div className="future-controls"><label>Slice definition<select aria-label="Forecast error slice" value={cohort} onChange={(e) => setCohort(e.target.value as typeof cohort)}>
        <option value="retrospective_lap_change">Observed lap change · retrospective only</option><option value="asof_prior_change">Prior lap versus prior median · as of cutoff</option></select></label>
        <label>Model<select aria-label="Forecast error model" value={model} onChange={(e) => setModel(e.target.value)}>{Object.entries(labels).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label></div>
      <p>{cohort === 'retrospective_lap_change' ? 'Observed lap change uses the later completed-lap outcome. It is not available to a forecast and was not an input.' : 'Prior-lap context was available by the retrospective cutoff; provider publication delays are not verified.'}</p>
      <div className="future-chart" role="img" aria-label="Mean absolute error by exploratory slice, in seconds"><ResponsiveContainer width="100%" height="100%"><BarChart data={chart} margin={{ left: 0, right: 20, top: 8, bottom: 0 }}><CartesianGrid stroke="#283238" /><XAxis dataKey="label" /><YAxis width={55} /><Tooltip /><Bar dataKey="persistence" name="Last-lap persistence" fill="#4dc9b0" isAnimationActive={false} /><Bar dataKey="selected" name={labels[model]} fill="#80aaff" isAnimationActive={false} /></BarChart></ResponsiveContainer></div>
      <p><span style={{ color: '#4dc9b0' }}>■</span> Last-lap persistence &nbsp; <span style={{ color: '#80aaff' }}>■</span> {labels[model]}</p>
      <p>Scroll the comparison table horizontally on narrow screens.</p>
      <div className="future-scroll" role="region" aria-label="Scrollable forecast error comparison" tabIndex={0}><table aria-label="Forecast error slice comparison"><thead><tr><th>Slice</th><th>Laps</th><th>Session-driver clusters</th><th>Persistence MAE</th><th>Model MAE</th><th>Paired difference</th><th>Conditional 95% interval</th></tr></thead><tbody>{rows.map((row) => {
        const base = row.models.last_completed_lap, selected = row.models[model]
        return <tr key={row.label}><th scope="row">{row.label}</th><td>{row.rows}</td><td>{row.clusters}</td><td>{base ? `${base.mae_s.toFixed(3)} s` : 'Unavailable'}</td><td>{selected ? `${selected.mae_s.toFixed(3)} s` : 'Unavailable'}</td><td>{selected ? `${selected.paired_mae_delta_s.toFixed(3)} s` : 'Unavailable'}</td><td>{selected?.conditional_cluster_bootstrap_95_s ? `[${selected.conditional_cluster_bootstrap_95_s.map((x) => x.toFixed(3)).join(', ')}] s` : 'Unavailable'}</td></tr>
      })}</tbody></table></div>
      <p>Intervals resample session-driver clusters within these two observed events; they do not quantify new-circuit uncertainty. Smaller MAE is better. The no-head-context model still uses last-lap persistence as its anchor.</p>
      <details><summary>Analysis limits and prediction provenance</summary><ul>{data.limits.map((limit) => <li key={limit}>{limit}</li>)}</ul><p>Saved prediction SHA-256 <code>{data.predictions_sha256}</code>.</p></details>
    </>}
  </section>
}
