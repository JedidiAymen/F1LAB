import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Gauge } from 'lucide-react'
import './RacePaceLab.css'

type RaceRef = { race_id: string; year: number; event: string; circuit: string; laps: number; drivers: number[] }
type Contribution = { feature: string; seconds: number }
type LapForecast = {
  cutoff_lap: number; target_lap: number; forecast_seconds: number; q10_seconds: number; q90_seconds: number
  baseline_seconds: number; actual_seconds: number; compound: string; tyre_age: number; regime: string
  green_clean: boolean; contributions: Contribution[]
}
type Forecast = { evidence: string; model_id: string; laps: LapForecast[]; note: string }
type Manifest = {
  model: { model_id: string; limitations: string[] }
  summary: {
    green_table: { model: string; n: number; mae: number; rmse: number }[]
    paired_vs_anchor: { model: string; mean_delta: number; ci_low: number; ci_high: number; clusters: number }[]
    interval: { nominal: number; empirical: number; mean_width_s: number }
    ablations?: { ablation: string; mae: number; delta_vs_full: number }[]
  }
  races: RaceRef[]
}

const W = 1000
const H = 300
const PAD = { left: 48, right: 16, top: 12, bottom: 26 }
const fixed = (v: number | null | undefined, d = 3) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(d))
const featureName = (name: string) => name.replaceAll('_', ' ')

export function RacePaceLab({ onBack }: { onBack: () => void }) {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [raceId, setRaceId] = useState('')
  const [driver, setDriver] = useState(0)
  const [forecast, setForecast] = useState<{ key: string; data: Forecast } | null>(null)
  const [selectedLap, setSelectedLap] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/pace/races', { signal: controller.signal })
      .then(async (r) => (r.ok ? (r.json() as Promise<Manifest>) : Promise.reject(new Error((await r.json()).detail ?? 'unavailable'))))
      .then((data) => {
        setManifest(data)
        const last = data.races.at(-1)
        if (last) { setRaceId(last.race_id); setDriver(last.drivers[0]) }
      })
      .catch((cause) => { if (cause.name !== 'AbortError') setError(String(cause.message ?? cause)) })
    return () => controller.abort()
  }, [])

  const race = manifest?.races.find((r) => r.race_id === raceId)
  const key = `${raceId}:${driver}`
  useEffect(() => {
    if (!raceId || !driver) return
    const controller = new AbortController()
    fetch(`/api/v1/pace/forecast?race_id=${raceId}&driver=${driver}`, { signal: controller.signal })
      .then(async (r) => (r.ok ? (r.json() as Promise<Forecast>) : Promise.reject(new Error((await r.json()).detail ?? 'unavailable'))))
      .then((data) => setForecast({ key: `${raceId}:${driver}`, data }))
      .catch((cause) => { if (cause.name !== 'AbortError') setError(String(cause.message ?? cause)) })
    return () => controller.abort()
  }, [raceId, driver])

  const laps = forecast?.key === key ? forecast.data.laps : null
  const view = useMemo(() => {
    if (!laps?.length) return null
    const clean = laps.filter((l) => l.green_clean).map((l) => l.actual_seconds)
    const sorted = [...clean].sort((a, b) => a - b)
    const at = (f: number) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * f))] ?? 90
    const iqr = Math.max(at(0.75) - at(0.25), 0.3)
    // Robust range: outliers (pit laps, undetected neutralisations) clamp to the edge instead of squashing the chart.
    const lo = Math.max(at(0.02), at(0.25) - 3 * iqr)
    const hi = Math.min(at(0.98), at(0.75) + 3 * iqr)
    const margin = Math.max((hi - lo) * 0.15, 0.4)
    return { lo: lo - margin, hi: hi + margin, first: laps[0].target_lap, last: laps.at(-1)!.target_lap }
  }, [laps])

  const selected = laps?.find((l) => l.target_lap === selectedLap) ?? laps?.find((l) => l.green_clean) ?? null

  if (error && !manifest) return (
    <div className="workstation pace-lab"><main className="pace-main"><div className="pace-error" role="alert">Race pace artifacts unavailable: {error}</div></main></div>
  )
  if (!manifest || !race) return <div className="workstation pace-lab"><main className="pace-main"><p className="pace-note">Loading race pace forecasts…</p></main></div>

  const lightgbm = manifest.summary.green_table.find((r) => r.model === 'lightgbm')
  const anchor = manifest.summary.green_table.find((r) => r.model === 'anchor_median3')
  const persistence = manifest.summary.green_table.find((r) => r.model === 'persistence_last_lap')
  const paired = manifest.summary.paired_vs_anchor.find((r) => r.model === 'lightgbm')
  const x = (lap: number) => view ? PAD.left + ((lap - view.first) / Math.max(view.last - view.first, 1)) * (W - PAD.left - PAD.right) : 0
  const y = (s: number) => view ? PAD.top + (1 - (Math.min(Math.max(s, view.lo), view.hi) - view.lo) / (view.hi - view.lo)) * (H - PAD.top - PAD.bottom) : 0
  const line = (pick: (l: LapForecast) => number) => (laps ?? []).map((l, i) => `${i ? 'L' : 'M'}${x(l.target_lap).toFixed(1)},${y(pick(l)).toFixed(1)}`).join('')
  const band = laps && view ? `${laps.map((l, i) => `${i ? 'L' : 'M'}${x(l.target_lap).toFixed(1)},${y(l.q90_seconds).toFixed(1)}`).join('')}${[...laps].reverse().map((l) => `L${x(l.target_lap).toFixed(1)},${y(l.q10_seconds).toFixed(1)}`).join('')}Z` : ''
  const maxContribution = Math.max(0.01, ...(selected?.contributions.map((c) => Math.abs(c.seconds)) ?? [0]))

  return (
    <div className="workstation pace-lab">
      <header className="topbar">
        <div className="brand"><div className="brand-mark">F<span>1</span></div><div className="brand-name">LAB <span>/ RACE INTELLIGENCE</span></div></div>
        <div className="session-id"><Gauge size={15} /><span>RACE PACE INTELLIGENCE</span></div>
        <button className="prediction-back" type="button" onClick={onBack}><ArrowLeft size={15} /> Race Control</button>
      </header>
      <main className="pace-main">
        <div className="pace-heading">
          <div>
            <div className="eyebrow">NEXT-LAP FORECAST · OUT-OF-FOLD · HISTORICAL</div>
            <h1>Race Pace <span>Intelligence</span></h1>
            <p>Each forecast uses only information at the end of the cutoff lap and a model fitted on earlier races.</p>
          </div>
          <div className="pace-stamp">ML PREDICTION · NOT LIVE</div>
        </div>

        <section className="pace-evidence panel" aria-label="Benchmark evidence">
          <div><span>LightGBM MAE</span><strong>{fixed(lightgbm?.mae)} s</strong><em>vs {fixed(anchor?.mae)} s rolling median</em></div>
          <div><span>Paired Δ vs median (races)</span><strong>{fixed(paired?.mean_delta)} s</strong><em>[{fixed(paired?.ci_low)}, {fixed(paired?.ci_high)}] · {paired?.clusters} races</em></div>
          <div><span>Last-lap persistence</span><strong>{fixed(persistence?.mae)} s</strong><em>strong simple baseline</em></div>
          <div><span>80% interval coverage</span><strong>{fixed(manifest.summary.interval.empirical * 100, 1)}%</strong><em>mean width {fixed(manifest.summary.interval.mean_width_s, 2)} s</em></div>
        </section>

        <section className="pace-controls panel">
          <label><span className="eyebrow">RACE</span>
            <select aria-label="Race" value={raceId} onChange={(e) => { const next = manifest.races.find((r) => r.race_id === e.target.value)!; setRaceId(next.race_id); setDriver(next.drivers.includes(driver) ? driver : next.drivers[0]); setSelectedLap(null) }}>
              {manifest.races.map((r) => <option key={r.race_id} value={r.race_id}>{r.year} · {r.event}</option>)}
            </select></label>
          <label><span className="eyebrow">DRIVER #</span>
            <select aria-label="Driver number" value={driver} onChange={(e) => { setDriver(Number(e.target.value)); setSelectedLap(null) }}>
              {race.drivers.map((d) => <option key={d} value={d}>#{d}</option>)}
            </select></label>
        </section>

        <section className="pace-chart panel" aria-label="Forecast versus actual lap time">
          {!laps || !view ? <p className="pace-note">Loading…</p> : (
            <>
              <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Actual and forecast lap times" data-testid="pace-chart">
                {[0, 0.25, 0.5, 0.75, 1].map((f) => { const s = view.lo + (view.hi - view.lo) * f; return <g key={f}><line className="pace-grid" x1={PAD.left} x2={W - PAD.right} y1={y(s)} y2={y(s)} /><text className="pace-axis" x={PAD.left - 6} y={y(s) + 3} textAnchor="end">{s.toFixed(1)}</text></g> })}
                <path className="pace-band" d={band} />
                <path className="pace-baseline" d={line((l) => l.baseline_seconds)} />
                <path className="pace-forecast" d={line((l) => l.forecast_seconds)} />
                {laps.map((l) => (
                  <circle key={l.target_lap} cx={x(l.target_lap)} cy={y(l.actual_seconds)} r={selected?.target_lap === l.target_lap ? 5 : 3}
                    className={l.green_clean ? 'pace-dot clean' : 'pace-dot other'} onClick={() => setSelectedLap(l.target_lap)}>
                    <title>{`Lap ${l.target_lap}: actual ${l.actual_seconds.toFixed(3)} s · forecast ${l.forecast_seconds.toFixed(3)} s · ${l.regime}${l.green_clean ? '' : ' (not green clean)'}`}</title>
                  </circle>
                ))}
                {[...new Set(laps.map((l) => l.target_lap).filter((n) => n % 10 === 0))].map((n) => <text key={n} className="pace-axis" x={x(n)} y={H - 8} textAnchor="middle">L{n}</text>)}
              </svg>
              <p className="pace-legend"><i className="pace-dot clean inline" /> actual green-clean · <i className="pace-dot other inline" /> actual, not green clean (pit, SC, yellow, red) · <span className="lg forecast" /> forecast · <span className="lg baseline" /> rolling-median baseline · shaded 10–90% interval. Axis range is robust (IQR-based); laps outside it sit on the edge.</p>
            </>
          )}
        </section>

        {selected && (
          <section className="pace-detail panel" aria-label="Selected lap forecast">
            <div>
              <span className="eyebrow">LAP {selected.target_lap} · FORECAST AT END OF LAP {selected.cutoff_lap}</span>
              <h2>{fixed(selected.forecast_seconds)} s <small>[{fixed(selected.q10_seconds, 2)}, {fixed(selected.q90_seconds, 2)}]</small></h2>
              <p>Actual {fixed(selected.actual_seconds)} s (retrospective) · error {fixed(selected.forecast_seconds - selected.actual_seconds)} s · baseline error {fixed(selected.baseline_seconds - selected.actual_seconds)} s.</p>
              <p>{selected.compound} · tyre age {selected.tyre_age} laps (scenario input) · regime <b>{selected.regime}</b>{selected.green_clean ? '' : ' — outside the model’s green-clean domain'}.</p>
            </div>
            <div className="pace-contrib" aria-label="Feature contributions">
              <span className="eyebrow">CONTRIBUTION TO THE DELTA FROM THE 3-LAP MEDIAN (s)</span>
              {selected.contributions.map((c) => (
                <div key={c.feature} className="contrib-row"><span>{featureName(c.feature)}</span>
                  <i className={c.seconds >= 0 ? 'pos' : 'neg'} style={{ width: `${(Math.abs(c.seconds) / maxContribution) * 45}%`, marginLeft: c.seconds >= 0 ? '50%' : `${50 - (Math.abs(c.seconds) / maxContribution) * 45}%` }} />
                  <b>{c.seconds >= 0 ? '+' : ''}{c.seconds.toFixed(3)}</b></div>
              ))}
              <p className="pace-note">Additive tree attributions describe this model’s arithmetic, not causes.</p>
            </div>
          </section>
        )}

        <section className="pace-limits panel">
          <span className="eyebrow">EVIDENCE &amp; LIMITS</span>
          <ul>{manifest.model.limitations.map((l) => <li key={l}>{l}</li>)}
            {manifest.summary.ablations && <li>Ablation: removing previous-pace features costs {fixed(manifest.summary.ablations.find((a) => a.ablation === 'minus_previous_pace')?.delta_vs_full)} s MAE; removing weather changes it by {fixed(manifest.summary.ablations.find((a) => a.ablation === 'minus_weather')?.delta_vs_full)} s (no gain from weather).</li>}
            <li>Safety-car laps are not forecastable (about 30 s error for every model).</li></ul>
        </section>
      </main>
    </div>
  )
}
