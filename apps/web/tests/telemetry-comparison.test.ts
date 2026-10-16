import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  comparisonCursorAtSessionTime,
  referenceLapStartSessionSeconds,
  type LapComparison,
} from '../src/lib/telemetry-comparison.ts'

const comparison: LapComparison = {
  session_key: 9912,
  meeting_key: 1268,
  distance_quality: 'estimated',
  sample_spacing_m: 10,
  common_distance_end_m: 20,
  lap_a: {
    driver_number: 1,
    lap_number: 50,
    start_utc: '2025-09-07T14:00:00.000Z',
    lap_duration_seconds: 2,
    integrated_distance_m: 20,
  },
  lap_b: {
    driver_number: 4,
    lap_number: 50,
    start_utc: '2025-09-07T14:00:04.000Z',
    lap_duration_seconds: 2,
    integrated_distance_m: 20,
  },
  samples: [
    {
      distance_m: 0,
      elapsed_a_seconds: 0,
      elapsed_b_seconds: 0,
      delta_time_b_minus_a_seconds: 0,
      speed_a_kmh: 72,
      speed_b_kmh: 54,
    },
    {
      distance_m: 10,
      elapsed_a_seconds: 1,
      elapsed_b_seconds: 1.5,
      delta_time_b_minus_a_seconds: 0.5,
      speed_a_kmh: 90,
      speed_b_kmh: 72,
    },
    {
      distance_m: 20,
      elapsed_a_seconds: 2,
      elapsed_b_seconds: 2.5,
      delta_time_b_minus_a_seconds: 0.5,
      speed_a_kmh: 108,
      speed_b_kmh: 90,
    },
  ],
}

const clockOrigin = '2025-09-07T13:00:00.000Z'

test('telemetry cursor derives distance from the canonical session clock', () => {
  assert.equal(referenceLapStartSessionSeconds(comparison, clockOrigin), 3600)
  const cursor = comparisonCursorAtSessionTime(comparison, clockOrigin, 3600.5)
  assert.ok(cursor)
  assert.equal(cursor.distance_m, 5)
  assert.equal(cursor.delta_time_b_minus_a_seconds, 0.25)
  assert.equal(cursor.speed_a_kmh, 81)
  assert.equal(cursor.speed_b_kmh, 63)
})

test('telemetry cursor is hidden before and after the reference lap', () => {
  assert.equal(comparisonCursorAtSessionTime(comparison, clockOrigin, 3599.999), null)
  assert.equal(comparisonCursorAtSessionTime(comparison, clockOrigin, 3602.001), null)
  assert.equal(comparisonCursorAtSessionTime(comparison, clockOrigin, Number.NaN), null)
  assert.equal(comparisonCursorAtSessionTime(comparison, 'invalid', 3601), null)
})
