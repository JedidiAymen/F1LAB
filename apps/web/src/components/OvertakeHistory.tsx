import { useEffect, useState } from 'react'

type Event = { race_id: string; event: string; year: number; pairs: number }
type Row = { lap: number; follower: number; leader: number; cutoff_utc: string; leader_cutoff_utc: string; interval_seconds: number; interval_age_seconds: number | null; timing_order_swapped: boolean; probabilities: Record<string, number> }
type Summary = { table: { model: string; n: number; brier: number }[] }
type Catalog = { events: Event[]; corrected_summary: Summary; status: string }
const MODELS: Record<string, string> = { constant_rate: 'Training rate', logistic_gap: 'Gap-only logistic', logistic_all: 'All-feature logistic', lightgbm_raw: 'LightGBM', lightgbm_calibrated: 'Calibrated LightGBM' }

export function OvertakeHistory() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [missing, setMissing] = useState(false)
  const [race, setRace] = useState('')
  const [loadedRace, setLoadedRace] = useState('')
  const [rows, setRows] = useState<Row[]>([])
  const [selected, setSelected] = useState(0)
  const [model, setModel] = useState('lightgbm_calibrated')
  const [caseError, setCaseError] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/overtake/historical/catalog', { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error('Unavailable')
      return response.json() as Promise<Catalog>
    }).then((value) => { setCatalog(value); setRace(value.events[0]?.race_id ?? '') })
      .catch((cause) => { if (cause.name !== 'AbortError') setMissing(true) })
    return () => controller.abort()
  }, [])
  useEffect(() => {
    if (!race) return
    const controller = new AbortController()
    fetch(`/api/v1/overtake/historical/cases?race_id=${encodeURIComponent(race)}`, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error('Unavailable')
      return response.json() as Promise<{ race_id: string; cases: Row[] }>
    }).then((value) => { setRows(value.cases); setLoadedRace(value.race_id); setCaseError(false) })
      .catch((cause) => { if (cause.name !== 'AbortError') setCaseError(true) })
    return () => controller.abort()
  }, [race])
  const row = loadedRace === race ? rows[selected] : null
  const score = catalog?.corrected_summary.table.find((item) => item.model === model)
  return <section className="ot-history" aria-label="Historical timing forecast explorer">
    <h3>Explore a saved historical forecast</h3>
    <p>Out-of-fold predictions from the corrected retrospective study. Later pit and neutralization outcomes selected these pairs, so the displayed probability is not an unconditional live forecast. Timing swaps are not verified passes. Next-lap tyre inputs and a completed-race length proxy may use information unavailable at cutoff.</p>
    {missing && <p role="status">Corrected local study artifacts are unavailable; see the reproduction instructions to build them.</p>}
    {!catalog && !missing && <p role="status">Loading saved historical forecasts…</p>}
    {catalog && <>
      <div className="ot-history-controls"><label>Race<select aria-label="Historical overtake race" value={race} onChange={(e) => { setRace(e.target.value); setSelected(0) }}>{catalog.events.map((event) => <option key={event.race_id} value={event.race_id}>{event.year} {event.event} · {event.pairs} pairs</option>)}</select></label>
        <label>Model<select aria-label="Historical overtake model" value={model} onChange={(e) => setModel(e.target.value)}>{Object.entries(MODELS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label></div>
      {score && <p>Corrected retrospective Brier: {score.brier.toFixed(4)} across {score.n.toLocaleString()} scored pairs. Original results below use the earlier dataset.</p>}
      {caseError && <p role="status">Selected race artifacts are unavailable or invalid.</p>}
      {loadedRace === race && rows.length > 0 && <label>Pair at cutoff<select aria-label="Historical overtake pair" value={selected} onChange={(e) => setSelected(Number(e.target.value))}>{rows.map((item, index) => <option key={`${item.lap}-${item.follower}-${item.leader}`} value={index}>Lap {item.lap} · #{item.follower} follows #{item.leader}</option>)}</select></label>}
      {row && <div className="ot-history-result" role="status" aria-label="Historical overtake forecast"><strong>{(row.probabilities[model] * 100).toFixed(1)}%</strong><p>{MODELS[model]} estimated a next-lap timing-order swap for #{row.follower} behind #{row.leader}. Later timing {row.timing_order_swapped ? 'showed an order swap' : 'did not show an order swap'} in this selected cohort.</p><p>Follower cutoff {row.cutoff_utc}; leader cutoff {row.leader_cutoff_utc}. Interval {row.interval_seconds.toFixed(3)} s; observation age {row.interval_age_seconds === null ? 'unknown' : `${row.interval_age_seconds.toFixed(3)} s`}.</p></div>}
      <p>Historical race labels and source cutoffs are estimates; provider publication latency and physical positions are not certified. These races were already inspected.</p>
    </>}
  </section>
}
