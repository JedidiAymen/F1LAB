import { Cloud } from 'lucide-react'
import { formatSessionTime, weatherAt, type WeatherObservation, type WeatherChange } from '@/lib/session-context'
import { Button } from '@/components/ui/button'

const reading = (value: number | null | undefined, suffix: string, decimals = 1) =>
  value == null ? '—' : `${value.toFixed(decimals)}${suffix}`

export function WeatherPanel({
  seconds,
  observation,
  available,
  changes,
  onSeek,
}: {
  seconds: number
  observation: WeatherObservation | null
  available: boolean
  changes: WeatherChange[]
  onSeek: (seconds: number) => void
}) {
  const { age, fresh, values } = weatherAt(seconds, observation)
  const status = !available
    ? 'Unavailable in this pack'
    : !observation
      ? 'Waiting for first observation'
      : !fresh
        ? 'Last reading is stale'
        : `${observation.quality} · ${Math.floor(age!)}s old`
  const currentChange = changes.filter((change) => change.session_time_seconds <= seconds).at(-1)
  return (
    <section
      className="weather-panel panel"
      aria-label="Weather observations"
      data-session-time={seconds}
      data-fresh={fresh}
      data-observed-time={observation?.session_time_seconds}
    >
      <div className="weather-heading">
        <Cloud size={16} aria-hidden="true" />
        <div>
          <h2>Weather observations</h2>
          <p data-testid="weather-quality">{status}</p>
          {observation && <small>Observed {formatSessionTime(observation.session_time_seconds)}</small>}
        </div>
      </div>
      <dl className="weather-readings">
        <div>
          <dt>Air</dt>
          <dd>{reading(values?.air_temperature_c, '°C')}</dd>
        </div>
        <div>
          <dt>Track</dt>
          <dd>{reading(values?.track_temperature_c, '°C')}</dd>
        </div>
        <div>
          <dt>Rainfall</dt>
          <dd data-testid="rainfall">
            {values?.rainfall == null ? '—' : values.rainfall ? 'Rain reported' : 'No rain reported'}
          </dd>
        </div>
        <div>
          <dt>Wind</dt>
          <dd>
            {reading(values?.wind_speed_mps, ' m/s')} <small>{reading(values?.wind_direction_degrees, '°', 0)}</small>
          </dd>
        </div>
        <div>
          <dt>Humidity</dt>
          <dd>{reading(values?.humidity_percent, '%', 0)}</dd>
        </div>
        <div>
          <dt>Pressure</dt>
          <dd>{reading(values?.pressure_mbar, ' mbar')}</dd>
        </div>
      </dl>
      {changes.length > 0 && (
        <div className="weather-changes" aria-label="Reported rainfall changes">
          <span>Rain reports</span>
          {changes.map((change) => (
            <Button
              key={change.event_id}
              size="xs"
              variant={currentChange?.event_id === change.event_id ? 'secondary' : 'ghost'}
              onClick={() => onSeek(change.session_time_seconds)}
              aria-label={`${change.rainfall ? 'Rain reported' : 'No rain reported'} at ${formatSessionTime(change.session_time_seconds)}`}
            >
              {formatSessionTime(change.session_time_seconds)} {change.rainfall ? 'RAIN' : 'NO RAIN'}
            </Button>
          ))}
        </div>
      )}
    </section>
  )
}
