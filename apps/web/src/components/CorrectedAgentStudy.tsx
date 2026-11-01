import { useEffect, useState } from 'react'

type Arm = 'baseline' | 'candidate'
type Step = { tool_id: string; action: string; args: object; observation: string }
type Case = { scenario_id: string; arm: Arm; expected: string; predicted: string; correct: boolean; seconds: number; explanation: string; evidence_ids: string[]; trace: Step[]; support: { verdict: string; reason: string } | null }
type Scores = { accuracy: number; cases: number; false_no_discrepancy: number; false_citation_ids: number; tool_calls: number; mean_seconds: number; p95_seconds: number }
type Study = { cases: Case[]; summary: { arms: Record<Arm, Scores>; paired_accuracy_delta: number; family_bootstrap_95: number[] }; support_method: string; protocol: { sources: Record<Arm, { commit: string }>; model_digest: string }; raw_results_sha256: string }

export function CorrectedAgentStudy() {
  const [data, setData] = useState<Study | null>(null)
  const [error, setError] = useState(false)
  const [selected, setSelected] = useState('feature_skew-s1')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/research/agent-corrected', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('Study unavailable')
      return response.json() as Promise<Study>
    }).then(setData).catch(cause => { if (cause.name !== 'AbortError') setError(true) })
    return () => controller.abort()
  }, [])
  return <section className="research-panel" aria-label="Corrected preflight agent evaluation">
    <h2>Corrected preflight: a second paired evaluation</h2>
    <p>Actual local Qwen3 8B output on 16 previously inspected synthetic scenarios per agent. The corrected candidate was evaluated separately from the earlier PR #1 revision. These cases do not establish performance on unseen or real incidents.</p>
    {error && <p role="status">Corrected evaluation evidence is unavailable or invalid.</p>}
    {!error && !data && <p role="status">Loading saved evaluation…</p>}
    {data && <>
      <div className="research-table-scroll" role="region" aria-label="Scrollable corrected agent scores" tabIndex={0}><table aria-label="Corrected agent scores"><thead><tr><th>Agent</th><th>Correct</th><th>False clean</th><th>Invalid citation IDs</th><th>Tool calls</th><th>Mean / p95</th></tr></thead><tbody>{(['baseline', 'candidate'] as Arm[]).map(arm => { const score = data.summary.arms[arm]; return <tr key={arm}><th scope="row">{arm === 'baseline' ? 'Foundation' : 'Corrected PR #1'}</th><td>{Math.round(score.accuracy * score.cases)} / {score.cases}</td><td>{score.false_no_discrepancy}</td><td>{score.false_citation_ids}</td><td>{score.tool_calls}</td><td>{score.mean_seconds.toFixed(1)} / {score.p95_seconds.toFixed(1)} s</td></tr> })}</tbody></table></div>
      <p>Accuracy difference {(data.summary.paired_accuracy_delta * 100).toFixed(1)} points; 95% known-family bootstrap [{data.summary.family_bootstrap_95.map(value => (value * 100).toFixed(1)).join(', ')}] points. Timings were measured on a shared machine across a resumed run and are not a controlled speed comparison.</p>
      <label>Incident <select aria-label="Corrected agent incident" value={selected} onChange={event => setSelected(event.target.value)}>{data.cases.filter(row => row.arm === 'candidate').map(row => <option key={row.scenario_id} value={row.scenario_id}>{row.scenario_id}</option>)}</select></label>
      <div className="research-columns" aria-label="Corrected agent traces">{(['baseline', 'candidate'] as Arm[]).map(arm => { const row = data.cases.find(item => item.arm === arm && item.scenario_id === selected); return row && <article key={arm} aria-label={`${arm} corrected evaluation trace`}><h3>{arm === 'baseline' ? 'Foundation' : 'Corrected PR #1'}</h3><p>Planted: {row.expected}; predicted: {row.predicted}. {row.correct ? 'Correct label' : 'Incorrect label'}.</p><p>{row.explanation}</p><p>Claim review: {row.support ? `${row.support.verdict} — ${row.support.reason}` : 'not reviewed'}</p>{row.trace.map(step => <details key={step.tool_id}><summary>{step.tool_id}: {step.action}{row.evidence_ids.includes(step.tool_id) ? ' · cited' : ''}</summary><pre>{JSON.stringify(step.args, null, 2)}</pre><pre>{step.observation}</pre></details>)}</article> })}</div>
      <p>{data.support_method} A valid citation ID alone does not establish support.</p>
      <details><summary>Source provenance</summary><p>Foundation <code>{data.protocol.sources.baseline.commit}</code><br />Candidate <code>{data.protocol.sources.candidate.commit}</code><br />Model digest <code>{data.protocol.model_digest}</code><br />Raw results SHA-256 <code>{data.raw_results_sha256}</code></p></details>
    </>}
  </section>
}
