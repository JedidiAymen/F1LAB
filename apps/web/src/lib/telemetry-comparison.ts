export const TELEMETRY_CHANNELS = [
  { id: 'speed', label: 'Speed', unit: 'km/h', axis: 'KM/H', discrete: false, defaultMax: 360, a: 'speed_a_kmh', b: 'speed_b_kmh' },
  { id: 'throttle', label: 'Throttle', unit: '% source', axis: 'THROTTLE %', discrete: false, defaultMax: 100, a: 'throttle_a_percent', b: 'throttle_b_percent' },
  { id: 'brake', label: 'Brake', unit: 'raw', axis: 'BRAKE RAW', discrete: true, defaultMax: 100, a: 'brake_a_source_value', b: 'brake_b_source_value' },
  { id: 'rpm', label: 'RPM', unit: 'rpm', axis: 'RPM', discrete: false, defaultMax: 15000, a: 'rpm_a', b: 'rpm_b' },
  { id: 'gear', label: 'Gear', unit: 'gear', axis: 'GEAR', discrete: true, defaultMax: 8, a: 'gear_a', b: 'gear_b' },
  { id: 'drs', label: 'DRS', unit: 'raw code', axis: 'DRS CODE', discrete: true, defaultMax: 14, a: 'drs_a_code', b: 'drs_b_code' },
] as const

export type TelemetryChannel = typeof TELEMETRY_CHANNELS[number]
export type TelemetryChannelId = TelemetryChannel['id']
export type TelemetryComparisonSample = {
  distance_m: number
  elapsed_a_seconds: number
  elapsed_b_seconds: number
  delta_time_b_minus_a_seconds: number
  speed_a_kmh: number
  speed_b_kmh: number
  throttle_a_percent?: number | null
  throttle_b_percent?: number | null
  brake_a_source_value?: number | null
  brake_b_source_value?: number | null
  rpm_a?: number | null
  rpm_b?: number | null
  gear_a?: number | null
  gear_b?: number | null
  drs_a_code?: number | null
  drs_b_code?: number | null
}

export type TelemetryLapSummary = {
  driver_number: number
  lap_number: number
  start_utc: string
  lap_duration_seconds: number
  integrated_distance_m: number
  maximum_sample_gap_seconds?: number
  bounded_point_count?: number
  interpolated_boundary_count?: number
  source_sample_count?: number
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

export type TelemetryCursor = Omit<TelemetryComparisonSample, 'elapsed_a_seconds' | 'elapsed_b_seconds'>

export function channelValue(sample: TelemetryCursor, channel: TelemetryChannel, driver: 'a' | 'b'): number | null {
  const value = sample[channel[driver]]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** Missing source values break the SVG path; discrete channels hold the earlier value. */
export function telemetryChannelPath(
  samples: TelemetryComparisonSample[], channel: TelemetryChannel, driver: 'a' | 'b',
  project: (distance: number, value: number) => [number, number],
): string {
  let connected = false
  const commands: string[] = []
  let previousValue: number | null = null
  for (const sample of samples) {
    const value = channelValue(sample, channel, driver)
    if (value === null) {
      // A discrete value is held until the first missing observation, so draw
      // that known interval to the null sample before starting a gap.
      if (connected && channel.discrete && previousValue !== null) {
        const [x] = project(sample.distance_m, previousValue)
        commands.push(`H${x.toFixed(2)}`)
      }
      connected = false
      previousValue = null
      continue
    }
    const [x, y] = project(sample.distance_m, value)
    commands.push(!connected ? `M${x.toFixed(2)} ${y.toFixed(2)}`
      : channel.discrete ? `H${x.toFixed(2)} V${y.toFixed(2)}` : `L${x.toFixed(2)} ${y.toFixed(2)}`)
    connected = true
    previousValue = value
  }
  return commands.join(' ')
}

export function referenceLapStartSessionSeconds(comparison: LapComparison, clockOriginUtc: string): number | null {
  const origin = Date.parse(clockOriginUtc)
  const start = Date.parse(comparison.lap_a.start_utc)
  if (!Number.isFinite(origin) || !Number.isFinite(start)) return null
  return (start - origin) / 1000
}

export function comparisonCursorAtSessionTime(
  comparison: LapComparison, clockOriginUtc: string, sessionSeconds: number,
): TelemetryCursor | null {
  if (!Number.isFinite(sessionSeconds) || comparison.samples.length < 2) return null
  const lapStart = referenceLapStartSessionSeconds(comparison, clockOriginUtc)
  if (lapStart == null) return null
  const elapsed = sessionSeconds - lapStart
  const samples = comparison.samples
  // The common distance grid can end before A's lap boundary: never freeze at its tail.
  if (elapsed < samples[0].elapsed_a_seconds || elapsed > samples.at(-1)!.elapsed_a_seconds) return null
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
  const fraction = span <= 0 ? 0 : (elapsed - before.elapsed_a_seconds) / span
  const interpolate = (a: number, b: number) => a + fraction * (b - a)
  const cursor: TelemetryCursor = {
    distance_m: interpolate(before.distance_m, after.distance_m),
    delta_time_b_minus_a_seconds: interpolate(before.delta_time_b_minus_a_seconds, after.delta_time_b_minus_a_seconds),
    speed_a_kmh: interpolate(before.speed_a_kmh, after.speed_a_kmh),
    speed_b_kmh: interpolate(before.speed_b_kmh, after.speed_b_kmh),
  }
  for (const channel of TELEMETRY_CHANNELS) {
    if (channel.id === 'speed') continue // Required speed fields were interpolated above.
    for (const driver of ['a', 'b'] as const) {
      const a = channelValue(before, channel, driver)
      const b = channelValue(after, channel, driver)
      cursor[channel[driver]] = channel.discrete ? (fraction === 1 ? b : a)
        : fraction === 0 ? a : fraction === 1 ? b : a === null || b === null ? null : interpolate(a, b)
    }
  }
  return cursor
}
