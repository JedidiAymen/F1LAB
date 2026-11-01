import assert from 'node:assert/strict'
import { test } from 'node:test'
import { distanceSegments } from '../src/lib/telemetry-segments.ts'
import type { TelemetryComparisonSample } from '../src/lib/telemetry-comparison.ts'

const samples: TelemetryComparisonSample[] = [0, 1, 2, 3, 4].map((i) => ({
  distance_m: i * 10, elapsed_a_seconds: i, elapsed_b_seconds: i + i * 0.1,
  delta_time_b_minus_a_seconds: i * 0.1, speed_a_kmh: 100 - i * 10, speed_b_kmh: 90 + i,
  brake_a_source_value: [0, 10, null, 10, 0][i], throttle_a_percent: [40, 60, null, 70, 103][i],
  gear_a: [4, 3, null, 4, 5][i],
}))

test('segments cover the shared grid and deltas telescope to its terminal delta', () => {
  const segments = distanceSegments(samples, 2)
  assert.equal(segments.length, 2)
  assert.equal(segments[0].end.distance_m, segments[1].start.distance_m)
  assert.ok(Math.abs(segments.reduce((sum, s) => sum + s.deltaSeconds, 0) - 0.4) < 1e-12)
  assert.equal(segments[0].a.minimumSpeed, 80)
  assert.equal(segments[1].a.exitSpeed, 60)
})

test('only known transitions are counted and missing readings are not filled', () => {
  const [segment] = distanceSegments(samples, 1)
  assert.deepEqual(segment.a.brakeCrossings, [10])
  assert.deepEqual(segment.a.throttleCrossings, [10])
  assert.deepEqual(segment.a.gearShifts, [10, 40])
  assert.equal(segment.a.missingBrake, 1)
  assert.equal(segment.b.missingThrottle, 5)
  assert.deepEqual(distanceSegments(samples, 0), [])
})
