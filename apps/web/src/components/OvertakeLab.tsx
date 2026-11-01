import { useEffect, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import './OvertakeLab.css'
import { OvertakeHistory } from './OvertakeHistory'

type Row = { model: string; n: number; brier: number; log_loss: number; auc: number; average_precision: number; ece: number }
type Paired = { model: string; baseline: string; mean_delta: number; ci_low: number; ci_high: number; clusters: number }
type Bin = { n: number; mean_predicted: number; observed: number }
type Year = { year: number; n: number; rate: number; mean_p: number; brier: number; auc: number }
type Summary = {
  races_scored: number; table: Row[]; paired_brier_vs_logistic_gap: Paired[]
  reliability_lightgbm_calibrated: Bin[]; by_year: Year[]
}
type Audit = { saved_pair_rows: number; strict_pair_rows: number; late_leader_rows: number; late_leader_rows_in_scored_races: number; shared_rows_with_changed_prior_rate: number; shared_rows_with_changed_prior_rate_in_scored_races: number; nonconsecutive_next_rows: number; late_examples: { race_id: string; year: number; event: string; lap: number; follower: number; leader: number; leader_minus_follower_seconds: number; race_scored: boolean }[] }

const fixed = (v: number, d = 3) => v.toFixed(d)
const label = (name: string) => name.replaceAll('_', ' ')

function Reliability({ bins }: { bins: Bin[] }) {
  const size = 200
  const pad = 28
  const max = Math.max(0.01, ...bins.flatMap((b) => [b.mean_predicted, b.observed])) * 1.1
  const x = (v: number) => pad + (v / max) * (size - pad - 8)
  const y = (v: number) => size - pad - (v / max) * (size - pad - 8)
  return (
    <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Reliability: forecast timing-order swap probability versus observed frequency" className="ot-rel">
      <line className="axis" x1={pad} y1={y(0)} x2={x(max)} y2={y(0)} />
      <line className="axis" x1={pad} y1={y(0)} x2={pad} y2={y(max)} />
      <line className="ideal" x1={x(0)} y1={y(0)} x2={x(max)} y2={y(max)} />
      {bins.map((b, index) => (
        <circle key={index} cx={x(b.mean_predicted)} cy={y(b.observed)} r={3.5}>
          <title>{`${b.n} pairs · forecast ${(b.mean_predicted * 100).toFixed(1)}% · observed ${(b.observed * 100).toFixed(1)}%`}</title>
        </circle>
      ))}
      <text x={size / 2} y={size - 4} textAnchor="middle">forecast</text>
      <text x={8} y={size / 2} transform={`rotate(-90 8 ${size / 2})`} textAnchor="middle">observed</text>
    </svg>
  )
}

export function OvertakeLab({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [audit, setAudit] = useState<Audit | null>(null)
  const [auditError, setAuditError] = useState(false)
  const [selected, setSelected] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/overtake/summary', { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json()
        if (!response.ok) throw new Error(body.detail ?? 'unavailable')
        return body as Summary
      })
      .then(setData)
      .catch((cause) => { if (cause.name !== 'AbortError') setError(String(cause.message ?? cause)) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/overtake/cutoff-audit', { signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error('Audit unavailable'); return response.json() as Promise<Audit> })
      .then(setAudit).catch((cause) => { if (cause.name !== 'AbortError') setAuditError(true) })
    return () => controller.abort()
  }, [])

  return (
    <main className="ot">
      <button className="prediction-back" type="button" onClick={onBack}><ArrowLeft size={15} /> Race Control</button>
      <span className="eyebrow">OVERTAKE INTELLIGENCE · RETROSPECTIVE · PROVISIONAL</span>
      <h2>How often did timing order change?</h2>
      <p className="ot-note">These labels infer order swaps from timing snapshots; they are not verified on-track passes. The cohort excludes later pit and neutralization outcomes and is not an unconditional live forecast population.</p>
      {auditError && <p role="status" className="ot-note">Cutoff audit is unavailable or failed its integrity check.</p>}
      {audit && <section aria-label="Overtake cutoff audit" className="ot-audit">
        <h3>Decision-time audit</h3>
        <p>Of {audit.saved_pair_rows.toLocaleString()} saved pairs, {audit.late_leader_rows} use a leader cutoff after the follower's cutoff; {audit.late_leader_rows_in_scored_races} are in scored races. A strict rebuild removes those pairs and changes the historical circuit-rate feature for {audit.shared_rows_with_changed_prior_rate.toLocaleString()} retained pairs ({audit.shared_rows_with_changed_prior_rate_in_scored_races.toLocaleString()} in scored races). Corrected retrospective scores are available in the historical explorer when local research artifacts are present; the earlier scores remain below.</p>
        <label>Affected pair <select aria-label="Affected overtake pair" value={selected} onChange={(event) => setSelected(Number(event.target.value))}>{audit.late_examples.map((row, index) => <option key={`${row.race_id}-${row.lap}-${row.follower}`} value={index}>{row.year} {row.event} · lap {row.lap}</option>)}</select></label>
        {audit.late_examples[selected] && <p role="status" aria-label="Selected cutoff finding">Follower #{audit.late_examples[selected].follower} / proposed leader #{audit.late_examples[selected].leader}: leader cutoff {audit.late_examples[selected].leader_minus_follower_seconds.toFixed(3)} s later; {audit.late_examples[selected].race_scored ? 'race included in saved scoring' : 'race outside saved scoring'}. This is a timing observation, not a causal explanation.</p>}
        <p>{audit.nonconsecutive_next_rows} saved pairs had nonconsecutive next records. Estimated cutoffs and publication latency remain uncertain.</p>
      </section>}
      <OvertakeHistory />
      {error && <p className="ot-note" role="alert">Unavailable: {error}</p>}
      {data && (
        <>
          <p className="ot-lede">
            Timing-inferred pairs within 3 s; later pit stops and neutralised laps are excluded. {data.races_scored} races scored by
            models fitted only on earlier races.
          </p>
          <div className="ot-table-scroll" role="region" aria-label="Scrollable model comparison" tabIndex={0}><table className="ot-table" aria-label="Model comparison">
            <thead><tr><th>MODEL</th><th>BRIER</th><th>LOG-LOSS</th><th>AUC</th><th>AVG PREC.</th><th>ECE</th></tr></thead>
            <tbody>
              {[...data.table].sort((a, b) => a.brier - b.brier).map((row) => (
                <tr key={row.model}>
                  <td>{label(row.model)}</td><td>{fixed(row.brier, 4)}</td><td>{fixed(row.log_loss, 4)}</td>
                  <td>{fixed(row.auc)}</td><td>{fixed(row.average_precision)}</td><td>{fixed(row.ece, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <div className="ot-grid">
            <section aria-label="Paired Brier difference">
              <h3>Brier change vs gap-only logistic</h3>
              <ul className="ot-paired">
                {data.paired_brier_vs_logistic_gap.map((row) => (
                  <li key={row.model}>
                    <span>{label(row.model)}</span>
                    <strong>{row.mean_delta > 0 ? '+' : ''}{fixed(row.mean_delta, 4)}</strong>
                    <em>[{fixed(row.ci_low, 4)}, {fixed(row.ci_high, 4)}]</em>
                  </li>
                ))}
              </ul>
              <p className="ot-note">Negative = better. Interval = race-clustered bootstrap; most skill is the gap itself.</p>
            </section>
            <section aria-label="Calibration">
              <h3>Reliability (calibrated LightGBM)</h3>
              <Reliability bins={data.reliability_lightgbm_calibrated} />
            </section>
          </div>
          <div className="ot-table-scroll" role="region" aria-label="Scrollable season comparison" tabIndex={0}><table className="ot-table" aria-label="By season">
            <thead><tr><th>SEASON</th><th>PAIRS</th><th>SWAP RATE</th><th>MEAN FORECAST</th><th>BRIER</th><th>AUC</th></tr></thead>
            <tbody>
              {data.by_year.map((row) => (
                <tr key={row.year}>
                  <td>{row.year}</td><td>{row.n}</td><td>{(row.rate * 100).toFixed(1)}%</td>
                  <td>{(row.mean_p * 100).toFixed(1)}%</td><td>{fixed(row.brier, 4)}</td><td>{fixed(row.auc)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </>
      )}
    </main>
  )
}
