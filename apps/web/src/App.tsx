import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  FlagTriangleRight,
  MapPin,
  Pause,
  Play,
  RotateCcw,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PlaybackClock } from '@/lib/playback-clock'
import { WeatherPanel } from '@/components/WeatherPanel'
import { StintPanel } from '@/components/StintPanel'
import {
  formatSessionTime as secondsLabel,
  trackStatusLabels,
  type TrackStatusObservation,
  type WeatherObservation,
  type WeatherChange,
  type TyreStint,
} from '@/lib/session-context'
import './App.css'

type Driver = {
  driver_id: string
  number: number
  acronym: string
  name: string
  team: string
  team_color: string
}
type DriverState = {
  position: number | null
  lap: number | null
  last_lap_seconds: number | null
  gap_to_leader_text: string | null
  gap_to_leader_seconds: number | null
  interval_ahead_seconds: number | null
  interval_ahead_text: string | null
  tyre_compound: string | null
  tyre_age_laps: number | null
  tyre_stints: TyreStint[]
  pit_count: number
  track_x: number | null
  track_y: number | null
  location_quality: 'measured' | 'estimated' | null
  retired: boolean
}
type RaceState = {
  session_time_seconds: number
  flag: string | null
  track_status: TrackStatusObservation | null
  weather: WeatherObservation | null
  drivers: Record<string, DriverState>
}
type ControlEvent = {
  event_id: string
  session_time_seconds: number
  payload: {
    category: string
    message: string
    flag: string | null
    scope: string | null
  }
}
type Manifest = {
  slug: string
  session: { season: number; round: number; provider_key: string }
  session_name: string
  duration_seconds: number
  clock_origin_utc: string
  provider: string
  circuit_name: string
  scheduled_laps: number
  capabilities: string[]
  drivers: Driver[]
  geometry: { centerline_xy: number[][]; quality: string; source: string }
  race_control: ControlEvent[]
  weather_changes: WeatherChange[]
  coverage: Record<string, unknown>
}

type CatalogEntry = {
  slug: string
  season: number
  round: number
  title: string
  display_name: string
  circuit: string
  available: boolean
}
const lapLabel = (value: number | null) =>
  value == null
    ? '—'
    : `${Math.floor(value / 60)}:${(value % 60).toFixed(3).padStart(6, '0')}`
const gapLabel = (seconds?: number | null, text?: string | null) =>
  text ?? (seconds == null ? '—' : `+${seconds.toFixed(3)}`)
const safeColor = (value: string) =>
  /^#[\da-fA-F]{6}$/.test(`#${value}`) ? `#${value}` : '#97a0a9'

function TrackMap({
  manifest,
  state,
  playing,
  selectedId,
  onSelect,
}: {
  manifest: Manifest
  state: RaceState | null
  playing: boolean
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const points = manifest.geometry.centerline_xy
  const sampleSeconds = state?.session_time_seconds ?? null
  const previousSeconds = useRef<number | null>(null)
  const mapSvgRef = useRef<SVGSVGElement | null>(null)
  useLayoutEffect(() => {
    const previous = previousSeconds.current
    const animate =
      playing &&
      previous !== null &&
      sampleSeconds !== null &&
      sampleSeconds > previous &&
      sampleSeconds - previous <= 4
    mapSvgRef.current?.querySelectorAll<SVGGElement>('.map-car').forEach((car) => {
      if (animate) car.style.removeProperty('transition')
      else car.style.transition = 'none'
    })
    previousSeconds.current = sampleSeconds
  }, [playing, sampleSeconds])
  const bounds = useMemo(() => {
    const xs = points.map((p) => p[0])
    const ys = points.map((p) => p[1])
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    }
  }, [points])
  const spanX = Math.max(1, bounds.maxX - bounds.minX)
  const spanY = Math.max(1, bounds.maxY - bounds.minY)
  const scale = Math.min(820 / spanX, 450 / spanY)
  const offsetX = (900 - spanX * scale) / 2
  const offsetY = (530 - spanY * scale) / 2
  const project = (x: number, y: number) => [
    offsetX + (x - bounds.minX) * scale,
    530 - offsetY - (y - bounds.minY) * scale,
  ]
  const path = points
    .map((p, i) => `${i ? 'L' : 'M'}${project(p[0], p[1]).join(' ')}`)
    .join(' ')
  const visible = manifest.drivers.filter(
    (d) =>
      state?.drivers[d.driver_id]?.track_x != null &&
      state.drivers[d.driver_id]?.track_y != null,
  )
  const selected = manifest.drivers.find((d) => d.driver_id === selectedId)
  const selectedState = selectedId ? state?.drivers[selectedId] : null
  return (
    <section
      className="track-panel panel"
      aria-label="Circuit position map"
      data-session-time={state?.session_time_seconds}
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">TRACK POSITION</span>
          <h2>{manifest.circuit_name}</h2>
        </div>
        <span className="panel-tag">
          <MapPin size={12} /> 2D · APPROXIMATE
        </span>
      </div>
      <div className="track-wrap">
        <svg
          ref={mapSvgRef}
          className="track-svg"
          viewBox="0 0 900 530"
          role="img"
          aria-label={`Provider-derived circuit trace with ${visible.length} cars located at the current replay time`}
        >
          <defs>
            <pattern
              id="map-grid"
              width="36"
              height="36"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 36 0 L 0 0 0 36"
                fill="none"
                stroke="#263039"
                strokeWidth=".6"
              />
            </pattern>
          </defs>
          <rect width="900" height="530" fill="url(#map-grid)" />
          <path
            d={path}
            fill="none"
            stroke="#313b43"
            strokeWidth="17"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d={path}
            fill="none"
            stroke="#79858e"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {visible.map((d) => {
            const s = state!.drivers[d.driver_id]
            const [x, y] = project(s.track_x!, s.track_y!)
            const active = selectedId === d.driver_id
            return (
              <g
                key={d.driver_id}
                onClick={() => onSelect(d.driver_id)}
                className="map-car"
                style={{
                  transform: `translate(${x}px, ${y}px)`,
                }}
                role="button"
                tabIndex={0}
                aria-label={`Select ${d.name}`}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onSelect(d.driver_id)
                }}
              >
                {active && (
                  <circle
                    cx={0}
                    cy={0}
                    r="18"
                    fill="none"
                    stroke={safeColor(d.team_color)}
                    strokeWidth="1"
                    opacity=".7"
                  />
                )}
                <circle
                  cx={0}
                  cy={0}
                  r={active ? 10 : 6}
                  fill={safeColor(d.team_color)}
                  fillOpacity={s.location_quality === 'estimated' ? 0.7 : 1}
                  stroke={
                    s.location_quality === 'estimated' ? '#efc681' : '#10161a'
                  }
                  strokeWidth={s.location_quality === 'estimated' ? 1 : 2}
                />
                {active && (
                  <text
                    x={16}
                    y={4}
                    fill="#f2f5f7"
                    fontSize="13"
                    fontWeight="700"
                  >
                    {d.acronym}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
        <div className="map-index">
          <span className="index-line" /> XY
          <br />
          <span className="map-index-small">PROVIDER XY · UNKNOWN UNIT</span>
        </div>
        <div className="map-count">
          {visible.length} / {manifest.drivers.length} CARS LOCATED
        </div>
      </div>
      <div className="track-footer">
        <div>
          <span className="dot measured" /> Provider point{' '}
          <span className="dot estimated" /> Interpolated position
        </div>
        <div>
          {selected
            ? `${selected.acronym} · ${selectedState?.location_quality ?? 'NO LOCATION'}`
            : 'SELECT A DRIVER'}
        </div>
      </div>
    </section>
  )
}

function ReplayWorkspace({
  slug,
  sessions,
  onSessionChange,
}: {
  slug: string
  sessions: CatalogEntry[]
  onSessionChange: (slug: string) => void
}) {
  const base = `/api/v1/replay/${slug}`
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [state, setState] = useState<RaceState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const clock = useRef(new PlaybackClock(0))
  const requestId = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${base}/manifest`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            (await response.json()).detail ?? 'Manifest unavailable',
          )
        return response.json()
      })
      .then((data: Manifest) => {
        clock.current = new PlaybackClock(data.duration_seconds)
        setManifest(data)
        setSelectedId(data.drivers[0]?.driver_id ?? null)
      })
      .catch((e) => {
        if (e.name !== 'AbortError') setError(String(e))
      })
    return () => controller.abort()
  }, [base])

  const seek = useCallback((seconds: number, pause = false) => {
    const now = performance.now()
    if (pause) clock.current.pause(now)
    clock.current.seek(seconds, now)
    const snapshot = clock.current.sample(now)
    setTime(snapshot.seconds)
    setPlaying(snapshot.playing)
  }, [])

  useEffect(() => {
    if (!manifest) return
    const tick = () => {
      const snapshot = clock.current.sample(performance.now())
      setTime(snapshot.seconds)
      setPlaying(snapshot.playing)
    }
    const timer = window.setInterval(tick, 200)
    const visibility = () => {
      if (document.hidden) {
        clock.current.pause(performance.now())
        tick()
      }
    }
    document.addEventListener('visibilitychange', visibility)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [manifest])

  const requestTime = time
  useEffect(() => {
    if (!manifest) return
    const controller = new AbortController()
    const id = ++requestId.current
    fetch(`${base}/state?seconds=${requestTime.toFixed(3)}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error((await response.json()).detail ?? 'State unavailable')
        return response.json()
      })
      .then((data: RaceState) => {
        if (id === requestId.current) {
          setState(data)
          setError(null)
        }
      })
      .catch((e) => {
        if (e.name !== 'AbortError' && id === requestId.current)
          setError(String(e))
      })
    return () => controller.abort()
  }, [manifest, requestTime, base])

  const togglePlayback = () => {
    const now = performance.now()
    if (playing) clock.current.pause(now)
    else clock.current.play(now)
    const snapshot = clock.current.sample(now)
    setTime(snapshot.seconds)
    setPlaying(snapshot.playing)
  }
  const changeSpeed = (value: number) => {
    clock.current.setSpeed(value, performance.now())
    setSpeed(value)
  }

  const ranked = useMemo(
    () =>
      manifest?.drivers.slice().sort((a, b) => {
        const left = state?.drivers[a.driver_id]?.position ?? 999
        const right = state?.drivers[b.driver_id]?.position ?? 999
        return left - right || a.number - b.number
      }) ?? [],
    [manifest, state],
  )
  const current = selectedId ? state?.drivers[selectedId] : null
  const selected = manifest?.drivers.find((d) => d.driver_id === selectedId)
  const messages =
    manifest?.race_control
      .filter(
        (e) => e.session_time_seconds <= (state?.session_time_seconds ?? 0),
      )
      .reverse() ?? []
  const currentLap = Math.max(
    0,
    ...Object.values(state?.drivers ?? {}).map((d) => d.lap ?? 0),
  )
  const raceStart = manifest?.race_control.find(
    (event) => event.payload.message === 'SESSION STARTED',
  )?.session_time_seconds

  return (
    <div className="workstation">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            F<span>1</span>
          </div>
          <div className="brand-name">
            LAB <span>/ RACE INTELLIGENCE</span>
          </div>
        </div>
        <div className="session-id">
          <span className="live-square" />
          <span className="session-mode">HISTORICAL REPLAY</span>
          <Select
            items={sessions.map((s) => ({ value: s.slug, label: s.title }))}
            value={slug}
            onValueChange={(value) => {
              if (value) onSessionChange(value)
            }}
          >
            <SelectTrigger aria-label="Historical session">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {sessions.map((s) => (
                  <SelectItem
                    key={s.slug}
                    value={s.slug}
                    disabled={!s.available}
                  >
                    {s.title}
                    {s.available ? '' : ' · pack unavailable'}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
        <div className="top-right">
          <span>OPENF1 · PUBLIC HISTORICAL</span>
          <span className="top-sep">/</span>
          <span>LOCAL PACK</span>
        </div>
      </header>
      <main data-replay-session={slug}>
        <div className="race-heading">
          <div>
            <div className="eyebrow">
              ROUND {manifest?.session.round ?? '—'}{' '}
              <span className="heading-rule" /> RACE CONTROL
            </div>
            <h1>
              {sessions.find((s) => s.slug === slug)?.display_name ?? slug}{' '}
              <span>{manifest?.session.season ?? ''}</span>
            </h1>
            <p>
              Historical race replay · source timing and approximate positions
              {raceStart != null && time < raceStart && (
                <Button
                  variant="link"
                  size="xs"
                  onClick={() => seek(raceStart, true)}
                >
                  Jump to race start
                </Button>
              )}
            </p>
          </div>
          <div
            className="race-facts"
            role="region"
            aria-label="Session summary"
            data-session-time={state?.session_time_seconds}
          >
            <div>
              <span>SESSION CLOCK</span>
              <strong
                data-testid="state-clock"
                data-seconds={state?.session_time_seconds ?? 0}
              >
                {secondsLabel(state?.session_time_seconds ?? 0)}
              </strong>
            </div>
            <div>
              <span>LEADER LAP</span>
              <strong>
                {currentLap || '—'}{' '}
                <small>/ {manifest?.scheduled_laps ?? '—'}</small>
              </strong>
            </div>
            <div>
              <span>LAST TRACK SIGNAL</span>
              <strong
                className="status-value"
                data-testid="track-status"
                data-status={state?.track_status?.signal.status ?? 'unconfirmed'}
                title={state?.track_status?.signal.message}
              >
                {state?.track_status
                  ? trackStatusLabels[state.track_status.signal.status]
                  : 'UNCONFIRMED'}
              </strong>
              {state?.track_status && (
                <small className="signal-time">
                  at {secondsLabel(state.track_status.session_time_seconds)}
                </small>
              )}
            </div>
          </div>
        </div>
        {error && (
          <div className="error-banner" role="alert">
            <CircleAlert size={17} />
            <span>
              {error}. Start the local replay service and build this session
              pack; see the setup guide.
            </span>
          </div>
        )}
        {manifest && !manifest.capabilities.includes('pit_stops') && (
          <div className="coverage-note" role="status">
            Pit-stop records are unavailable for this session. Tyre stints
            remain available.
          </div>
        )}
        {!manifest ? (
          <div className="loading">
            {error ? 'REPLAY UNAVAILABLE' : 'LOADING LOCAL REPLAY…'}
          </div>
        ) : (
          <>
            <WeatherPanel
              seconds={state?.session_time_seconds ?? 0}
              observation={state?.weather ?? null}
              available={manifest.capabilities.includes('weather')}
              changes={manifest.weather_changes}
              onSeek={(seconds) => seek(seconds, true)}
            />
            <div className="workspace-grid">
              <section
                className="timing-panel panel"
                aria-label="Timing tower"
                data-session-time={state?.session_time_seconds}
              >
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">CLASSIFICATION</span>
                    <h2>Timing tower</h2>
                  </div>
                  <span className="panel-tag">{ranked.length} DRIVERS</span>
                </div>
                <div className="timing-head">
                  <span>POS</span>
                  <span>DRIVER</span>
                  <span>GAP</span>
                  <span>TYRE</span>
                </div>
                <div className="timing-list">
                  {ranked.map((driver) => {
                    const s = state?.drivers[driver.driver_id]
                    const active = selectedId === driver.driver_id
                    return (
                      <button
                        key={driver.driver_id}
                        type="button"
                        onClick={() => setSelectedId(driver.driver_id)}
                        className={`timing-row${active ? ' active' : ''}`}
                        style={
                          {
                            '--driver-color': safeColor(driver.team_color),
                          } as React.CSSProperties
                        }
                      >
                        <span className="pos">{s?.position ?? '—'}</span>
                        <span className="driver-cell">
                          <b>{driver.acronym}</b>
                          <small>{driver.team}</small>
                        </span>
                        <span className="gap">
                          {s?.position === 1
                            ? 'LEADER'
                            : gapLabel(
                                s?.gap_to_leader_seconds,
                                s?.gap_to_leader_text,
                              )}
                        </span>
                        <span
                          className={`tyre ${s?.tyre_compound?.toLowerCase() ?? ''}`}
                        >
                          {s?.tyre_compound?.[0] ?? '—'}
                        </span>
                      </button>
                    )
                  })}
                </div>
                <div className="panel-note">
                  Position: latest provider observation · gaps may expire
                </div>
              </section>
              <TrackMap
                manifest={manifest}
                state={state}
                playing={playing}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
              <aside className="right-column">
                <section
                  className="driver-panel panel"
                  aria-label="Driver focus"
                  data-session-time={state?.session_time_seconds}
                >
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">FOCUS DRIVER</span>
                      <h2>{selected?.name ?? 'Select a driver'}</h2>
                    </div>
                    <span className="car-number">
                      {selected?.number ?? '—'}
                    </span>
                  </div>
                  <div
                    className="driver-team"
                    style={{
                      borderColor: safeColor(selected?.team_color ?? ''),
                    }}
                  >
                    {selected?.team ?? '—'}
                  </div>
                  <div className="driver-metrics">
                    <div>
                      <span>POSITION</span>
                      <strong>{current?.position ?? '—'}</strong>
                    </div>
                    <div>
                      <span>COMPLETED LAPS</span>
                      <strong>{current?.lap ?? '—'}</strong>
                    </div>
                    <div>
                      <span>LAST LAP</span>
                      <strong>
                        {lapLabel(current?.last_lap_seconds ?? null)}
                      </strong>
                    </div>
                    <div>
                      <span>PIT STOPS</span>
                      <strong>
                        {manifest.capabilities.includes('pit_stops')
                          ? (current?.pit_count ?? '—')
                          : 'Unavailable'}
                      </strong>
                    </div>
                  </div>
                  <div className="driver-foot">
                    LOCATION{' '}
                    <b>
                      {current?.location_quality?.toUpperCase() ??
                        'UNAVAILABLE'}
                    </b>{' '}
                    <span>·</span> INTERVAL{' '}
                    <b>
                      {gapLabel(
                        current?.interval_ahead_seconds,
                        current?.interval_ahead_text,
                      )}
                    </b>
                  </div>
                </section>
                <StintPanel
                  seconds={state?.session_time_seconds ?? 0}
                  driverName={selected?.name ?? null}
                  stints={current?.tyre_stints ?? []}
                  tyreAge={current?.tyre_age_laps ?? null}
                  scheduledLaps={manifest.scheduled_laps}
                  available={manifest.capabilities.includes('stints')}
                />
                <section
                  className="control-panel panel"
                  aria-label="Race control feed"
                  data-session-time={state?.session_time_seconds}
                >
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">SOURCE MESSAGES</span>
                      <h2>Race control</h2>
                    </div>
                    <FlagTriangleRight size={16} />
                  </div>
                  <div className="control-list">
                    {messages.length ? (
                      messages.map((e) => (
                        <button
                          type="button"
                          key={e.event_id}
                          className="control-row"
                          data-session-time={e.session_time_seconds}
                          onClick={() => seek(e.session_time_seconds, true)}
                        >
                          <time>{secondsLabel(e.session_time_seconds)}</time>
                          <div>
                            <span>
                              {e.payload.category || 'MESSAGE'}
                              {e.payload.flag ? ` · ${e.payload.flag}` : ''}
                            </span>
                            <p>{e.payload.message}</p>
                          </div>
                        </button>
                      ))
                    ) : (
                      <p className="no-messages">
                        No control messages at this session time.
                      </p>
                    )}
                  </div>
                  <div className="panel-note">
                    Click a message to seek to its provider time
                  </div>
                </section>
              </aside>
            </div>
            <section className="transport panel" aria-label="Replay transport">
              <div className="transport-main">
                <div className="transport-title">
                  <span className="eyebrow">REPLAY TRANSPORT</span>
                  <strong>
                    {secondsLabel(time)}{' '}
                    <span>/ {secondsLabel(manifest.duration_seconds)}</span>
                  </strong>
                </div>
                <div className="transport-controls">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Back 10 seconds"
                    onClick={() => seek(time - 10)}
                  >
                    <ChevronLeft />
                  </Button>
                  <Button
                    className="play-button"
                    size="icon-lg"
                    aria-label={playing ? 'Pause replay' : 'Play replay'}
                    onClick={togglePlayback}
                  >
                    {playing ? (
                      <Pause fill="currentColor" />
                    ) : (
                      <Play fill="currentColor" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Forward 10 seconds"
                    onClick={() => seek(time + 10)}
                  >
                    <ChevronRight />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Restart replay"
                    onClick={() => seek(0, true)}
                  >
                    <RotateCcw />
                  </Button>
                </div>
                <Select
                  items={[0.25, 0.5, 1, 2, 4, 8, 16].map((value) => ({
                    value,
                    label: `${value}×`,
                  }))}
                  value={speed}
                  onValueChange={(value) => {
                    if (value) changeSpeed(value)
                  }}
                >
                  <SelectTrigger
                    aria-label="Playback speed"
                    className="speed-controls"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {[0.25, 0.5, 1, 2, 4, 8, 16].map((value) => (
                        <SelectItem key={value} value={value}>
                          {value}×
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
              <div className="scrubber">
                <Slider
                  aria-label="Session time"
                  min={0}
                  max={manifest.duration_seconds}
                  step={0.1}
                  value={[time]}
                  onValueChange={(value) =>
                    seek(Array.isArray(value) ? value[0] : value)
                  }
                />
                <div className="scrub-labels">
                  <span>SCHEDULED START</span>
                  <span>PACK END</span>
                </div>
              </div>
            </section>
            <footer className="source-footer">
              <span>
                <span className="dot measured" /> REPLAY OBSERVATIONS{' '}
                {state &&
                Math.abs(state.session_time_seconds - requestTime) < 0.21
                  ? '· SYNCED'
                  : '· UPDATING'}
              </span>
              <span>
                {manifest.geometry.source} · approximate coordinates, unknown
                unit · missing samples hidden
              </span>
              <span>OPENF1 HISTORICAL DATA</span>
            </footer>
          </>
        )}
      </main>
    </div>
  )
}

function App() {
  const [sessions, setSessions] = useState<CatalogEntry[]>([])
  const [slug, setSlug] = useState('monza-2025')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/replays', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('Catalog unavailable')
        return response.json()
      })
      .then(setSessions)
      .catch(() => {})
    return () => controller.abort()
  }, [])
  return (
    <ReplayWorkspace
      key={slug}
      slug={slug}
      sessions={sessions}
      onSessionChange={setSlug}
    />
  )
}

export default App
