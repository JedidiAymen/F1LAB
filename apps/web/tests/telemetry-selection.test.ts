import assert from 'node:assert/strict'
import { test } from 'node:test'
import { changeTelemetryDriver, telemetrySelectionError, telemetrySelectionQuery, type TelemetryLapLibrary } from '../src/lib/telemetry-selection.ts'

const lap = (lap_number: number) => ({ lap_number, start_utc: '2025-09-07T14:00:00Z', lap_duration_seconds: 80,
  integrated_distance_m: 5700, maximum_sample_gap_seconds: 0.8, source_sample_count: 200, pit_entry_status: 'checked_not_pit_in' as const })
const library: TelemetryLapLibrary = {
  schema_version: 1, session_slug: 'monza-2025', session_key: 9912, meeting_key: 1268, limits: [],
  drivers: [
    { driver_number: 1, name: 'Max', acronym: 'VER', available: true, laps: [lap(10), lap(11)], rejected_laps: [] },
    { driver_number: 4, name: 'Lando', acronym: 'NOR', available: true, laps: [lap(11), lap(12)], rejected_laps: [] },
    { driver_number: 16, name: 'Charles', acronym: 'LEC', available: false, laps: [], rejected_laps: [], unavailable_reason: 'No cached source' },
  ],
  default_selection: { driver_a: 1, lap_a: 10, driver_b: 4, lap_b: 11 },
}
const initial = library.default_selection!

test('selection eligibility permits one driver across different laps and rejects unavailable or identical pairs', () => {
  assert.equal(telemetrySelectionError(library, initial), null)
  assert.equal(telemetrySelectionError(library, { ...initial, driver_b: 1, lap_b: 11 }), null)
  assert.match(telemetrySelectionError(library, { ...initial, driver_b: 1, lap_b: 10 })!, /two different laps/)
  assert.match(telemetrySelectionError(library, { ...initial, driver_b: 16, lap_b: 11 })!, /validated cached/)
  assert.match(telemetrySelectionError(library, { ...initial, lap_b: 999 })!, /validated cached/)
})

test('driver changes retain eligible laps and replace unsupported laps using only that driver’s catalog', () => {
  assert.deepEqual(changeTelemetryDriver(library, initial, 'b', 1), { ...initial, driver_b: 1 })
  assert.deepEqual(changeTelemetryDriver(library, initial, 'a', 4), { ...initial, driver_a: 4, lap_a: 11 })
  assert.deepEqual(changeTelemetryDriver(library, initial, 'a', 16), initial)
  assert.deepEqual(initial, library.default_selection)
})

test('comparison query transmits all four identities without session time or map focus', () => {
  const params = new URLSearchParams(telemetrySelectionQuery(initial))
  assert.deepEqual(Object.fromEntries(params), { driver_a: '1', lap_a: '10', driver_b: '4', lap_b: '11' })
})
