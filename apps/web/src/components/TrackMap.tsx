import { memo, useLayoutEffect, useMemo, useRef } from 'react'
import { MapPin } from 'lucide-react'
import {
  headingScreenDegrees,
  projectCircuit,
  projectTrail,
  type CircuitGeometry,
  type CircuitProjection,
  type LocationContext,
} from '@/lib/circuit-geometry'

type MapDriver = { driver_id: string; acronym: string; name: string; team_color: string }
type MapState = {
  session_time_seconds: number
  drivers: Record<string, {
    track_x: number | null
    track_y: number | null
    location_quality: 'measured' | 'estimated' | null
  }>
  location_context?: LocationContext | null
}

const safeColor = (value: string) =>
  /^#[\da-fA-F]{6}$/.test(`#${value}`) ? `#${value}` : '#97a0a9'

// Projection/path construction and these static nodes do not repeat at 5 Hz.
const CircuitTrace = memo(function CircuitTrace({ projection }: { projection: CircuitProjection }) {
  return <>
    <path d={projection.path} fill="none" stroke="#313b43" strokeWidth="17" strokeLinecap="round" strokeLinejoin="round" />
    <path d={projection.path} fill="none" stroke="#79858e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    {projection.lapOrigin && <g transform={`translate(${projection.lapOrigin.join(' ')})`} className="trace-origin">
      <title>Estimated source-lap trace origin; not the official timing line</title>
      <circle r="5" fill="#d1d8dd" stroke="#10161a" strokeWidth="2" />
      <circle r="11" fill="none" stroke="#d1d8dd" strokeWidth="1" strokeDasharray="2 3" />
    </g>}
  </>
})

export function TrackMap({ manifest, state, playing, selectedId, onSelect }: {
  manifest: { circuit_name: string; drivers: MapDriver[]; geometry: CircuitGeometry }
  state: MapState | null
  playing: boolean
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const projection = useMemo(() => projectCircuit(manifest.geometry), [manifest.geometry])
  const sampleSeconds = state?.session_time_seconds ?? null
  const previousSeconds = useRef<number | null>(null)
  const mapSvgRef = useRef<SVGSVGElement | null>(null)
  useLayoutEffect(() => {
    const previous = previousSeconds.current
    const animate = playing && previous !== null && sampleSeconds !== null
      && sampleSeconds > previous && sampleSeconds - previous <= 4
    mapSvgRef.current?.querySelectorAll<SVGGElement>('.map-car').forEach((car) => {
      if (animate) car.style.removeProperty('transition')
      else car.style.transition = 'none'
    })
    previousSeconds.current = sampleSeconds
  }, [playing, sampleSeconds])

  const visible = manifest.drivers.filter((driver) =>
    state?.drivers[driver.driver_id]?.track_x != null && state.drivers[driver.driver_id]?.track_y != null)
  const selected = manifest.drivers.find((driver) => driver.driver_id === selectedId)
  const selectedState = selectedId ? state?.drivers[selectedId] : null
  const returnedContext = state?.location_context
  const context = returnedContext && returnedContext.driver_id === selectedId
    && returnedContext.session_time_seconds === sampleSeconds ? returnedContext : null
  const trail = useMemo(() => context && projection ? projectTrail(context, projection) : [], [context, projection])
  const heading = context?.location_available ? headingScreenDegrees(context.heading_radians) : null
  const latestTrailTime = context?.segments.flat().at(-1)?.session_time_seconds
  const geometry = manifest.geometry

  return (
    <section className="track-panel panel" aria-label="Circuit position map" data-session-time={state?.session_time_seconds}
      data-geometry-id={geometry.geometry_id ?? 'legacy-trace'}>
      <div className="panel-heading">
        <div><span className="eyebrow">TRACK POSITION</span><h2>{manifest.circuit_name}</h2></div>
        <span className="panel-tag" title={geometry.source}><MapPin size={12} /> 2D · APPROXIMATE</span>
      </div>
      <div className="track-wrap">
        {!projection && <div className="map-unavailable">Circuit trace is unavailable or invalid.</div>}
        <svg ref={mapSvgRef} className="track-svg" viewBox="0 0 900 530" role="img"
          aria-label={`Provider-derived circuit trace with ${visible.length} cars located at the current replay time`}>
          <defs><pattern id="map-grid" width="36" height="36" patternUnits="userSpaceOnUse">
            <path d="M 36 0 L 0 0 0 36" fill="none" stroke="#263039" strokeWidth=".6" />
          </pattern></defs>
          <rect width="900" height="530" fill="url(#map-grid)" />
          {projection && <CircuitTrace projection={projection} />}
          {projection && context && <g data-testid="selected-trail" data-driver-id={context.driver_id}
            data-session-time={context.session_time_seconds} data-latest-sample-time={latestTrailTime}
            fill="none" stroke={safeColor(selected?.team_color ?? '')} strokeWidth="3" strokeLinecap="round" opacity=".8">
            <title>Last {context.window_seconds} seconds of source locations; gaps are disconnected and estimated endpoints dashed</title>
            {trail.map((line, index) => <path key={index} d={line.path} strokeDasharray={line.estimated ? '4 4' : undefined} />)}
          </g>}
          {projection && visible.map((driver) => {
            const current = state!.drivers[driver.driver_id]
            const [x, y] = projection.project(current.track_x!, current.track_y!)
            const active = selectedId === driver.driver_id
            return <g key={driver.driver_id} className="map-car" style={{ transform: `translate(${x}px, ${y}px)` }}
              onClick={() => onSelect(driver.driver_id)} role="button" tabIndex={0}
              aria-label={`Select ${driver.name}`}
              onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(driver.driver_id) } }}>
              {active && <circle r="18" fill="none" stroke={safeColor(driver.team_color)} strokeWidth="1" opacity=".7" />}
              <circle r={active ? 10 : 6} fill={safeColor(driver.team_color)}
                fillOpacity={current.location_quality === 'estimated' ? .7 : 1}
                stroke={current.location_quality === 'estimated' ? '#efc681' : '#10161a'}
                strokeWidth={current.location_quality === 'estimated' ? 1 : 2} />
              {active && heading !== null && <path data-testid="selected-heading" data-heading-radians={context?.heading_radians}
                d="M 11 -4 L 20 0 L 11 4 Z" fill={safeColor(driver.team_color)} transform={`rotate(${heading})`}>
                <title>Estimated direction of recent displacement, not measured chassis orientation</title>
              </path>}
              {active && <text x="23" y="4" fill="#f2f5f7" fontSize="13" fontWeight="700">{driver.acronym}</text>}
            </g>
          })}
        </svg>
        <div className="map-index"><span className="index-line" /> XY<br />
          <span className="map-index-small">PROVIDER XY · UNKNOWN UNIT</span></div>
        <div className="map-count">{visible.length} / {manifest.drivers.length} CARS LOCATED</div>
        <div className="map-geometry-note" title={geometry.source}>
          DRIVING-LINE TRACE · PIT LANE UNAVAILABLE
          {geometry.diagnostics && <span>{geometry.diagnostics.retained_source_points} SOURCE POINTS · VALIDATED CLOSURE</span>}
        </div>
      </div>
      <div className="track-footer">
        <div><span className="dot measured" /> Provider point{' '}<span className="dot estimated" /> Interpolated position</div>
        <div>{selected ? `${selected.acronym} · ${selectedState?.location_quality ?? 'NO LOCATION'} · 12 s TRAIL` : 'SELECT A DRIVER'}</div>
      </div>
    </section>
  )
}
