export type Observation = {
  event_id: string
  source: string
  observed_at: string
  session_time_seconds: number
  quality: 'measured' | 'estimated' | 'simulated'
}

export type WeatherValues = {
  air_temperature_c: number | null
  track_temperature_c: number | null
  humidity_percent: number | null
  pressure_mbar: number | null
  wind_direction_degrees: number | null
  wind_speed_mps: number | null
  rainfall: boolean | null
}

export type WeatherObservation = Observation & {
  values: WeatherValues
  max_age_seconds: number
}
export type WeatherChange = {
  event_id: string
  session_time_seconds: number
  rainfall: boolean
}
export type TyreStint = {
  stint_number: number
  lap_start: number
  lap_end: number | null
  lap_end_quality: 'measured' | 'estimated' | 'simulated' | null
  compound: string
  tyre_age_at_start: number | null
  source_event_id: string
  closed_by_event_id: string | null
  session_time_seconds: number
  quality: 'measured' | 'estimated' | 'simulated'
  observed_at: string
}

export type TrackStatusObservation = Observation & {
  signal: {
    status:
      | 'green'
      | 'yellow'
      | 'red'
      | 'safety_car'
      | 'vsc'
      | 'chequered'
      | 'running_unknown'
      | 'suspended'
      | 'vsc_ending'
      | 'safety_car_ending'
    message: string
    basis: string
  }
}

export const trackStatusLabels: Record<TrackStatusObservation['signal']['status'], string> = {
  green: 'GREEN',
  yellow: 'YELLOW',
  red: 'RED FLAG',
  safety_car: 'SAFETY CAR',
  vsc: 'VSC',
  chequered: 'CHEQUERED',
  running_unknown: 'RUNNING / UNKNOWN',
  suspended: 'SUSPENDED',
  vsc_ending: 'VSC ENDING',
  safety_car_ending: 'SC ENDING',
}

export function weatherAt(seconds: number, observation: WeatherObservation | null) {
  const age = observation ? seconds - observation.session_time_seconds : null
  const fresh = age != null && age >= 0 && age <= observation!.max_age_seconds
  return { age, fresh, values: fresh ? observation!.values : null }
}

export function formatSessionTime(value: number) {
  const n = Math.floor(value)
  return `${String(Math.floor(n / 3600)).padStart(2, '0')}:${String(Math.floor((n % 3600) / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`
}
