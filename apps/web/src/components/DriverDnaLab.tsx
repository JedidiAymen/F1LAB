import { useEffect, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import './DriverDnaLab.css'

type Row = { model: string; accuracy: number; ci?: [number, number] }
type Summary = {
  laps: number; per_circuit: Record<string, number>; shared_drivers: string[]; chance_task_a: number
  majority_task_b: number; task_a: Row[]; task_b: Row[]; seeds: number[]; device: string; limits: string[]
  task_b_controls: Record<string, { mean_accuracy: number; ci: [number, number] }>
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
const label = (name: string) => name.replaceAll('_', ' ')

function Bars({ rows, reference, referenceLabel }: { rows: Row[]; reference: number; referenceLabel: string }) {
  return (
    <ul className="dna-bars">
      {rows.map((row) => (
        <li key={row.model}>
          <span>{row.model}</span>
          <div className="dna-track">
            <i style={{ width: pct(row.accuracy) }} />
            {row.ci && <b style={{ left: pct(row.ci[0]), width: pct(row.ci[1] - row.ci[0]) }} />}
            <u style={{ left: pct(reference) }} title={referenceLabel} />
          </div>
          <strong>{pct(row.accuracy)}</strong>
        </li>
      ))}
    </ul>
  )
}

export function DriverDnaLab({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/driver-dna/summary', { signal: controller.signal })
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
    <main className="dna">
      <button className="prediction-back" type="button" onClick={onBack}><ArrowLeft size={15} /> Race Control</button>
      <span className="eyebrow">DRIVER DNA · EVALUATION · NOT A LIVE MODEL</span>
      <h2>Can telemetry tell drivers apart?</h2>
      {error && <p className="dna-note" role="alert">Unavailable: {error}</p>}
      {data && (
        <>
          <p className="dna-lede">
            {data.laps.toLocaleString()} clean race laps from {Object.keys(data.per_circuit).join(', ')} resampled to
            256 points of lap distance. {data.shared_drivers.length} drivers race in all three events.
            Neural models use {data.seeds.length} seeds on {data.device}.
          </p>
          <section aria-label="Cross-circuit identification">
            <h3>Task A · identify the driver on an unseen circuit</h3>
            <Bars rows={data.task_a} reference={data.chance_task_a} referenceLabel="chance" />
            <p className="dna-note">Marker = chance ({pct(data.chance_task_a)}). Drivers who kept the same car can be recognised by the car.</p>
          </section>
          <section aria-label="Teammate discrimination">
            <h3>Task B · tell two teammates apart (same car)</h3>
            <Bars rows={data.task_b} reference={data.majority_task_b} referenceLabel="majority baseline" />
            <p className="dna-note">Marker = majority baseline ({pct(data.majority_task_b)}); bar overlay = 95% interval over teammate pairs.</p>
            <ul className="dna-controls" aria-label="Confound controls">
              {Object.entries(data.task_b_controls).map(([name, value]) => (
                <li key={name}><span>{label(name)}</span><strong>{pct(value.mean_accuracy)}</strong></li>
              ))}
            </ul>
          </section>
          <ul className="dna-limits">{data.limits.map((text) => <li key={text}>{text}</li>)}</ul>
        </>
      )}
    </main>
  )
}
