import { useEffect, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import './FutureSegmentStudy.css'

type Metrics = { mae_s: number; median_ae_s: number; rmse_s: number }
type Candidate = { model: string; test: Metrics; by_session: Record<string, Metrics>; paired_vs_persistence_s: number; conditional_driver_bootstrap_95_s: number[] }
type Case = { case_id: number; circuit: string; driver: string; lap_number: number; session_key: number; remaining_seconds: number; [key: string]: string | number }
type Study = { artifact_mode: string; session_catalog: { session_key: number; circuit: string }[]; dataset: { rows: number; split_rows: Record<string, number>; quality: Record<string, { kept: number; source_laps: number }> }; results: Candidate[]; cases: Case[]; limitations: string[]; source_sha: string; prediction_sha256: string; training_curves: Record<string, { stage: string; epoch: number; validation_scaled_mae?: number }[]> }
type Prefix = { case_id: number; seconds: number[]; channels: Record<string, number[]>; evidence: string }
const label = (value: string) => value === 'tcn_no_context_seed42'
  ? 'TCN seed 42 · no head context · last-lap anchor retained'
  : value.replaceAll('_', ' ')

export default function FutureSegmentStudy() {
  const [data, setData] = useState<Study | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [session, setSession] = useState('all')
  const [model, setModel] = useState('tcn_seed42')
  const [selected, setSelected] = useState<number | null>(null)
  const [prefix, setPrefix] = useState<Prefix | null>(null)
  const [prefixError, setPrefixError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/driver-dna/future-study', { signal: controller.signal }).then(async (response) => {
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Study unavailable')
      return body as Study
    }).then(setData).catch((cause) => { if (cause.name !== 'AbortError') setError(cause.message) })
    return () => controller.abort()
  }, [])
  const cases = data?.cases.filter((row) => session === 'all' || String(row.session_key) === session) ?? []
  const incident = cases.find((row) => row.case_id === selected) ?? cases[0]
  const caseId = incident?.case_id
  useEffect(() => {
    if (caseId == null) return
    const controller = new AbortController()
    fetch(`/api/v1/driver-dna/future-study/${caseId}`, { signal: controller.signal }).then(async (response) => {
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Prefix unavailable')
      return body as Prefix
    }).then((body) => { setPrefix(body); setPrefixError(null) }).catch((cause) => { if (cause.name !== 'AbortError') setPrefixError(cause.message) })
    return () => controller.abort()
  }, [caseId])
  const observed = prefix?.case_id === caseId ? prefix : null
  const failures = [...cases].sort((a, b) => Math.abs(Number(b[model]) - b.remaining_seconds) - Math.abs(Number(a[model]) - a.remaining_seconds)).slice(0, 8)
  const curves = data?.training_curves[model]?.filter((row) => row.stage === 'supervised') ?? []
  return <section className="dna-future" aria-label="Inductive future performance study">
    <span className="eyebrow">NEW TASK · FIRST 20 SECONDS → REMAINING LAP</span>
    <h3>Does the observed prefix help predict what comes next?</h3>
    <p>Five measured channels, training-only normalization and completed prior laps. Held-out Australia and Japan 2026; retrospective observation-time availability. This predicts future pace, not innate driving style.</p>
    {error && <p role="status">{error}</p>}
    {!data && !error && <p role="status">Loading saved experiments…</p>}
    {data && <>
      <p>{data.dataset.rows.toLocaleString()} usable prefixes across six sessions: {data.dataset.split_rows.train} training, {data.dataset.split_rows.validation} validation, {data.dataset.split_rows.test} test. Future slow, pit and safety-car outcomes remain in this completed-lap cohort.</p>
      <p role="status">{data.results.every((row) => row.test.mae_s >= data.results[0].test.mae_s) ? 'Persistence remained strongest. No trained replacement is promoted.' : 'Inspect paired uncertainty before drawing an improvement conclusion.'}</p>
      {data.artifact_mode === 'aggregate_only' && <p role="status">Aggregate experiment results only. Individual telemetry prefixes and trained weights stay local; mount the reproduced artifacts for lap investigation.</p>}
      <div className="future-controls"><label>Held-out circuit<select aria-label="Future study circuit" value={session} onChange={(event) => setSession(event.target.value)}><option value="all">Both held-out circuits</option>{data.session_catalog.map(({ session_key: key, circuit: name }) => <option value={key} key={key}>{name}</option>)}</select></label>
        <label>Investigated model<select aria-label="Future study model" value={model} onChange={(event) => setModel(event.target.value)}>{data.results.map((row) => <option key={row.model} value={row.model}>{label(row.model)}</option>)}</select></label></div>
      <div className="future-scroll"><table aria-label="Future performance benchmarks"><thead><tr><th>Model</th><th>MAE (s)</th><th>Median AE (s)</th><th>RMSE (s)</th></tr></thead><tbody>{data.results.map((row) => {
        const score = session === 'all' ? row.test : row.by_session[session]
        return <tr key={row.model} data-selected={row.model === model}><th scope="row">{label(row.model)}</th><td>{score.mae_s.toFixed(3)}</td><td>{score.median_ae_s.toFixed(3)}</td><td>{score.rmse_s.toFixed(3)}</td></tr>
      })}</tbody></table></div>
      <p>Full-test conditional driver-bootstrap intervals compare error with persistence; they do not estimate performance on a population of new circuits.</p>
      <p>The no-head-context TCN still adds its learned residual to the last completed lap; only additional context inputs to the neural head are removed.</p>
      {data.results.filter((row) => row.model === model).map((row) => <p key={row.model} aria-label="Future paired comparison">{label(row.model)} minus last-lap MAE: {row.paired_vs_persistence_s.toFixed(3)} s, 95% conditional interval [{row.conditional_driver_bootstrap_95_s.map((v) => v.toFixed(3)).join(', ')}] s. Lower is better. No automatic promotion.</p>)}
      <label>Held-out lap<select aria-label="Future study lap" value={caseId ?? ''} onChange={(event) => setSelected(Number(event.target.value))}>{cases.map((row) => <option key={row.case_id} value={row.case_id}>{row.circuit} · {row.driver} · lap {row.lap_number}</option>)}</select></label>
      <div className="future-failures" aria-label="Future study failure cases">{failures.map((row) => <button key={row.case_id} onClick={() => setSelected(row.case_id)} aria-pressed={caseId === row.case_id}>{row.circuit} · {row.driver} · L{row.lap_number}<strong>{Math.abs(Number(row[model]) - row.remaining_seconds).toFixed(2)} s error</strong></button>)}</div>
      {incident && <p role="status" aria-label="Future selected prediction">{incident.circuit} · {incident.driver} · lap {incident.lap_number}: predicted remaining {Number(incident[model]).toFixed(2)} s; observed remaining {incident.remaining_seconds.toFixed(2)} s. Input cutoff: 20 s. No future telemetry enters these traces.</p>}
      {prefixError && <p role="status">{prefixError}</p>}
      {observed && <div aria-label="Synchronized observed prefixes">{Object.entries(observed.channels).map(([name, values]) => <div key={name}><h4>{label(name)} {({ speed: '(km/h)', throttle: '(%)', brake: '(%)', gear: '(gear)', rpm: '(rpm)' } as Record<string, string>)[name]}</h4><div className="future-chart"><ResponsiveContainer width="100%" height="100%"><LineChart syncId="future-prefix" data={observed.seconds.map((seconds, i) => ({ seconds, value: values[i] }))}><CartesianGrid stroke="#283238" /><XAxis dataKey="seconds" unit=" s" type="number" domain={[0, 20]} /><YAxis width={55} /><Tooltip /><Line dataKey="value" name={label(name)} type={name === 'brake' || name === 'gear' ? 'stepAfter' : 'linear'} dot={false} stroke="#4dc9b0" isAnimationActive={false} /></LineChart></ResponsiveContainer></div></div>)}</div>}
      {curves.length > 0 && <div><h4>Validation curve · training-scaled residual MAE</h4><div className="future-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={curves}><XAxis dataKey="epoch" /><YAxis width={55} /><Tooltip /><Line dataKey="validation_scaled_mae" stroke="#80aaff" dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div></div>}
      <details><summary>Coverage, limitations and provenance</summary><pre>{JSON.stringify(data.dataset.quality, null, 2)}</pre><ul>{data.limitations.map((text) => <li key={text}>{text}</li>)}</ul><p>Source revision <code>{data.source_sha}</code>; prediction SHA-256 <code>{data.prediction_sha256}</code>.</p></details>
    </>}
  </section>
}
