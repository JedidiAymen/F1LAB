/** Provider XY display geometry; no physical distance or surveyed width is implied. */
export type CircuitGeometry = {
  schema_version?: number
  geometry_id?: string
  centerline_xy: number[][]
  source: string
  quality: string
  closed?: boolean
  coordinate_unit?: string
  start_line?: { xy: number[]; quality: string; basis: string }
  provenance?: { driver_id: string; lap_number: number; closure: string; source_shape: string }
  diagnostics?: { retained_source_points: number; closure_ratio: number; max_sample_gap_seconds: number }
  pit_lane_xy?: null
}

export type TrailPoint = {
  session_time_seconds: number
  track_x: number
  track_y: number
  quality: 'measured' | 'estimated'
}

export type LocationContext = {
  schema_version: number
  driver_id: string
  session_time_seconds: number
  window_seconds: number
  coordinate_system: string
  segments: TrailPoint[][]
  heading_radians: number | null
  heading_quality: 'estimated' | null
  location_available: boolean
}

export type CircuitProjection = {
  path: string
  project: (x: number, y: number) => [number, number]
  lapOrigin: [number, number] | null
}

export function projectCircuit(geometry: CircuitGeometry): CircuitProjection | null {
  const points = geometry.centerline_xy
  if (points.length < 2 || points.some((point) => point.length !== 2 || !point.every(Number.isFinite))) return null
  const xs = points.map((point) => point[0])
  const ys = points.map((point) => point[1])
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  if (Math.max(...xs) === minX && Math.max(...ys) === minY) return null
  const spanX = Math.max(1, Math.max(...xs) - minX)
  const spanY = Math.max(1, Math.max(...ys) - minY)
  const scale = Math.min(820 / spanX, 450 / spanY)
  const offsetX = (900 - spanX * scale) / 2
  const offsetY = (530 - spanY * scale) / 2
  const project = (x: number, y: number): [number, number] => [
    offsetX + (x - minX) * scale,
    530 - offsetY - (y - minY) * scale,
  ]
  const origin = geometry.start_line?.xy
  return {
    project,
    path: points.map((point, index) => `${index ? 'L' : 'M'}${project(point[0], point[1]).join(' ')}`).join(' '),
    lapOrigin: origin?.length === 2 && origin.every(Number.isFinite) ? project(origin[0], origin[1]) : null,
  }
}

/** The map flips provider Y into screen Y, so its direction angle is negated. */
export function headingScreenDegrees(radians: number | null): number | null {
  return radians == null || !Number.isFinite(radians) ? null : -radians * 180 / Math.PI
}

export function projectTrail(context: LocationContext, projection: CircuitProjection) {
  return context.segments.flatMap((segment) => segment.slice(1).map((point, index) => {
    const previous = segment[index]
    return {
      path: `M${projection.project(previous.track_x, previous.track_y).join(' ')} L${projection.project(point.track_x, point.track_y).join(' ')}`,
      estimated: previous.quality === 'estimated' || point.quality === 'estimated',
    }
  }))
}
