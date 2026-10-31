import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

type Arm = 'baseline' | 'candidate'
type Incident = { scenario_id: string; arm: Arm; expected: string; predicted: string; correct: boolean; seconds: number; status: string; explanation: string; evidence_ids: string[]; support: { verdict: string; reason: string }; input_fingerprints: Record<string, string>; trace: { tool_id: string; action: string; args: object; observation: string }[] }
type Scores = { accuracy: number; cases: number; false_no_discrepancy: number; mean_seconds: number; tool_calls: number; false_citation_ids: number; failed_workers: number; invalid_or_undetermined: number }
type Study = { evidence: string; summary: { arms: Record<Arm, Scores>; paired_accuracy_delta: number; family_bootstrap_95: number[] }; cases: Incident[]; support_method: string; source_sha256: Record<string, string>; protocol: { model_digest: string; sources: Record<Arm, { commit: string }>; settings: { model: string } } }
const name = (text: string) => text.replaceAll('_', ' ')
const percent = (value: number) => `${(100 * value).toFixed(1)}%`

export function PairedAgentStudy() {
  const [data, setData] = useState<Study | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [filter, setFilter] = useState('all')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/research/agent-paired', { signal: controller.signal }).then(async (response) => {
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Paired evaluation unavailable')
      return body as Study
    }).then(setData).catch((cause) => { if (cause.name !== 'AbortError') setError(String(cause.message)) })
    return () => controller.abort()
  }, [])
  const ids = [...new Set(data?.cases.map((row) => row.scenario_id))].filter((id) => filter === 'all' || data?.cases.some((row) => row.scenario_id === id && !row.correct))
  const active = ids.includes(selected ?? '') ? selected : ids[0]
  return <section className="research-panel" aria-label="Paired agent study">
    <h2>Same incident. Two investigations.</h2>
    <p>Frozen foundation agent versus draft PR #1. Actual local Qwen3 output on 16 paired synthetic cases; both use the same data and generation limits. The review PR remains unmerged.</p>
    {!data && !error && <p role="status">Loading the paired evidence…</p>}
    {error && <p role="status">{error}</p>}
    {data && <>
      <Badge variant="outline">{data.evidence}</Badge>
      <div className="research-table-scroll"><table aria-label="Paired model scores"><thead><tr><th>Implementation</th><th>Correct / cases</th><th>False clean</th><th>Unresolved</th><th>Supported explanations</th><th>Mean time</th><th>Tool calls</th><th>Failed workers</th></tr></thead><tbody>{(['baseline', 'candidate'] as Arm[]).map((arm) => {
        const score = data.summary.arms[arm]
        return <tr key={arm}><th scope="row">{arm === 'baseline' ? 'Foundation' : 'PR #1'}</th><td>{Math.round(score.accuracy * score.cases)} / {score.cases} ({percent(score.accuracy)})</td><td>{score.false_no_discrepancy}</td><td>{score.invalid_or_undetermined}</td><td>{data.cases.filter((row) => row.arm === arm && row.support.verdict === 'supported').length} / {score.cases}</td><td>{score.mean_seconds.toFixed(2)} s</td><td>{score.tool_calls}</td><td>{score.failed_workers}</td></tr>
      })}</tbody></table></div>
      <p aria-label="Paired uncertainty">Accuracy change {(100 * data.summary.paired_accuracy_delta).toFixed(1)} percentage points; 95% fault-family bootstrap [{data.summary.family_bootstrap_95.map((value) => (100 * value).toFixed(1)).join(', ')}] points. Eight known families, two seeds each. This is not evidence of performance on unseen faults or real incidents.</p>
      <label htmlFor="paired-filter">Incident cohort</label>
      <Select value={filter} onValueChange={(value) => setFilter(value ?? 'all')}><SelectTrigger id="paired-filter" aria-label="Paired incident cohort"><SelectValue>{filter === 'all' ? 'All paired incidents' : 'Either agent failed'}</SelectValue></SelectTrigger><SelectContent><SelectGroup><SelectItem value="all">All paired incidents</SelectItem><SelectItem value="failures">Either agent failed</SelectItem></SelectGroup></SelectContent></Select>
      <div className="paired-case-grid" aria-label="Paired incident selection">{ids.map((id) => <Button key={id} variant={id === active ? 'secondary' : 'ghost'} aria-pressed={id === active} onClick={() => setSelected(id)}>
        <span>{name(id)}</span><span>{(['baseline', 'candidate'] as Arm[]).map((arm) => <span key={arm} className="paired-outcome" data-correct={data.cases.find((row) => row.scenario_id === id && row.arm === arm)?.correct}>{arm === 'baseline' ? 'F' : 'PR'}: {data.cases.find((row) => row.scenario_id === id && row.arm === arm)?.correct ? '✓' : '×'}</span>)}</span>
      </Button>)}</div>
      <div className="research-columns" aria-label="Paired incident evidence">{(['baseline', 'candidate'] as Arm[]).map((arm) => {
        const row = data.cases.find((item) => item.scenario_id === active && item.arm === arm)
        return row && <article key={arm} aria-label={`${arm} investigation`}>
          <h3>{arm === 'baseline' ? 'Foundation' : 'PR #1'} · {row.scenario_id}</h3>
          <Badge variant="outline">{row.correct ? 'Correct label' : 'Incorrect label'}</Badge><p>Planted: {name(row.expected)}. Diagnosis: {name(row.predicted)}. {row.seconds.toFixed(2)} s.</p>
          <p>{row.explanation}</p><h3>Cited evidence: {row.support.verdict}</h3><p>{row.support.reason}</p>
          {row.trace.map((step) => <details key={step.tool_id}><summary>{step.tool_id}: {step.action}{row.evidence_ids.includes(step.tool_id) ? ' · cited' : ''}</summary><pre>{JSON.stringify(step.args, null, 2)}</pre><pre>{step.observation}</pre></details>)}
          <details><summary>Scenario data fingerprints</summary><dl className="research-lineage">{Object.entries(row.input_fingerprints).map(([key, hash]) => <div key={key}><dt>{key}</dt><dd><code>{hash}</code></dd></div>)}</dl></details>
        </article>
      })}</div>
      <p>{data.support_method} Citation IDs existing does not establish logical support. The earlier 2/8 LLM result and scripted 200/200 reference remain separate studies.</p>
      <details><summary>Paired protocol and provenance</summary><dl className="research-lineage"><div><dt>Model</dt><dd>{data.protocol.settings.model}<br /><code>{data.protocol.model_digest}</code></dd></div>{Object.entries(data.protocol.sources).map(([arm, source]) => <div key={arm}><dt>{arm} source</dt><dd><code>{source.commit}</code></dd></div>)}{Object.entries(data.source_sha256).map(([file, hash]) => <div key={file}><dt>{file}</dt><dd><code>{hash}</code></dd></div>)}</dl></details>
    </>}
  </section>
}
