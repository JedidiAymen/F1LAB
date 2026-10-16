import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  comparisonCursorAtSessionTime,
  TELEMETRY_CHANNELS,
  telemetryChannelPath,
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


test('common grid tail hides the cursor before the longer reference lap ends', () => {
  const truncated = { ...comparison, lap_a: { ...comparison.lap_a, lap_duration_seconds: 4 } }
  assert.ok(comparisonCursorAtSessionTime(truncated, clockOrigin, 3602))
  assert.equal(comparisonCursorAtSessionTime(truncated, clockOrigin, 3602.001), null)
})

test('continuous channels interpolate without inventing missing values or clipping source throttle', () => {
  const full = { ...comparison, samples: comparison.samples.map((sample, index) => ({
    ...sample, throttle_a_percent: [100, 104, 108][index], throttle_b_percent: [50, null, 90][index],
    rpm_a: [10000, 12000, 14000][index], rpm_b: null,
  })) }
  const cursor = comparisonCursorAtSessionTime(full, clockOrigin, 3600.5)!
  assert.equal(cursor.throttle_a_percent, 102)
  assert.equal(cursor.throttle_b_percent, null)
  assert.equal(cursor.rpm_a, 11000)
  assert.equal(cursor.rpm_b, null)
  // Exact known endpoints survive a missing neighbor, which cannot support interpolation.
  assert.equal(comparisonCursorAtSessionTime(full, clockOrigin, 3600)!.throttle_b_percent, 50)
  assert.equal(comparisonCursorAtSessionTime(full, clockOrigin, 3602)!.throttle_b_percent, 90)
})

test('gear, raw brake and DRS retain previous values until their exact sample boundary', () => {
  const full = { ...comparison, samples: comparison.samples.map((sample, index) => ({
    ...sample, gear_a: [4, 5, 6][index], brake_a_source_value: [0, 60, null][index], drs_a_code: [8, 12, 14][index],
  })) }
  const before = comparisonCursorAtSessionTime(full, clockOrigin, 3600.999)!
  assert.equal(before.gear_a, 4)
  assert.equal(before.brake_a_source_value, 0)
  assert.equal(before.drs_a_code, 8)
  const exact = comparisonCursorAtSessionTime(full, clockOrigin, 3601)!
  assert.equal(exact.gear_a, 5)
  assert.equal(exact.brake_a_source_value, 60)
  assert.equal(exact.drs_a_code, 12)
  assert.equal(comparisonCursorAtSessionTime(full, clockOrigin, 3602)!.brake_a_source_value, null)
})

test('trace gaps do not draw zeroes or bridge missing source readings; discrete traces step', () => {
  const samples = comparison.samples.map((sample, index) => ({ ...sample, throttle_a_percent: [102, null, 106][index], gear_a: [4, 5, 6][index] }))
  const project = (distance: number, value: number): [number, number] => [distance, value]
  const throttle = TELEMETRY_CHANNELS.find((channel) => channel.id === 'throttle')!
  assert.equal(telemetryChannelPath(samples, throttle, 'a', project), 'M0.00 102.00 M20.00 106.00')
  assert.equal(telemetryChannelPath(samples, throttle, 'b', project), '')
  const gear = TELEMETRY_CHANNELS.find((channel) => channel.id === 'gear')!
  assert.equal(telemetryChannelPath(samples, gear, 'a', project), 'M0.00 4.00 H10.00 V5.00 H20.00 V6.00')
})
