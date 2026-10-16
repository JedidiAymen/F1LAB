import {
  comparisonCursorAtSessionTime,
  referenceLapStartSessionSeconds,
  type LapComparison,
  type TelemetryComparisonSample,
} from '@/lib/telemetry-comparison'
import { Button } from '@/components/ui/button'

const PLOT = {
  left: 74,
  right: 980,
  speedTop: 40,
  speedBottom: 166,
  deltaTop: 218,
  deltaBottom: 294,
}

function formatSeconds(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(3)} s`
}

function pathFor(
  samples: TelemetryComparisonSample[],
  project: (sample: TelemetryComparisonSample) => [number, number],
) {
  return samples
    .map((sample, index) => {
      const [x, y] = project(sample)
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}

export function TelemetryPanel({
  seconds,
  clockOriginUtc,
  comparison,
  available,
  loading,
  error,
  onSeek,
}: {
  seconds: number
  clockOriginUtc: string
  comparison: LapComparison | null
  available: boolean
  loading: boolean
  error: string | null
  onSeek: (seconds: number) => void
}) {
  const cursor = comparison
    ? comparisonCursorAtSessionTime(comparison, clockOriginUtc, seconds)
    : null
  const lapStart = comparison
    ? referenceLapStartSessionSeconds(comparison, clockOriginUtc)
    : null
  const distanceEnd = comparison?.common_distance_end_m ?? 1
  const speeds = comparison
    ? comparison.samples.flatMap((sample) => [sample.speed_a_kmh, sample.speed_b_kmh])
    : [360]
  const speedMax = Math.max(360, Math.ceil(Math.max(...speeds) / 50) * 50)
  const deltas = comparison
    ? comparison.samples.map((sample) => sample.delta_time_b_minus_a_seconds)
    : [-0.4, 0.25]
  const deltaMin = Math.min(0, ...deltas)
  const deltaMax = Math.max(0, ...deltas)
  const deltaPadding = Math.max(0.03, (deltaMax - deltaMin) * 0.08)
  const plotDeltaMin = deltaMin - deltaPadding
  const plotDeltaMax = deltaMax + deltaPadding
  const x = (distance: number) =>
    PLOT.left + (distance / distanceEnd) * (PLOT.right - PLOT.left)
  const speedY = (value: number) =>
    PLOT.speedBottom - (Math.max(0, Math.min(speedMax, value)) / speedMax) * (PLOT.speedBottom - PLOT.speedTop)
  const deltaY = (value: number) =>
    PLOT.deltaBottom - ((value - plotDeltaMin) / (plotDeltaMax - plotDeltaMin)) * (PLOT.deltaBottom - PLOT.deltaTop)
  const speedAPath = comparison
    ? pathFor(comparison.samples, (sample) => [x(sample.distance_m), speedY(sample.speed_a_kmh)])
    : ''
  const speedBPath = comparison
    ? pathFor(comparison.samples, (sample) => [x(sample.distance_m), speedY(sample.speed_b_kmh)])
    : ''
  const deltaPath = comparison
    ? pathFor(comparison.samples, (sample) => [x(sample.distance_m), deltaY(sample.delta_time_b_minus_a_seconds)])
    : ''
  const cursorX = cursor ? x(cursor.distance_m) : null

  return (
    <section
      className="telemetry-panel panel"
      aria-label="Telemetry comparison"
      data-testid="telemetry-panel"
      data-session-time={seconds}
      data-cursor-distance={cursor?.distance_m.toFixed(3) ?? ''}
      data-cursor-visible={cursor ? 'true' : 'false'}
    >
      <div className="panel-heading telemetry-heading">
        <div>
          <span className="eyebrow">LAP ANALYSIS · HISTORICAL SOURCE DATA</span>
          <h2>{comparison
            ? `#${comparison.lap_a.driver_number} L${comparison.lap_a.lap_number} vs #${comparison.lap_b.driver_number} L${comparison.lap_b.lap_number}`
            : 'Distance-aligned comparison'}
          </h2>
        </div>
        <span className="panel-tag">SPEED-INTEGRATED · ESTIMATED</span>
      </div>
      {loading ? (
        <p className="telemetry-empty">Loading cached telemetry comparison…</p>
      ) : error ? (
        <p className="telemetry-empty" role="status">Telemetry comparison unavailable: {error}</p>
      ) : !available ? (
        <p className="telemetry-empty">
          Build this session’s local comparison with the documented telemetry command.
        </p>
      ) : !comparison ? (
        <p className="telemetry-empty">
          The comparison artifact is not available from the replay service.
        </p>
      ) : (
        <>
          <div className="telemetry-chart-wrap">
            <svg
              className="telemetry-chart"
              viewBox="0 0 1020 354"
              role="img"
              aria-label={`Speed and B minus A time across estimated distance. ${comparison.lap_a.lap_duration_seconds.toFixed(3)} second reference lap.`}
            >
              <rect x="0" y="0" width="1020" height="354" fill="#151c21" />
              {Array.from({ length: Math.floor(speedMax / 100) + 1 }, (_, index) => index * 100).map((speed) => {
                const y = speedY(speed)
                return (
                  <g key={`speed-${speed}`}>
                    <line x1={PLOT.left} x2={PLOT.right} y1={y} y2={y} className="telemetry-grid-line" />
                    <text x={PLOT.left - 12} y={y + 4} textAnchor="end" className="telemetry-axis-label">{speed}</text>
                  </g>
                )
              })}
              {[plotDeltaMin, 0, plotDeltaMax].map((delta) => {
                const y = deltaY(delta)
                return (
                  <g key={`delta-${delta}`}>
                    <line x1={PLOT.left} x2={PLOT.right} y1={y} y2={y} className="telemetry-grid-line" />
                    <text x={PLOT.left - 12} y={y + 4} textAnchor="end" className="telemetry-axis-label">{delta.toFixed(2)}</text>
                  </g>
                )
              })}
              {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
                const distance = distanceEnd * fraction
                const position = x(distance)
                return (
                  <g key={`distance-${fraction}`}>
                    <line x1={position} x2={position} y1={PLOT.speedTop} y2={PLOT.deltaBottom} className="telemetry-grid-line telemetry-grid-vertical" />
                    <text x={position} y="316" textAnchor="middle" className="telemetry-axis-label">
                      {Math.round(distance)}
                    </text>
                  </g>
                )
              })}
              <text x="10" y="105" className="telemetry-axis-title">KM/H</text>
              <text x="10" y="258" className="telemetry-axis-title">B − A (S)</text>
              <text x={(PLOT.left + PLOT.right) / 2} y="346" textAnchor="middle" className="telemetry-axis-title">ESTIMATED DISTANCE FROM LAP START (M)</text>
              <path d={speedAPath} className="telemetry-line telemetry-line-a" />
              <path d={speedBPath} className="telemetry-line telemetry-line-b" />
              <path d={deltaPath} className="telemetry-line telemetry-line-delta" />
              {cursorX != null && (
                <line
                  x1={cursorX}
                  x2={cursorX}
                  y1={PLOT.speedTop}
                  y2={PLOT.deltaBottom}
                  className="telemetry-cursor"
                  data-testid="telemetry-cursor"
                />
              )}
            </svg>
            <div className="telemetry-legend" aria-hidden="true">
              <span><i className="telemetry-key key-a" />#{comparison.lap_a.driver_number} speed</span>
              <span><i className="telemetry-key key-b" />#{comparison.lap_b.driver_number} speed</span>
              <span><i className="telemetry-key key-delta" />B − A cumulative time</span>
            </div>
          </div>
          <div className="telemetry-readout" aria-live="polite">
            {cursor ? (
              <>
                <div>
                  <span>CANONICAL REPLAY CURSOR</span>
                  <strong>{cursor.distance_m.toFixed(0)} m</strong>
                </div>
                <div>
                  <span>B − A AT THIS DISTANCE</span>
                  <strong>{formatSeconds(cursor.delta_time_b_minus_a_seconds)}</strong>
                </div>
                <div>
                  <span>SPEED · #{comparison.lap_a.driver_number} / #{comparison.lap_b.driver_number}</span>
                  <strong>{cursor.speed_a_kmh.toFixed(0)} / {cursor.speed_b_kmh.toFixed(0)} km/h</strong>
                </div>
              </>
            ) : (
              <div className="telemetry-outside">
                <span>CANONICAL SESSION TIME IS OUTSIDE THE REFERENCE LAP</span>
                <strong>
                  {lapStart != null
                    ? `Lap #${comparison.lap_a.driver_number} L${comparison.lap_a.lap_number} starts at ${lapStart.toFixed(3)} s`
                    : 'Reference lap start time is unavailable'}
                </strong>
              </div>
            )}
            {!cursor && lapStart != null && (
              <Button variant="outline" size="sm" onClick={() => onSeek(lapStart)}>
                Jump to reference lap
              </Button>
            )}
          </div>
          <div className="panel-note">
            Cursor follows the canonical replay clock. Distance is integrated from sampled speed; lap start timing and track distance are estimated.
          </div>
        </>
      )}
    </section>
  )
}
