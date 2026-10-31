import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

type Case = { scenario_id: string; expected: string; predicted: string; correct: boolean; seconds: number; explanation: string; evidence_ids: string[]; trace: { tool_id?: string; action?: string; args?: object; observation?: string; final?: { root_cause: string } }[] }
type Evaluation = { evidence: string; solver: string; summary: { cases: number; accuracy: number; mean_seconds: number; tool_calls: number; false_citation_ids: number; undetermined_or_invalid: number }; cases: Case[]; source_sha256: Record<string, string>; support_status: string }

export function AgentInvestigation() {
  const [data, setData] = useState<Evaluation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/research/agent-evaluation', { signal: controller.signal }).then(async (response) => {
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Saved evaluation unavailable')
      return body as Evaluation
    }).then(setData).catch((cause) => { if (cause.name !== 'AbortError') setError(String(cause.message)) })
    return () => controller.abort()
  }, [])
  const incident = data?.cases.find((item) => item.scenario_id === selected) ?? data?.cases[0]
  return <section className="research-panel" aria-label="Agent investigation replay">
    <h2>Forecast Debug Agent</h2><p>Replay what the local model examined before it made a diagnosis. This view runs no queries or model calls.</p>
    {error && <p role="status">{error}</p>}
    {data && <>
      <Badge variant="outline">{data.evidence}</Badge>
      <p>{data.solver}: {(data.summary.accuracy * 100).toFixed(0)}% root-cause accuracy across {data.summary.cases} cases. Mean latency {data.summary.mean_seconds.toFixed(2)} s; {data.summary.tool_calls} tool calls; {data.summary.false_citation_ids} nonexistent citation IDs.</p>
      <p>{data.support_status} The scripted reference is a separate solvability check.</p>
      <label htmlFor="agent-incident">Saved incident</label>
      <Select value={incident?.scenario_id ?? ''} onValueChange={setSelected}>
        <SelectTrigger id="agent-incident" aria-label="Saved incident"><SelectValue /></SelectTrigger>
        <SelectContent><SelectGroup>{data.cases.map((item) => <SelectItem key={item.scenario_id} value={item.scenario_id}>{item.scenario_id}</SelectItem>)}</SelectGroup></SelectContent>
      </Select>
      {incident && <div aria-label="Incident evidence">
        <h3>{incident.correct ? 'Correct diagnosis' : 'Incorrect diagnosis'}: {incident.predicted.replaceAll('_', ' ')}</h3>
        <p>Planted cause: {incident.expected.replaceAll('_', ' ')}. Inference {incident.seconds.toFixed(2)} s. Cited observations: {incident.evidence_ids.join(', ')}.</p>
        <p>{incident.explanation}</p>
        {incident.trace.filter((step) => step.tool_id).map((step) => <details key={step.tool_id}>
          <summary>{step.tool_id}: {step.action}</summary>
          <pre>{JSON.stringify(step.args, null, 2)}</pre>
          <pre>{step.observation}</pre>
        </details>)}
      </div>}
      <details><summary>Evaluation source hashes</summary><dl className="research-lineage">{Object.entries(data.source_sha256).map(([file, hash]) => <div key={file}><dt>{file}</dt><dd><code>{hash}</code></dd></div>)}</dl></details>
    </>}
  </section>
}
