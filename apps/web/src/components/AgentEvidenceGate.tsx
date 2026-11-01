import { useEffect, useState } from 'react'

type Signal = { code: string; description: string; citation: string }
type Case = { scenario_id: string; expected: string; proposed: string; original_correct: boolean; decision: string; status: string; signals: Signal[] }
type Study = { cases: Case[]; summary: { cases: number; original_correct: number; clean_proposals: number; false_clean_proposals: number; true_clean_proposals: number; false_clean_withheld: number; true_clean_withheld: number; clean_statuses: Record<string, number> }; limitations: string; results_sha256: string; gate_revision: string }

export function AgentEvidenceGate() {
  const [study, setStudy] = useState<Study | null>(null)
  const [error, setError] = useState(false)
  const [selected, setSelected] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/research/agent-evidence-gate', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('Unavailable')
      return response.json() as Promise<Study>
    }).then(data => { setStudy(data); setSelected(data.cases[0]?.scenario_id ?? '') })
      .catch(cause => { if (cause.name !== 'AbortError') setError(true) })
    return () => controller.abort()
  }, [])
  const row = study?.cases.find(item => item.scenario_id === selected)
  return <section className="research-panel" aria-label="Observational agent evidence gate">
    <h2>Withhold an unsupported clean decision</h2>
    <p>The opt-in observational gate checks cited tool results and requires review. It never approves a root cause; callers must enforce its decision because default inference is unchanged. This replay uses 16 previously inspected synthetic cases from the corrected-candidate Qwen3 run; it is not a new LLM evaluation. The hardened gate and wording were checked again after the initial results were seen. A signal does not establish materiality.</p>
    {error && <p role="status">Saved gate evidence is unavailable or invalid.</p>}
    {!study && !error && <p role="status">Loading the evidence-gate study…</p>}
    {study && <>
      <p>Original agent: {study.summary.original_correct}/{study.summary.cases} correct labels. It proposed “no material discrepancy” {study.summary.clean_proposals} times: {study.summary.false_clean_proposals} were faults, {study.summary.true_clean_proposals} were clean cases.</p>
      <p>The gate withheld all {study.summary.false_clean_withheld} false-clean and all {study.summary.true_clean_withheld} genuinely clean proposals. This follows from a policy of withholding <em>every</em> clean proposal; it is not a demonstrated gain in root-cause accuracy.</p>
      <p>Of those clean proposals, {study.summary.clean_statuses.signal_present ?? 0} had a selected observation signal; {study.summary.clean_statuses.insufficient ?? 0} had insufficient evidence under these checks.</p>
      <label>Scenario <select aria-label="Evidence gate scenario" value={selected} onChange={event => setSelected(event.target.value)}>{study.cases.map(item => <option key={item.scenario_id} value={item.scenario_id}>{item.scenario_id}</option>)}</select></label>
      {row && <article role="status" aria-label="Evidence gate decision"><h3>{row.scenario_id}</h3><p>Planted: {row.expected} · proposed: {row.proposed} · gate: {row.decision} ({row.status}).</p>{row.signals.length ? <ul>{row.signals.map((signal, index) => <li key={`${signal.citation}-${signal.code}-${index}`}>{signal.description} <code>{signal.citation}</code></li>)}</ul> : <p>No selected positive observation could be established from cited evidence.</p>}</article>}
      <p>{study.limitations} Read the <a href="https://github.com/JedidiAymen/F1LAB/pull/10">corrected candidate trace study</a> for the original observations; the two review branches have explicit dependencies.</p>
      <details><summary>Provenance</summary><p>Gate source <code>{study.gate_revision}</code><br />Prior trace projection SHA-256 <code>{study.results_sha256}</code></p></details>
    </>}
  </section>
}
