import assert from 'node:assert/strict'
import { test } from 'node:test'
import { headingScreenDegrees, projectCircuit, projectTrail, type LocationContext } from '../src/lib/circuit-geometry.ts'

const geometry = { source: 'synthetic fixture', quality: 'estimated', centerline_xy: [[0, 0], [100, 0], [100, 200], [0, 200], [0, 0]] }

test('provider XY projection preserves aspect and reverses screen Y without implying metres', () => {
  const projection = projectCircuit(geometry)!
  const [x0, y0] = projection.project(0, 0)
  const [x1, y1] = projection.project(100, 200)
  assert.equal((x1 - x0) / (y0 - y1), .5)
  assert.ok(y1 < y0)
  assert.equal(projection.lapOrigin, null)
  assert.equal(headingScreenDegrees(Math.PI / 2), -90)
  assert.equal(headingScreenDegrees(Number.NaN), null)
})

test('invalid and degenerate traces are unavailable rather than repaired', () => {
  assert.equal(projectCircuit({ ...geometry, centerline_xy: [[0, 0], [Number.NaN, 1]] }), null)
  assert.equal(projectCircuit({ ...geometry, centerline_xy: [[1, 1], [1, 1]] }), null)
  assert.equal(projectCircuit({ ...geometry, centerline_xy: [] }), null)
})

test('trail projection keeps source gaps disconnected and marks estimated connectors', () => {
  const context: LocationContext = {
    schema_version: 1, driver_id: 'ONE', session_time_seconds: 10, window_seconds: 12,
    coordinate_system: 'unknown_provider_unit', heading_radians: null, heading_quality: null,
    location_available: true,
    segments: [
      [{ session_time_seconds: 1, track_x: 0, track_y: 0, quality: 'measured' },
        { session_time_seconds: 2, track_x: 1, track_y: 1, quality: 'measured' }],
      [{ session_time_seconds: 9, track_x: 10, track_y: 10, quality: 'measured' },
        { session_time_seconds: 10, track_x: 11, track_y: 11, quality: 'estimated' }],
    ],
  }
  const segments = projectTrail(context, projectCircuit(geometry)!)
  assert.equal(segments.length, 2)
  assert.equal(segments[0].estimated, false)
  assert.equal(segments[1].estimated, true)
})
