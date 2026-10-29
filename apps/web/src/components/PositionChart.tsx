import { useEffect, useMemo, useState } from 'react'
import './PositionChart.css'

type Series = { driver_id: string; positions: (number | null)[]; gaps: (number | null)[]; laps: (number | null)[] }
type Timeline = { step_seconds: number; duration_seconds: number; times: number[]; drivers: Series[] }
type DriverMeta = { driver_id: string; acronym: string; team_color: string }

const W = 1000
const H = 280
const PAD = { left: 38, right: 46, top: 14, bottom: 26 }
const GAP_CAP_SECONDS = 120
const color = (hex: string) => (/^[\da-fA-F]{6}$/.test(hex) ? `#${hex}` : '#97a0a9')

/** Position or gap-to-leader history; every point is a canonical RaceState sample. */
export function PositionChart({
  slug, drivers, seconds, selectedId, onSelect, onSeek,
}: {
  slug: string
  drivers: DriverMeta[]
  seconds: number
  selectedId: string | null
  onSelect: (id: string) => void
  onSeek: (seconds: number) => void
}) {
  const [data, setData] = useState<{ slug: string; timeline: Timeline } | null>(null)
  const [error, setError] = useState<{ slug: string; message: string } | null>(null)
  const [mode, setMode] = useState<'position' | 'gap'>('position')

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/v1/replay/${slug}/timeline?step=30`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`timeline ${response.status}`))))
      .then((timeline: Timeline) => setData({ slug, timeline }))
      .catch((cause) => { if (cause.name !== 'AbortError') setError({ slug, message: String(cause.message ?? cause) }) })
    return () => controller.abort()
  }, [slug])

  const timeline = data?.slug === slug ? data.timeline : null
  const failure = error?.slug === slug ? error.message : null
  const meta = useMemo(() => new Map(drivers.map((driver) => [driver.driver_id, driver])), [drivers])

  if (failure) return <section className="position-chart panel" aria-label="Race history"><p className="pc-note">Race history unavailable: {failure}</p></section>
  if (!timeline) return <section className="position-chart panel" aria-label="Race history"><p className="pc-note">Loading race history…</p></section>

  const field = Math.max(...timeline.drivers.flatMap((d) => d.positions.filter((p): p is number => p != null)), 1)
  const maxGap = Math.min(GAP_CAP_SECONDS, Math.max(10, ...timeline.drivers.flatMap((d) => d.gaps.filter((g): g is number => g != null))))
  const x = (t: number) => PAD.left + (t / timeline.duration_seconds) * (W - PAD.left - PAD.right)
  const y = (value: number) => mode === 'position'
    ? PAD.top + ((value - 1) / Math.max(field - 1, 1)) * (H - PAD.top - PAD.bottom)
    : PAD.top + (Math.min(value, maxGap) / maxGap) * (H - PAD.top - PAD.bottom)

  const path = (series: Series) => {
    const values = mode === 'position' ? series.positions : series.gaps.map((gap, i) => (series.positions[i] === 1 ? 0 : gap))
    let d = ''
    let pen = false
    values.forEach((value, i) => {
      if (value == null) { pen = false; return }
      d += `${pen ? 'L' : 'M'}${x(timeline.times[i]).toFixed(1)},${y(value).toFixed(1)}`
      pen = true
    })
    return d
  }
  const ordered = [...timeline.drivers].sort((a, b) => Number(a.driver_id === selectedId) - Number(b.driver_id === selectedId))
  const ticks = Array.from({ length: Math.floor(timeline.duration_seconds / 600) + 1 }, (_, i) => i * 600)
  const rows = mode === 'position' ? Array.from({ length: field }, (_, i) => i + 1).filter((p) => p === 1 || p % 5 === 0) : [0, maxGap / 2, maxGap]

  const seekFromPointer = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const fraction = ((event.clientX - box.left) / box.width * W - PAD.left) / (W - PAD.left - PAD.right)
    onSeek(Math.min(Math.max(fraction, 0), 1) * timeline.duration_seconds)
  }

  return (
    <section className="position-chart panel" aria-label="Race history">
      <div className="pc-heading">
        <div>
          <span className="eyebrow">RACE HISTORY · SOURCE TIMING · {timeline.step_seconds}s SAMPLES</span>
          <h2>{mode === 'position' ? 'Position by session time' : 'Gap to leader'}</h2>
        </div>
        <div className="pc-toggle" role="group" aria-label="Chart metric">
          <button type="button" className={mode === 'position' ? 'active' : ''} onClick={() => setMode('position')}>POSITION</button>
          <button type="button" className={mode === 'gap' ? 'active' : ''} onClick={() => setMode('gap')}>GAP</button>
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Click to seek the replay" onClick={seekFromPointer} data-testid="position-chart">
        {rows.map((row) => (
          <g key={row}>
            <line className="pc-grid" x1={PAD.left} x2={W - PAD.right} y1={y(mode === 'position' ? row : row)} y2={y(mode === 'position' ? row : row)} />
            <text className="pc-axis" x={PAD.left - 6} y={y(row) + 3} textAnchor="end">{mode === 'position' ? `P${row}` : `${Math.round(row)}s`}</text>
          </g>
        ))}
        {ticks.map((t) => (
          <text key={t} className="pc-axis" x={x(t)} y={H - 8} textAnchor="middle">{Math.round(t / 60)}′</text>
        ))}
        {ordered.map((series) => {
          const info = meta.get(series.driver_id)
          const active = series.driver_id === selectedId
          return <path key={series.driver_id} d={path(series)} fill="none" stroke={color(info?.team_color ?? '')}
            strokeWidth={active ? 2.6 : 1.2} opacity={active ? 1 : 0.45} className="pc-line">
            <title>{info?.acronym ?? series.driver_id}</title>
          </path>
        })}
        <line className="pc-cursor" x1={x(Math.min(seconds, timeline.duration_seconds))} x2={x(Math.min(seconds, timeline.duration_seconds))} y1={PAD.top} y2={H - PAD.bottom} />
        {timeline.drivers.map((series) => {
          const last = [...series.positions].reverse().findIndex((p) => p != null)
          if (last < 0) return null
          const index = series.positions.length - 1 - last
          const info = meta.get(series.driver_id)
          const value = mode === 'position' ? series.positions[index]! : (series.gaps[index] ?? 0)
          return (
            <text key={series.driver_id} className={`pc-label ${series.driver_id === selectedId ? 'active' : ''}`}
              x={W - PAD.right + 5} y={y(value) + 3} onClick={(event) => { event.stopPropagation(); onSelect(series.driver_id) }}>
              {info?.acronym ?? series.driver_id}
            </text>
          )
        })}
      </svg>
      <p className="pc-note">Click the chart to seek; click a label to focus a driver. Lines break where the source reports no value. Gap is capped at {GAP_CAP_SECONDS}s.</p>
    </section>
  )
}
