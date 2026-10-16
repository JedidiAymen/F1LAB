import { type TyreStint } from '@/lib/session-context'

function compoundClass(compound: string) {
  switch (compound.toLowerCase()) {
    case 'soft':
    case 'medium':
    case 'hard':
    case 'intermediate':
    case 'wet':
      return compound.toLowerCase()
    default:
      return 'unknown'
  }
}

function lapRange(stint: TyreStint) {
  return stint.lap_end == null
    ? `L${stint.lap_start} · in progress`
    : stint.lap_start === stint.lap_end
      ? `L${stint.lap_start}`
      : `L${stint.lap_start}–${stint.lap_end}`
}

export function StintPanel({
  seconds,
  driverName,
  stints,
  tyreAge,
  scheduledLaps,
  available,
}: {
  seconds: number
  driverName: string | null
  stints: TyreStint[]
  tyreAge: number | null
  scheduledLaps: number
  available: boolean
}) {
  const denominator = Math.max(1, scheduledLaps)
  const sharedLapBoundary = stints.some((stint, index) =>
    index > 0 && stints[index - 1].lap_end != null && stint.lap_start <= stints[index - 1].lap_end!,
  )
  return (
    <section
      className="stint-panel panel"
      aria-label="Tyre stints"
      data-session-time={seconds}
      data-driver={driverName ?? ''}
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">TYRE LIFE</span>
          <h2>{driverName ? `${driverName} · stint history` : 'Stint history'}</h2>
        </div>
        <span className="panel-tag">
          {driverName && tyreAge != null ? `AGE ${tyreAge} LAPS` : 'SOURCE DATA'}
        </span>
      </div>
      {!available ? (
        <p className="stint-empty">Stint records are unavailable in this pack.</p>
      ) : !driverName ? (
        <p className="stint-empty">Select a driver to inspect tyre history.</p>
      ) : stints.length === 0 ? (
        <p className="stint-empty">No stint observation at this replay time.</p>
      ) : (
        <div className="stint-content">
          <div
            className="stint-timeline"
            role="img"
            aria-label={stints
              .map((stint) =>
                `Stint ${stint.stint_number}, ${stint.compound}, ${lapRange(stint)}, start time ${stint.quality}`,
              )
              .join('; ')}
          >
            {stints.map((stint) => {
              const endLap = stint.lap_end ?? stint.lap_start
              const left = ((stint.lap_start - 1) / denominator) * 100
              const width = (Math.max(1, endLap - stint.lap_start + 1) / denominator) * 100
              return (
                <div className="stint-lane" key={stint.source_event_id}>
                  <span
                    className={`stint-segment ${compoundClass(stint.compound)}`}
                    style={{ left: `${left}%`, width: `${width}%` }}
                    title={`Stint ${stint.stint_number} · ${stint.compound} · ${lapRange(stint)} · start ${stint.quality}`}
                    data-quality={stint.quality}
                    data-stint-number={stint.stint_number}
                  />
                </div>
              )
            })}
          </div>
          <div className="stint-axis">
            <span>LAP 1</span>
            <span>{scheduledLaps > 0 ? `LAP ${scheduledLaps}` : 'PACK END'}</span>
          </div>
          {sharedLapBoundary && (
            <p className="stint-note">
              Mapped stint boundaries share a lap; both source records are retained.
            </p>
          )}
          <ol className="stint-list">
            {stints.map((stint) => (
              <li key={stint.source_event_id} data-stint-number={stint.stint_number}>
                <span className={`stint-swatch ${compoundClass(stint.compound)}`} />
                <b>STINT {stint.stint_number}</b>
                <span>{stint.compound}</span>
                <span>{lapRange(stint)}</span>
                <small>{stint.quality.toUpperCase()} START</small>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}
