import { useEffect, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import './OvertakeLab.css'

type Row = { model: string; n: number; brier: number; log_loss: number; auc: number; average_precision: number; ece: number }
type Paired = { model: string; baseline: string; mean_delta: number; ci_low: number; ci_high: number; clusters: number }
type Bin = { n: number; mean_predicted: number; observed: number }
type Year = { year: number; n: number; rate: number; mean_p: number; brier: number; auc: number }
type Summary = {
  races_scored: number; table: Row[]; paired_brier_vs_logistic_gap: Paired[]
  reliability_lightgbm_calibrated: Bin[]; by_year: Year[]
}

const fixed = (v: number, d = 3) => v.toFixed(d)
const label = (name: string) => name.replaceAll('_', ' ')

function Reliability({ bins }: { bins: Bin[] }) {
  const size = 200
  const pad = 28
  const max = Math.max(0.01, ...bins.flatMap((b) => [b.mean_predicted, b.observed])) * 1.1
  const x = (v: number) => pad + (v / max) * (size - pad - 8)
  const y = (v: number) => size - pad - (v / max) * (size - pad - 8)
  return (
    <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Reliability: forecast pass probability versus observed frequency" className="ot-rel">
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

  return (
    <main className="ot">
      <button className="prediction-back" type="button" onClick={onBack}><ArrowLeft size={15} /> Race Control</button>
      <span className="eyebrow">OVERTAKE INTELLIGENCE · WALK-FORWARD · NOT LIVE</span>
      <h2>Will the car behind pass next lap?</h2>
      {error && <p className="ot-note" role="alert">Unavailable: {error}</p>}
      {data && (
        <>
          <p className="ot-lede">
            Pairs within 3 s on track; pit stops and neutralised laps are excluded. {data.races_scored} races scored by
            models fitted only on earlier races.
          </p>
          <table className="ot-table" aria-label="Model comparison">
            <thead><tr><th>MODEL</th><th>BRIER</th><th>LOG-LOSS</th><th>AUC</th><th>AVG PREC.</th><th>ECE</th></tr></thead>
            <tbody>
              {[...data.table].sort((a, b) => a.brier - b.brier).map((row) => (
                <tr key={row.model}>
                  <td>{label(row.model)}</td><td>{fixed(row.brier, 4)}</td><td>{fixed(row.log_loss, 4)}</td>
                  <td>{fixed(row.auc)}</td><td>{fixed(row.average_precision)}</td><td>{fixed(row.ece, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
          <table className="ot-table" aria-label="By season">
            <thead><tr><th>SEASON</th><th>PAIRS</th><th>PASS RATE</th><th>MEAN FORECAST</th><th>BRIER</th><th>AUC</th></tr></thead>
            <tbody>
              {data.by_year.map((row) => (
                <tr key={row.year}>
                  <td>{row.year}</td><td>{row.n}</td><td>{(row.rate * 100).toFixed(1)}%</td>
                  <td>{(row.mean_p * 100).toFixed(1)}%</td><td>{fixed(row.brier, 4)}</td><td>{fixed(row.auc)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  )
}
