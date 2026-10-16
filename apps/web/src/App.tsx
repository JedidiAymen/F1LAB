import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, CircleAlert, FlagTriangleRight, MapPin, Pause, Play, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import './App.css'

type Driver = { driver_id: string; number: number; acronym: string; name: string; team: string; team_color: string }
type DriverState = {
  position: number | null; lap: number | null; last_lap_seconds: number | null; gap_to_leader_text: string | null
  interval_ahead_text: string | null; tyre_compound: string | null; pit_count: number; track_x: number | null
  track_y: number | null; location_quality: 'measured' | 'estimated' | null; retired: boolean
}
type RaceState = { session_time_seconds: number; flag: string | null; drivers: Record<string, DriverState> }
type ControlEvent = { event_id: string; session_time_seconds: number; payload: { category: string; message: string; flag: string | null; scope: string | null } }
type Manifest = {
  session_name: string; duration_seconds: number; clock_origin_utc: string; provider: string
  drivers: Driver[]; geometry: { centerline_xy: number[][]; quality: string; source: string }
  race_control: ControlEvent[]; coverage: Record<string, unknown>
}

const base = '/api/v1/replay/monza-2025'
const secondsLabel = (value: number) => {
  const n = Math.floor(value)
  return `${String(Math.floor(n / 3600)).padStart(2, '0')}:${String(Math.floor(n % 3600 / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`
}
const lapLabel = (value: number | null) => value == null ? '—' : `${Math.floor(value / 60)}:${(value % 60).toFixed(3).padStart(6, '0')}`
const safeColor = (value: string) => /^#[\da-fA-F]{6}$/.test(`#${value}`) ? `#${value}` : '#97a0a9'

function TrackMap({ manifest, state, selectedId, onSelect }: {
  manifest: Manifest; state: RaceState | null; selectedId: string | null; onSelect: (id: string) => void
}) {
  const points = manifest.geometry.centerline_xy
  const bounds = useMemo(() => {
    const xs = points.map(p => p[0]); const ys = points.map(p => p[1])
    return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) }
  }, [points])
  const spanX = Math.max(1, bounds.maxX - bounds.minX)
  const spanY = Math.max(1, bounds.maxY - bounds.minY)
  const scale = Math.min(820 / spanX, 450 / spanY)
  const offsetX = (900 - spanX * scale) / 2
  const offsetY = (530 - spanY * scale) / 2
  const project = (x: number, y: number) => [offsetX + (x - bounds.minX) * scale, 530 - offsetY - (y - bounds.minY) * scale]
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${project(p[0], p[1]).join(' ')}`).join(' ')
  const visible = manifest.drivers.filter(d => state?.drivers[d.driver_id]?.track_x != null && state.drivers[d.driver_id]?.track_y != null)
  const selected = manifest.drivers.find(d => d.driver_id === selectedId)
  const selectedState = selectedId ? state?.drivers[selectedId] : null
  return <section className="track-panel panel" aria-label="Circuit position map">
    <div className="panel-heading"><div><span className="eyebrow">TRACK POSITION</span><h2>Autodromo Nazionale Monza</h2></div><span className="panel-tag"><MapPin size={12} /> 2D · APPROXIMATE</span></div>
    <div className="track-wrap">
      <svg className="track-svg" viewBox="0 0 900 530" role="img" aria-label={`Provider-derived circuit trace with ${visible.length} cars located at the current replay time`}>
        <defs><pattern id="map-grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M 36 0 L 0 0 0 36" fill="none" stroke="#263039" strokeWidth=".6" /></pattern></defs>
        <rect width="900" height="530" fill="url(#map-grid)" />
        <path d={path} fill="none" stroke="#313b43" strokeWidth="17" strokeLinecap="round" strokeLinejoin="round" />
        <path d={path} fill="none" stroke="#79858e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {visible.map(d => {
          const s = state!.drivers[d.driver_id]; const [x, y] = project(s.track_x!, s.track_y!); const active = selectedId === d.driver_id
          return <g key={d.driver_id} onClick={() => onSelect(d.driver_id)} className="map-car" role="button" tabIndex={0} aria-label={`Select ${d.name}`} onKeyDown={e => { if (e.key === 'Enter') onSelect(d.driver_id) }}>
            {active && <circle cx={x} cy={y} r="18" fill="none" stroke={safeColor(d.team_color)} strokeWidth="1" opacity=".7" />}
            <circle cx={x} cy={y} r={active ? 10 : 6} fill={safeColor(d.team_color)} stroke="#10161a" strokeWidth="2" />
            {active && <text x={x + 16} y={y + 4} fill="#f2f5f7" fontSize="13" fontWeight="700">{d.acronym}</text>}
          </g>
        })}
      </svg>
      <div className="map-index"><span className="index-line" /> N<br /><span className="map-index-small">PROVIDER XY · UNKNOWN UNIT</span></div>
      <div className="map-count">{visible.length} / {manifest.drivers.length} CARS LOCATED</div>
    </div>
    <div className="track-footer"><div><span className="dot measured" /> Provider point <span className="dot estimated" /> Interpolated position</div><div>{selected ? `${selected.acronym} · ${selectedState?.location_quality ?? 'NO LOCATION'}` : 'SELECT A DRIVER'}</div></div>
  </section>
}

function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [state, setState] = useState<RaceState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const clock = useRef(0)
  const lastFrame = useRef<number | null>(null)
  const requestId = useRef(0)

  useEffect(() => {
    fetch(`${base}/manifest`).then(async response => { if (!response.ok) throw new Error((await response.json()).detail ?? 'Manifest unavailable'); return response.json() })
      .then((data: Manifest) => { setManifest(data); setSelectedId(data.drivers[0]?.driver_id ?? null) }).catch(e => setError(String(e)))
  }, [])

  const seek = useCallback((seconds: number) => {
    const next = Math.max(0, Math.min(manifest?.duration_seconds ?? 0, seconds))
    clock.current = next; setTime(next)
  }, [manifest?.duration_seconds])

  useEffect(() => {
    if (!playing || !manifest) return
    let frame: number
    const tick = (now: number) => {
      if (lastFrame.current != null) {
        const next = Math.min(manifest.duration_seconds, clock.current + (now - lastFrame.current) / 1000 * speed)
        clock.current = next; setTime(next)
        if (next >= manifest.duration_seconds) { setPlaying(false); lastFrame.current = null; return }
      }
      lastFrame.current = now
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(frame); lastFrame.current = null }
  }, [playing, speed, manifest])

  const requestTime = manifest && time >= manifest.duration_seconds
    ? manifest.duration_seconds : Math.floor(time * 5) / 5
  useEffect(() => {
    if (!manifest) return
    const controller = new AbortController()
    const id = ++requestId.current
    fetch(`${base}/state?seconds=${requestTime.toFixed(3)}`, { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error((await response.json()).detail ?? 'State unavailable'); return response.json() })
      .then((data: RaceState) => { if (id === requestId.current) { setState(data); setError(null) } })
      .catch(e => { if (e.name !== 'AbortError' && id === requestId.current) setError(String(e)) })
    return () => controller.abort()
  }, [manifest, requestTime])

  const ranked = useMemo(() => manifest?.drivers.slice().sort((a, b) => {
    const left = state?.drivers[a.driver_id]?.position ?? 999
    const right = state?.drivers[b.driver_id]?.position ?? 999
    return left - right || a.number - b.number
  }) ?? [], [manifest, state])
  const current = selectedId ? state?.drivers[selectedId] : null
  const selected = manifest?.drivers.find(d => d.driver_id === selectedId)
  const messages = manifest?.race_control.filter(e => e.session_time_seconds <= (state?.session_time_seconds ?? 0)).slice(-12).reverse() ?? []
  const currentLap = Math.max(0, ...Object.values(state?.drivers ?? {}).map(d => d.lap ?? 0))

  return <div className="workstation">
    <header className="topbar">
      <div className="brand"><div className="brand-mark">F<span>1</span></div><div className="brand-name">LAB <span>/ RACE INTELLIGENCE</span></div></div>
      <div className="session-id"><span className="live-square" /> HISTORICAL REPLAY <span className="top-sep">/</span> 2025 ITALIAN GRAND PRIX</div>
      <div className="top-right"><span>OPENF1 · PUBLIC HISTORICAL</span><span className="top-sep">/</span><span>LOCAL PACK</span></div>
    </header>
    <main>
      <div className="race-heading"><div><div className="eyebrow">ROUND 16 <span className="heading-rule" /> RACE CONTROL</div><h1>Monza <span>2025</span></h1><p>One race. One clock. Every observation in context.</p></div><div className="race-facts"><div><span>SESSION CLOCK</span><strong>{secondsLabel(time)}</strong></div><div><span>LEADER LAP</span><strong>{currentLap || '—'} <small>/ 53</small></strong></div><div><span>STATUS</span><strong className="status-value">{state?.flag?.toUpperCase() ?? 'UNCONFIRMED'}</strong></div></div></div>
      {error && <div className="error-banner" role="alert"><CircleAlert size={17} /><span>{error}. Start the local API and build the Monza replay pack; see docs/REPLAY_2025_MONZA.md.</span></div>}
      {!manifest ? <div className="loading">{error ? 'REPLAY UNAVAILABLE' : 'LOADING LOCAL REPLAY…'}</div> : <>
        <div className="workspace-grid">
          <section className="timing-panel panel"><div className="panel-heading"><div><span className="eyebrow">CLASSIFICATION</span><h2>Timing tower</h2></div><span className="panel-tag">{ranked.length} DRIVERS</span></div><div className="timing-head"><span>POS</span><span>DRIVER</span><span>GAP</span><span>TYRE</span></div><div className="timing-list">{ranked.map(driver => { const s = state?.drivers[driver.driver_id]; const active = selectedId === driver.driver_id; return <button key={driver.driver_id} type="button" onClick={() => setSelectedId(driver.driver_id)} className={`timing-row${active ? ' active' : ''}`} style={{ '--driver-color': safeColor(driver.team_color) } as React.CSSProperties}><span className="pos">{s?.position ?? '—'}</span><span className="driver-cell"><b>{driver.acronym}</b><small>{driver.team}</small></span><span className="gap">{s?.position === 1 ? 'LEADER' : s?.gap_to_leader_text ?? '—'}</span><span className={`tyre ${s?.tyre_compound?.toLowerCase() ?? ''}`}>{s?.tyre_compound?.[0] ?? '—'}</span></button> })}</div><div className="panel-note">Position: latest provider observation · gaps may expire</div></section>
          <TrackMap manifest={manifest} state={state} selectedId={selectedId} onSelect={setSelectedId} />
          <aside className="right-column"><section className="driver-panel panel"><div className="panel-heading"><div><span className="eyebrow">FOCUS DRIVER</span><h2>{selected?.name ?? 'Select a driver'}</h2></div><span className="car-number">{selected?.number ?? '—'}</span></div><div className="driver-team" style={{ borderColor: safeColor(selected?.team_color ?? '') }}>{selected?.team ?? '—'}</div><div className="driver-metrics"><div><span>POSITION</span><strong>{current?.position ?? '—'}</strong></div><div><span>CURRENT LAP</span><strong>{current?.lap ?? '—'}</strong></div><div><span>LAST LAP</span><strong>{lapLabel(current?.last_lap_seconds ?? null)}</strong></div><div><span>PIT STOPS</span><strong>{current?.pit_count ?? '—'}</strong></div></div><div className="driver-foot">LOCATION <b>{current?.location_quality?.toUpperCase() ?? 'UNAVAILABLE'}</b> <span>·</span> INTERVAL <b>{current?.interval_ahead_text ?? '—'}</b></div></section>
          <section className="control-panel panel"><div className="panel-heading"><div><span className="eyebrow">OFFICIAL FEED</span><h2>Race control</h2></div><FlagTriangleRight size={16} /></div><div className="control-list">{messages.length ? messages.map(e => <button type="button" key={e.event_id} className="control-row" onClick={() => { seek(e.session_time_seconds); setPlaying(false) }}><time>{secondsLabel(e.session_time_seconds)}</time><div><span>{e.payload.category || 'MESSAGE'}{e.payload.flag ? ` · ${e.payload.flag}` : ''}</span><p>{e.payload.message}</p></div></button>) : <p className="no-messages">No control messages at this session time.</p>}</div><div className="panel-note">Click a message to seek to its provider time</div></section></aside>
        </div>
        <section className="transport panel" aria-label="Replay transport"><div className="transport-main"><div className="transport-title"><span className="eyebrow">REPLAY TRANSPORT</span><strong>{secondsLabel(time)} <span>/ {secondsLabel(manifest.duration_seconds)}</span></strong></div><div className="transport-controls"><Button variant="ghost" size="icon" aria-label="Back 10 seconds" onClick={() => seek(time - 10)}><ChevronLeft /></Button><Button className="play-button" size="icon-lg" aria-label={playing ? 'Pause replay' : 'Play replay'} onClick={() => setPlaying(!playing)}>{playing ? <Pause fill="currentColor" /> : <Play fill="currentColor" />}</Button><Button variant="ghost" size="icon" aria-label="Forward 10 seconds" onClick={() => seek(time + 10)}><ChevronRight /></Button><Button variant="ghost" size="icon" aria-label="Restart replay" onClick={() => { seek(0); setPlaying(false) }}><RotateCcw /></Button></div><div className="speed-controls" aria-label="Playback speed">{[1, 2, 4].map(value => <button type="button" key={value} className={speed === value ? 'selected' : ''} onClick={() => setSpeed(value)}>{value}×</button>)}</div></div><div className="scrubber"><Slider aria-label="Session time" min={0} max={manifest.duration_seconds} step={0.1} value={[time]} onValueChange={value => seek(Array.isArray(value) ? value[0] : value)} /><div className="scrub-labels"><span>LIGHTS OUT</span><span>FINISH</span></div></div></section>
        <footer className="source-footer"><span><span className="dot measured" /> CANONICAL RACESTATE {state && Math.abs(state.session_time_seconds - requestTime) < .21 ? '· SYNCED' : '· UPDATING'}</span><span>{manifest.geometry.source} · approximate coordinates, unknown unit · missing samples hidden</span><span>OPENF1 HISTORICAL DATA</span></footer>
      </>}
    </main>
  </div>
}

export default App
