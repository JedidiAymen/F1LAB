export type TelemetrySelection = { driver_a: number; lap_a: number; driver_b: number; lap_b: number }
export type AvailableTelemetryLap = {
  lap_number: number
  start_utc: string
  lap_duration_seconds: number
  integrated_distance_m: number
  maximum_sample_gap_seconds: number
  source_sample_count: number
  pit_entry_status: 'checked_not_pit_in' | 'unverified'
}
export type TelemetryLibraryDriver = {
  driver_number: number
  name: string
  acronym: string
  available: boolean
  unavailable_reason?: string | null
  laps: AvailableTelemetryLap[]
  rejected_laps: { lap_number: number; reason: string }[]
}
export type TelemetryLapLibrary = {
  schema_version: number
  session_slug: string
  session_key: number
  meeting_key: number
  drivers: TelemetryLibraryDriver[]
  default_selection: TelemetrySelection | null
  limits: string[]
}

export function initialTelemetrySelection(library: TelemetryLapLibrary): TelemetrySelection | null {
  if (library.default_selection && !telemetrySelectionError(library, library.default_selection)) return library.default_selection
  const laps = library.drivers.filter((driver) => driver.available).flatMap((driver) => driver.laps.map((lap) => ({ driver: driver.driver_number, lap: lap.lap_number })))
  if (laps.length < 2) return null
  const a = laps[0]
  const b = laps.find((entry) => entry.driver !== a.driver) ?? laps[1]
  return { driver_a: a.driver, lap_a: a.lap, driver_b: b.driver, lap_b: b.lap }
}

/** Eligibility comes from the validated library, never from race timing alone. */
export function telemetrySelectionError(library: TelemetryLapLibrary, selection: TelemetrySelection): string | null {
  for (const side of ['a', 'b'] as const) {
    const driver = library.drivers.find((entry) => entry.driver_number === selection[`driver_${side}`])
    if (!driver?.available || !driver.laps.some((lap) => lap.lap_number === selection[`lap_${side}`])) {
      return 'Choose drivers and laps with validated cached telemetry.'
    }
  }
  return selection.driver_a === selection.driver_b && selection.lap_a === selection.lap_b
    ? 'Choose two different laps. The same driver can be compared across laps.' : null
}

/** Retain the lap number only when it is eligible for the newly selected driver. */
export function changeTelemetryDriver(library: TelemetryLapLibrary, selection: TelemetrySelection, side: 'a' | 'b', driverNumber: number): TelemetrySelection {
  const driver = library.drivers.find((entry) => entry.driver_number === driverNumber && entry.available)
  if (!driver?.laps.length) return selection
  const currentLap = selection[`lap_${side}`]
  return { ...selection, [`driver_${side}`]: driverNumber, [`lap_${side}`]: driver.laps.some((lap) => lap.lap_number === currentLap) ? currentLap : driver.laps[0].lap_number }
}

export function telemetrySelectionQuery(selection: TelemetrySelection): string {
  return new URLSearchParams(Object.entries(selection).map(([key, value]) => [key, String(value)])).toString()
}
