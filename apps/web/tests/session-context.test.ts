import assert from 'node:assert/strict'
import { test } from 'node:test'
import { weatherAt, type WeatherObservation } from '../src/lib/session-context.ts'

test('weather display accepts the exact freshness cutoff and hides stale/future readings', () => {
  const weather: WeatherObservation = {
    event_id: 'fixture',
    source: 'synthetic',
    observed_at: '2024-01-01T00:01:40Z',
    session_time_seconds: 100,
    quality: 'measured',
    max_age_seconds: 120,
    values: {
      rainfall: false,
      air_temperature_c: 0,
      track_temperature_c: null,
      pressure_mbar: 1000,
      humidity_percent: 50,
      wind_speed_mps: 0,
      wind_direction_degrees: 0,
    },
  }
  assert.equal(weatherAt(100, weather).fresh, true)
  assert.equal(weatherAt(220, weather).values?.air_temperature_c, 0)
  assert.equal(weatherAt(220.001, weather).values, null)
  assert.equal(weatherAt(99.999, weather).values, null)
  assert.equal(weatherAt(100, null).values, null)
})
