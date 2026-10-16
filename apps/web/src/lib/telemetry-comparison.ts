export type TelemetryComparisonSample = {
  distance_m: number
  elapsed_a_seconds: number
  elapsed_b_seconds: number
  delta_time_b_minus_a_seconds: number
  speed_a_kmh: number
  speed_b_kmh: number
}

export type TelemetryLapSummary = {
  driver_number: number
  lap_number: number
  start_utc: string
  lap_duration_seconds: number
  integrated_distance_m: number
}

export type LapComparison = {
  session_key: number
  meeting_key: number
  distance_quality: 'estimated'
  sample_spacing_m: number
  common_distance_end_m: number
  lap_a: TelemetryLapSummary
  lap_b: TelemetryLapSummary
  samples: TelemetryComparisonSample[]
}

export type TelemetryCursor = {
  distance_m: number
  delta_time_b_minus_a_seconds: number
  speed_a_kmh: number
  speed_b_kmh: number
}

export function referenceLapStartSessionSeconds(
  comparison: LapComparison,
  clockOriginUtc: string,
): number | null {
  const origin = Date.parse(clockOriginUtc)
  const start = Date.parse(comparison.lap_a.start_utc)
  if (!Number.isFinite(origin) || !Number.isFinite(start)) return null
  return (start - origin) / 1000
}

export function comparisonCursorAtSessionTime(
  comparison: LapComparison,
  clockOriginUtc: string,
  sessionSeconds: number,
): TelemetryCursor | null {
  if (!Number.isFinite(sessionSeconds) || comparison.samples.length < 2) return null
  const lapStart = referenceLapStartSessionSeconds(comparison, clockOriginUtc)
  if (lapStart == null) return null
  const elapsed = sessionSeconds - lapStart
  if (elapsed < 0 || elapsed > comparison.lap_a.lap_duration_seconds) return null

  const samples = comparison.samples
  let low = 0
  let high = samples.length - 1
  while (low + 1 < high) {
    const middle = Math.floor((low + high) / 2)
    if (samples[middle].elapsed_a_seconds <= elapsed) low = middle
    else high = middle
  }
  const before = samples[low]
  const after = samples[high]
  const span = after.elapsed_a_seconds - before.elapsed_a_seconds
  const fraction = span <= 0 ? 0 : Math.max(0, Math.min(1, (elapsed - before.elapsed_a_seconds) / span))
  const interpolate = (a: number, b: number) => a + fraction * (b - a)
  return {
    distance_m: interpolate(before.distance_m, after.distance_m),
    delta_time_b_minus_a_seconds: interpolate(
      before.delta_time_b_minus_a_seconds,
      after.delta_time_b_minus_a_seconds,
    ),
    speed_a_kmh: interpolate(before.speed_a_kmh, after.speed_a_kmh),
    speed_b_kmh: interpolate(before.speed_b_kmh, after.speed_b_kmh),
  }
}
