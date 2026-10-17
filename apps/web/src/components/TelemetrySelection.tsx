import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { changeTelemetryDriver, telemetrySelectionError, type TelemetryLapLibrary, type TelemetrySelection as Selection } from '@/lib/telemetry-selection'

export function TelemetrySelection({ library, initialSelection, onApply }: {
  library: TelemetryLapLibrary
  initialSelection: Selection
  onApply: (selection: Selection) => void
}) {
  const [draft, setDraft] = useState(initialSelection)
  const validation = telemetrySelectionError(library, draft)
  const available = library.drivers.filter((driver) => driver.available && driver.laps.length > 0)
  return <div className="telemetry-selection" role="group" aria-label="Choose telemetry laps">
    <div className="telemetry-selection-controls">
      {(['a', 'b'] as const).map((side) => {
        const title = side === 'a' ? 'Reference' : 'Comparison'
        const driver = library.drivers.find((entry) => entry.driver_number === draft[`driver_${side}`])
        return <div className="telemetry-selection-pair" key={side}>
          <div className="telemetry-selection-field">
            <span id={`telemetry-${side}-driver-label`}>{title} driver</span>
            <Select value={draft[`driver_${side}`]} items={library.drivers.map((entry) => ({ value: entry.driver_number, label: `#${entry.driver_number} ${entry.acronym}${entry.available ? '' : ' · unavailable'}` }))}
              onValueChange={(value) => { if (value !== null) setDraft(changeTelemetryDriver(library, draft, side, value)) }}>
              <SelectTrigger aria-labelledby={`telemetry-${side}-driver-label`}><SelectValue /></SelectTrigger>
              <SelectContent><SelectGroup>
                {library.drivers.map((entry) => <SelectItem key={entry.driver_number} value={entry.driver_number} disabled={!entry.available || !entry.laps.length}>
                  #{entry.driver_number} {entry.acronym}{entry.available && entry.laps.length ? ` · ${entry.laps.length} laps` : ` · ${entry.unavailable_reason ?? 'unavailable'}`}
                </SelectItem>)}
              </SelectGroup></SelectContent>
            </Select>
          </div>
          <div className="telemetry-selection-field">
            <span id={`telemetry-${side}-lap-label`}>{title} lap</span>
            <Select value={draft[`lap_${side}`]} items={driver?.laps.map((lap) => ({ value: lap.lap_number, label: `L${lap.lap_number} · ${lap.lap_duration_seconds.toFixed(3)} s` }))}
              onValueChange={(value) => { if (value !== null) setDraft({ ...draft, [`lap_${side}`]: value }) }}>
              <SelectTrigger aria-labelledby={`telemetry-${side}-lap-label`}><SelectValue /></SelectTrigger>
              <SelectContent><SelectGroup>{driver?.laps.map((lap) => <SelectItem key={lap.lap_number} value={lap.lap_number}>
                L{lap.lap_number} · {lap.lap_duration_seconds.toFixed(3)} s
              </SelectItem>)}</SelectGroup></SelectContent>
            </Select>
          </div>
        </div>
      })}
      <Button variant="outline" size="sm" disabled={!!validation} onClick={() => onApply({ ...draft })}>Compare laps</Button>
    </div>
    <p className="telemetry-selection-note" {...(validation ? { role: 'status' } : {})}>{validation ?? `${available.length} of ${library.drivers.length} drivers have eligible cached laps. Apply to compare; replay time stays unchanged.`}</p>
    <p className="telemetry-selection-note">Draft selection: {(['a', 'b'] as const).map((side) => {
      const lap = library.drivers.find((driver) => driver.driver_number === draft[`driver_${side}`])?.laps.find((entry) => entry.lap_number === draft[`lap_${side}`])
      return lap ? `${side.toUpperCase()} · gap ${lap.maximum_sample_gap_seconds.toFixed(3)} s · ${lap.pit_entry_status === 'unverified' ? 'pit-in status unverified' : 'checked not pit-in'}` : ''
    }).filter(Boolean).join(' / ')}</p>
  </div>
}
