import type { TelemetryComparisonSample } from './telemetry-comparison'

export type SegmentSide = {
  entrySpeed: number
  minimumSpeed: number
  exitSpeed: number
  brakeCrossings: number[]
  throttleCrossings: number[]
  gearShifts: number[]
  missingBrake: number
  missingThrottle: number
  missingGear: number
  sampleCount: number
}
export type DistanceSegment = {
  index: number
  start: TelemetryComparisonSample
  end: TelemetryComparisonSample
  deltaSeconds: number
  a: SegmentSide
  b: SegmentSide
}

/** Fixed, shared-grid windows: these are not surveyed corners or exact track positions. */
export function distanceSegments(samples: TelemetryComparisonSample[], requested = 12): DistanceSegment[] {
  if (!Number.isInteger(requested) || requested < 1 || samples.length < 2) return []
  const count = Math.min(requested, samples.length - 1)
  const side = (points: TelemetryComparisonSample[], driver: 'a' | 'b'): SegmentSide => {
    const speed = (p: TelemetryComparisonSample) => driver === 'a' ? p.speed_a_kmh : p.speed_b_kmh
    const brake = (p: TelemetryComparisonSample) => driver === 'a' ? p.brake_a_source_value : p.brake_b_source_value
    const throttle = (p: TelemetryComparisonSample) => driver === 'a' ? p.throttle_a_percent : p.throttle_b_percent
    const gear = (p: TelemetryComparisonSample) => driver === 'a' ? p.gear_a : p.gear_b
    const known = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v)
    const brakeCrossings: number[] = [], throttleCrossings: number[] = [], gearShifts: number[] = []
    for (let i = 1; i < points.length; i++) {
      const prior = points[i - 1], next = points[i]
      const b0 = brake(prior), b1 = brake(next), t0 = throttle(prior), t1 = throttle(next), g0 = gear(prior), g1 = gear(next)
      if (known(b0) && known(b1) && b0 <= 0 && b1 > 0) brakeCrossings.push(next.distance_m)
      if (known(t0) && known(t1) && t0 < 50 && t1 >= 50) throttleCrossings.push(next.distance_m)
      if (known(g0) && known(g1) && g0 !== g1) gearShifts.push(next.distance_m)
    }
    return { entrySpeed: speed(points[0]), minimumSpeed: Math.min(...points.map(speed)), exitSpeed: speed(points[points.length - 1]),
      brakeCrossings, throttleCrossings, gearShifts,
      missingBrake: points.filter((point) => !known(brake(point))).length,
      missingThrottle: points.filter((point) => !known(throttle(point))).length,
      missingGear: points.filter((point) => !known(gear(point))).length, sampleCount: points.length }
  }
  return Array.from({ length: count }, (_, index) => {
    const from = Math.floor(index * (samples.length - 1) / count)
    const to = Math.floor((index + 1) * (samples.length - 1) / count)
    const points = samples.slice(from, to + 1), start = points[0], end = points[points.length - 1]
    return { index: index + 1, start, end, deltaSeconds: end.delta_time_b_minus_a_seconds - start.delta_time_b_minus_a_seconds,
      a: side(points, 'a'), b: side(points, 'b') }
  })
}
