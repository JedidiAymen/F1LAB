import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ExternalLink } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AgentInvestigation } from '@/components/AgentInvestigation'

type Comparison = { model: string; rows: number; mae_s: number; bias_s: number; unmatched_rows: number; vs_persistence: { mean_delta: number; ci_low: number; ci_high: number; clusters: number } }
type Race = { race_id: string; event: string; year: number; rows: number; mae_s: number; bias_s: number }
type Report = {
  evidence: string; created_at_utc: string; evaluation: string; comparison: Comparison[]
  seasons: { year: number; rows: number; mae_s: number; bias_s: number }[]; races: Race[]; failures: Race[]
  drift: { reference: string; current: string; reference_rows: number; current_rows: number; features: { feature: string; psi: number | null; reference_missing: number; current_missing: number }[] }
  sources: Record<string, string>; limitations: string[]
  served_card: { model_id: string; version: string; dataset_fingerprint: string; intended_use: string; data_license: string; features: { name: string; unit: string; available_at: string }[] } | null
  run_provenance: { run_kind: string; source: { sha: string; dirty: boolean | null }; tracking: { status: string; run_id?: string } } | null
}
const number = (value: number) => value.toFixed(3)
const signed = (value: number) => `${value > 0 ? '+' : ''}${number(value)}`
const modelName = (value: string) => value.replaceAll('_', ' ')

export function ResearchObservatory({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [season, setSeason] = useState('all')
  const [selectedRace, setSelectedRace] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/research/reliability', { signal: controller.signal }).then(async (response) => {
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Research artifacts unavailable')
      return body as Report
    }).then(setData).catch((cause) => { if (cause.name !== 'AbortError') setError(String(cause.message)) })
    return () => controller.abort()
  }, [])
  const races = useMemo(() => data?.races.filter((race) => season === 'all' || String(race.year) === season)
    .sort((a, b) => b.mae_s - a.mae_s) ?? [], [data, season])
  const race = races.find((item) => item.race_id === selectedRace) ?? races[0]
  const candidate = data?.comparison.find((item) => item.model === 'lightgbm')
  return (
    <main className="research-observatory dark">
      <header className="research-heading">
        <div>
          <Button variant="ghost" size="sm" onClick={onBack}><ArrowLeft data-icon="inline-start" />Race Control</Button>
          <h1>Research & reliability</h1>
          <p>Trace the model. Inspect the evidence. Keep the failures visible.</p>
        </div>
        <Badge variant="outline">Saved experiments</Badge>
      </header>
      {!data && !error && <p role="status">Loading the saved experiment and source fingerprints…</p>}
      {error && <p role="alert">{error}</p>}
      {data && <>
        <div className="research-status"><Badge variant="secondary">{data.evidence} data</Badge><span>{data.evaluation}</span></div>
        <section className="research-verdict" aria-label="Evidence verdict">
          <h2>Does the model beat persistence?</h2>
          {candidate && <><strong>{signed(candidate.vs_persistence.mean_delta)} s</strong>
            <p>MAE difference, 95% race-clustered interval [{signed(candidate.vs_persistence.ci_low)}, {signed(candidate.vs_persistence.ci_high)}] s.</p>
            <Badge variant="outline">{candidate.vs_persistence.ci_low <= 0 && candidate.vs_persistence.ci_high >= 0 ? 'No reliable gain established' : 'Inspect the paired interval'}</Badge>
          </>}
          <p>Lower is better. These events have already been inspected; they are not an untouched test set.</p>
        </section>
        <div className="research-columns">
          <section className="research-panel" aria-label="Benchmark candidates">
            <h2>Benchmark ledger</h2><p>Same green-clean outcome cohort. Errors in seconds.</p>
            <div className="research-table-scroll"><table>
              <thead><tr><th>Candidate</th><th>MAE</th><th>Bias</th><th>Scored laps</th></tr></thead>
              <tbody>{[...data.comparison].sort((a, b) => a.mae_s - b.mae_s).map((row) => <tr key={row.model}>
                <th scope="row">{modelName(row.model)}</th><td>{number(row.mae_s)}</td><td>{signed(row.bias_s)}</td><td>{row.rows.toLocaleString()}</td>
              </tr>)}</tbody>
            </table></div>
            <p>One served binary version. These candidates are saved benchmark forecasts, not separately deployed models.</p>
            <h3>Season bias</h3>
            <div className="research-chart" role="img" aria-label="LightGBM bias by season in seconds">
              <ResponsiveContainer width="100%" height="100%"><BarChart data={data.seasons} margin={{ left: 0, right: 20, top: 12, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--border)" /><XAxis dataKey="year" stroke="var(--muted-foreground)" />
                <YAxis unit=" s" stroke="var(--muted-foreground)" width={62} /><Tooltip contentStyle={{ background: 'var(--popover)', borderColor: 'var(--border)', color: 'var(--foreground)' }} />
                <ReferenceLine y={0} stroke="var(--foreground)" /><Bar dataKey="bias_s" name="Prediction minus truth (s)" fill="var(--chart-2)" isAnimationActive={false} />
              </BarChart></ResponsiveContainer>
            </div>
          </section>
          <section className="research-panel" aria-label="Input distribution drift">
            <h2>What changed in the inputs?</h2><p>{data.drift.reference} → {data.drift.current}. PSI is descriptive, not a diagnosis.</p>
            <div className="research-table-scroll"><table>
              <thead><tr><th>Feature</th><th>PSI</th><th>Missing before</th><th>Missing now</th></tr></thead>
              <tbody>{[...data.drift.features].sort((a, b) => (b.psi ?? -1) - (a.psi ?? -1)).map((feature) => <tr key={feature.feature}>
                <th scope="row">{modelName(feature.feature)}</th><td>{feature.psi == null ? 'Unknown' : number(feature.psi)}</td>
                <td>{(feature.reference_missing * 100).toFixed(1)}%</td><td>{(feature.current_missing * 100).toFixed(1)}%</td>
              </tr>)}</tbody>
            </table></div>
            <p>{data.drift.reference_rows.toLocaleString()} reference rows; {data.drift.current_rows.toLocaleString()} current rows. Weather, calendar and circuit mix can all change these distributions.</p>
            <h3>Failure review</h3>
            <label htmlFor="research-season">Season</label>
            <Select value={season} onValueChange={(value) => setSeason(value ?? 'all')}>
              <SelectTrigger id="research-season" aria-label="Research season"><SelectValue /></SelectTrigger>
              <SelectContent><SelectGroup><SelectItem value="all">All seasons</SelectItem>{data.seasons.map((item) => <SelectItem key={item.year} value={String(item.year)}>{item.year}</SelectItem>)}</SelectGroup></SelectContent>
            </Select>
            <div className="research-failures" aria-label="Race failure cases">{races.slice(0, 5).map((item) => <Button key={item.race_id} variant={race?.race_id === item.race_id ? 'secondary' : 'ghost'} onClick={() => setSelectedRace(item.race_id)}>
              {item.year} {item.event}<span>{number(item.mae_s)} s</span>
            </Button>)}</div>
            {race && <p role="status" aria-label="Selected failure">{race.year} {race.event}: {race.rows.toLocaleString()} scored laps; MAE {number(race.mae_s)} s; bias {signed(race.bias_s)} s. Outcome-filtered cohort.</p>}
          </section>
        </div>
        <section className="research-panel" aria-label="Model lineage">
          <h2>Model & source lineage</h2>
          {data.served_card && <><dl className="research-lineage">
            <div><dt>Served artifact</dt><dd>{data.served_card.model_id} / v{data.served_card.version}</dd></div>
            <div><dt>Tracking</dt><dd>{data.run_provenance?.tracking.status ?? 'Not imported'} / {data.run_provenance?.run_kind ?? 'Original training source unrecorded'}</dd></div>
            <div><dt>Dataset fingerprint</dt><dd><code>{data.served_card.dataset_fingerprint}</code></dd></div>
            {data.run_provenance && <div><dt>Registration source</dt><dd><code>{data.run_provenance.source.sha}</code>{data.run_provenance.source.dirty && ' (working tree modified)'}</dd></div>}
          </dl><p>{data.served_card.data_license}. {data.served_card.intended_use}.</p></>}
          <details><summary>Source hashes and feature availability</summary>
            <dl className="research-lineage">{Object.entries(data.sources).map(([name, hash]) => <div key={name}><dt>{name}</dt><dd><code>{hash}</code></dd></div>)}</dl>
            {data.served_card && <div className="research-table-scroll"><table><thead><tr><th>Feature</th><th>Unit</th><th>Known when</th></tr></thead><tbody>{data.served_card.features.map((feature) => <tr key={feature.name}><th scope="row">{feature.name}</th><td>{feature.unit}</td><td>{feature.available_at}</td></tr>)}</tbody></table></div>}
          </details>
          <details><summary>Limits of this evidence</summary><ul>{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
          <a href="http://127.0.0.1:5000" target="_blank" rel="noreferrer">Open local MLflow <ExternalLink size={12} /></a><p>Optional service on this computer. Registration-source SHA for an imported artifact is not its original training SHA.</p>
        </section>
      </>}
      <AgentInvestigation />
    </main>
  )
}
