import { useMemo, useState } from 'react'
import {
  channelValue, comparisonCursorAtSessionTime, referenceLapStartSessionSeconds,
  TELEMETRY_CHANNELS, telemetryChannelPath,
  type LapComparison, type TelemetryChannelId,
} from '@/lib/telemetry-comparison'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const PLOT = { left: 74, right: 980, top: 40, bottom: 166, deltaTop: 218, deltaBottom: 294 }
const formatSeconds = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(3)} s`
const formatValue = (value: number | null) => value === null ? 'Unavailable' : Number.isInteger(value) ? String(value) : value.toFixed(1)

export function TelemetryPanel({ seconds, clockOriginUtc, comparison, available, loading, error, onSeek }: {
  seconds: number
  clockOriginUtc: string
  comparison: LapComparison | null
  available: boolean
  loading: boolean
  error: string | null
  onSeek: (seconds: number) => void
}) {
  const [channelId, setChannelId] = useState<TelemetryChannelId>('speed')
  const channel = TELEMETRY_CHANNELS.find((entry) => entry.id === channelId)!
  const cursor = comparison ? comparisonCursorAtSessionTime(comparison, clockOriginUtc, seconds) : null
  const lapStart = comparison ? referenceLapStartSessionSeconds(comparison, clockOriginUtc) : null
  // Build full traces only when the artifact or channel changes, never on clock ticks.
  const plot = useMemo(() => {
    const samples = comparison?.samples ?? []
    const distanceEnd = comparison?.common_distance_end_m || 1
    const values = samples.flatMap((sample) => [channelValue(sample, channel, 'a'), channelValue(sample, channel, 'b')]).filter((value): value is number => value !== null)
    const max = Math.max(channel.defaultMax, ...values)
    const y = (value: number) => PLOT.bottom - value / max * (PLOT.bottom - PLOT.top)
    const x = (distance: number) => PLOT.left + distance / distanceEnd * (PLOT.right - PLOT.left)
    const deltas = samples.map((sample) => sample.delta_time_b_minus_a_seconds)
    const minDelta = Math.min(0, ...deltas)
    const maxDelta = Math.max(0, ...deltas)
    const padding = Math.max(0.03, (maxDelta - minDelta) * 0.08)
    const deltaMin = minDelta - padding
    const deltaMax = maxDelta + padding
    const deltaY = (value: number) => PLOT.deltaBottom - (value - deltaMin) / (deltaMax - deltaMin) * (PLOT.deltaBottom - PLOT.deltaTop)
    return {
      distanceEnd, max, x, y, deltaMin, deltaMax, deltaY,
      availableA: samples.some((sample) => channelValue(sample, channel, 'a') !== null),
      availableB: samples.some((sample) => channelValue(sample, channel, 'b') !== null),
      pathA: telemetryChannelPath(samples, channel, 'a', (distance, value) => [x(distance), y(value)]),
      pathB: telemetryChannelPath(samples, channel, 'b', (distance, value) => [x(distance), y(value)]),
      deltaPath: samples.map((sample, index) => `${index === 0 ? 'M' : 'L'}${x(sample.distance_m).toFixed(2)} ${deltaY(sample.delta_time_b_minus_a_seconds).toFixed(2)}`).join(' '),
    }
  }, [comparison, channel])
  const cursorX = cursor ? plot.x(cursor.distance_m) : null

  return (
    <section className="telemetry-panel panel" aria-label="Telemetry comparison" data-testid="telemetry-panel"
      data-session-time={seconds} data-cursor-distance={cursor?.distance_m.toFixed(3) ?? ''}
      data-cursor-visible={cursor ? 'true' : 'false'} data-channel={channelId}>
      <div className="panel-heading telemetry-heading">
        <div>
          <span className="eyebrow">LAP ANALYSIS · HISTORICAL SOURCE DATA</span>
          <h2>{comparison ? `#${comparison.lap_a.driver_number} L${comparison.lap_a.lap_number} vs #${comparison.lap_b.driver_number} L${comparison.lap_b.lap_number}` : 'Distance-aligned comparison'}</h2>
        </div>
        <span className="panel-tag">SPEED-INTEGRATED · ESTIMATED</span>
      </div>
      {loading ? <p className="telemetry-empty">Loading cached telemetry comparison…</p>
        : error ? <p className="telemetry-empty" role="status">Telemetry comparison unavailable: {error}</p>
        : !available ? <p className="telemetry-empty">Build this session’s local comparison with the documented telemetry command.</p>
        : !comparison ? <p className="telemetry-empty">The comparison artifact is not available from the replay service.</p>
        : <>
          <Tabs value={channelId} onValueChange={(value) => setChannelId(value as TelemetryChannelId)} className="telemetry-channel-tabs">
            <div className="telemetry-channel-controls">
              <TabsList aria-label="Telemetry channel" variant="line">
                {TELEMETRY_CHANNELS.map((entry) => <TabsTrigger key={entry.id} value={entry.id}>{entry.label}</TabsTrigger>)}
              </TabsList>
              <span>{channel.discrete ? 'PREVIOUS SOURCE VALUE · STEP TRACE' : 'LINEAR INTERPOLATION'} · {channel.unit}</span>
            </div>
            <TabsContent value={channelId} className="telemetry-chart-wrap">
              {(!plot.availableA || !plot.availableB) && <p className="telemetry-channel-unavailable" role="status">
                {channel.label} unavailable for {!plot.availableA ? `#${comparison.lap_a.driver_number}` : ''}{!plot.availableA && !plot.availableB ? ' and ' : ''}{!plot.availableB ? `#${comparison.lap_b.driver_number}` : ''}. Missing readings are gaps.
              </p>}
              <svg className="telemetry-chart" viewBox="0 0 1020 354" role="img"
                aria-label={`${channel.label} and B minus A time across estimated distance. ${comparison.lap_a.lap_duration_seconds.toFixed(3)} second reference lap.`}>
                <rect x="0" y="0" width="1020" height="354" fill="#151c21" />
                {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
                  const value = plot.max * fraction
                  const y = plot.y(value)
                  return <g key={`channel-${fraction}`}>
                    <line x1={PLOT.left} x2={PLOT.right} y1={y} y2={y} className="telemetry-grid-line" />
                    <text x={PLOT.left - 12} y={y + 4} textAnchor="end" className="telemetry-axis-label">{Number.isInteger(value) ? value : value.toFixed(1)}</text>
                  </g>
                })}
                {[plot.deltaMin, 0, plot.deltaMax].map((delta) => {
                  const y = plot.deltaY(delta)
                  const crowdedWithZero = delta !== 0 && Math.abs(y - plot.deltaY(0)) < 14
                  return <g key={`delta-${delta}`}>
                    <line x1={PLOT.left} x2={PLOT.right} y1={y} y2={y} className="telemetry-grid-line" />
                    {!crowdedWithZero && <text x={PLOT.left - 12} y={y + 4} textAnchor="end" className="telemetry-axis-label">{delta.toFixed(2)}</text>}
                  </g>
                })}
                {[0, 0.25, 0.5, 0.75, 1].map((fraction) => <g key={`distance-${fraction}`}>
                  <line x1={plot.x(plot.distanceEnd * fraction)} x2={plot.x(plot.distanceEnd * fraction)} y1={PLOT.top} y2={PLOT.deltaBottom} className="telemetry-grid-line telemetry-grid-vertical" />
                  <text x={plot.x(plot.distanceEnd * fraction)} y="316" textAnchor="middle" className="telemetry-axis-label">{Math.round(plot.distanceEnd * fraction)}</text>
                </g>)}
                <text x="10" y="25" className="telemetry-axis-title">{channel.axis}</text>
                <text x="10" y="258" className="telemetry-axis-title">B − A (S)</text>
                <text x={(PLOT.left + PLOT.right) / 2} y="346" textAnchor="middle" className="telemetry-axis-title">ESTIMATED DISTANCE FROM LAP START (M)</text>
                <path d={plot.pathA} className="telemetry-line telemetry-line-a" data-testid="telemetry-trace-a" />
                <path d={plot.pathB} className="telemetry-line telemetry-line-b" data-testid="telemetry-trace-b" />
                <path d={plot.deltaPath} className="telemetry-line telemetry-line-delta" />
                {cursorX !== null && <line x1={cursorX} x2={cursorX} y1={PLOT.top} y2={PLOT.deltaBottom} className="telemetry-cursor" data-testid="telemetry-cursor" />}
              </svg>
              <div className="telemetry-legend" aria-hidden="true">
                <span><i className="telemetry-key key-a" />#{comparison.lap_a.driver_number} {channel.label.toLowerCase()}</span>
                <span><i className="telemetry-key key-b" />#{comparison.lap_b.driver_number} {channel.label.toLowerCase()}</span>
                <span><i className="telemetry-key key-delta" />B − A cumulative time</span>
              </div>
            </TabsContent>
          </Tabs>
          <div className="telemetry-readout" aria-live="polite">
            {cursor ? <>
              <div><span>CANONICAL REPLAY CURSOR</span><strong>{cursor.distance_m.toFixed(0)} m</strong></div>
              <div><span>B − A AT THIS DISTANCE</span><strong>{formatSeconds(cursor.delta_time_b_minus_a_seconds)}</strong></div>
            </> : <div className="telemetry-outside">
              <span>CANONICAL SESSION TIME IS OUTSIDE THE SHARED TELEMETRY RANGE</span>
              <strong>{lapStart !== null ? `Lap #${comparison.lap_a.driver_number} L${comparison.lap_a.lap_number} starts at ${lapStart.toFixed(3)} s` : 'Reference lap start time is unavailable'}</strong>
            </div>}
            {!cursor && lapStart !== null && <Button variant="outline" size="sm" onClick={() => onSeek(lapStart)}>Jump to reference lap</Button>}
          </div>
          {cursor && <div className="telemetry-channel-readouts">
            <table aria-label="Canonical telemetry cursor readings">
              <thead><tr><th scope="col">CHANNEL</th><th scope="col">#{comparison.lap_a.driver_number}</th><th scope="col">#{comparison.lap_b.driver_number}</th><th scope="col">SOURCE UNITS</th></tr></thead>
              <tbody>{TELEMETRY_CHANNELS.map((entry) => <tr key={entry.id} data-channel={entry.id}>
                <th scope="row">{entry.label}{entry.id === 'brake' || entry.id === 'drs' ? ' · raw' : ''}</th>
                <td>{formatValue(channelValue(cursor, entry, 'a'))}</td><td>{formatValue(channelValue(cursor, entry, 'b'))}</td><td>{entry.unit}</td>
              </tr>)}</tbody>
            </table>
          </div>}
          <div className="panel-note">
            Cursor follows the canonical replay clock over the shared distance grid. Distance and lap boundaries are estimated from sampled speed and timing.
            {' '}Brake values and DRS codes retain provider meaning; no on/off inference. Throttle source values can exceed 100%. Missing channels remain unavailable.
            {comparison.lap_a.maximum_sample_gap_seconds !== undefined && comparison.lap_b.maximum_sample_gap_seconds !== undefined
              ? ` Maximum source gaps A/B: ${comparison.lap_a.maximum_sample_gap_seconds.toFixed(3)} / ${comparison.lap_b.maximum_sample_gap_seconds.toFixed(3)} s.` : ''}
          </div>
        </>}
    </section>
  )
}
