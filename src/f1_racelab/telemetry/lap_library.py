"""Build and read an offline, content-addressed library of source-bounded laps.

A manifest is published only after all referenced deterministic gzip files exist.
The API reads this validated local snapshot and never contacts a provider.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from bisect import bisect_left, bisect_right
from datetime import timedelta
from pathlib import Path
from typing import Literal

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from f1_racelab.data.openf1_qualifying import RAW_ROOT, OpenF1Client
from f1_racelab.session.catalog import SESSIONS, ReplaySpec
from f1_racelab.telemetry.artifacts import COMPARISONS
from f1_racelab.telemetry.contracts import LapComparison, LapTelemetry, _aware_timestamp
from f1_racelab.telemetry.distance_alignment import (
    DEFAULT_MAX_SAMPLE_GAP_SECONDS,
    build_lap_telemetry,
    compare_laps,
)

LIBRARY_ROOT = Path(__file__).resolve().parents[3] / 'data/processed/telemetry_laps'
HASH_PATTERN = r'^[0-9a-f]{64}$'
LIMITS = (
    'Lap starts and speed-integrated distances are estimated.',
    'Equal integrated distance does not certify an equal physical track point.',
    'Tyres, fuel, weather, traffic and safety-car conditions are uncontrolled.',
    'Pit-out laps and known pit-in laps are excluded; absent pit data is labelled unverified.',
    'This library is historical analysis and may include laps later than the replay cursor.',
)


class LibraryContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', allow_inf_nan=False)


class LapEntry(LibraryContract):
    lap_number: int = Field(ge=1)
    start_utc: AwareDatetime
    lap_duration_seconds: float = Field(gt=0)
    integrated_distance_m: float = Field(gt=0)
    maximum_sample_gap_seconds: float = Field(gt=0, le=DEFAULT_MAX_SAMPLE_GAP_SECONDS + 1e-6)
    source_sample_count: int = Field(ge=1)
    bounded_point_count: int = Field(ge=2)
    interpolated_boundary_count: int = Field(ge=0, le=2)
    pit_entry_status: Literal['checked_not_pit_in', 'unverified']
    filename: str = Field(pattern=r'^driver-[1-9][0-9]*-lap-[1-9][0-9]*-[0-9a-f]{64}\.json\.gz$')
    sha256: str = Field(pattern=HASH_PATTERN)


class RejectedLap(LibraryContract):
    lap_number: int = Field(ge=1)
    reason: str = Field(min_length=1)


class DriverEntry(LibraryContract):
    driver_number: int = Field(gt=0)
    name: str = Field(min_length=1)
    acronym: str = Field(min_length=1)
    available: bool
    unavailable_reason: str | None = None
    laps: tuple[LapEntry, ...] = ()
    rejected_laps: tuple[RejectedLap, ...] = ()

    @model_validator(mode='after')
    def validate_driver(self) -> DriverEntry:
        numbers = [lap.lap_number for lap in self.laps]
        rejected = [lap.lap_number for lap in self.rejected_laps]
        if len(set(numbers + rejected)) != len(numbers + rejected):
            raise ValueError('Driver lap numbers must be unique across accepted and rejected laps')
        if numbers != sorted(numbers):
            raise ValueError('Library laps must be sorted by lap number')
        if self.available != bool(self.laps):
            raise ValueError('Driver availability must equal nonempty accepted laps')
        if self.available == bool(self.unavailable_reason):
            raise ValueError('Unavailable drivers require a reason; available drivers must omit it')
        for lap in self.laps:
            if lap.filename != f'driver-{self.driver_number}-lap-{lap.lap_number}-{lap.sha256}.json.gz':
                raise ValueError('Lap filename must encode driver, lap and content hash')
        return self


class LapSelection(LibraryContract):
    driver_a: int = Field(gt=0)
    lap_a: int = Field(ge=1)
    driver_b: int = Field(gt=0)
    lap_b: int = Field(ge=1)


class LapLibrary(LibraryContract):
    schema_version: Literal[1] = 1
    session_slug: str
    session_key: int = Field(gt=0)
    meeting_key: int = Field(gt=0)
    source: Literal['OpenF1 v1'] = 'OpenF1 v1'
    source_hashes: dict[str, str] = Field(min_length=2)
    drivers: tuple[DriverEntry, ...] = Field(min_length=1)
    default_selection: LapSelection | None = None
    limits: tuple[str, ...] = LIMITS

    @model_validator(mode='after')
    def validate_library(self) -> LapLibrary:
        spec = SESSIONS.get(self.session_slug)
        if spec is None or (spec.session_key, spec.meeting_key) != (self.session_key, self.meeting_key):
            raise ValueError('Library session identity does not match the replay catalog')
        numbers = [driver.driver_number for driver in self.drivers]
        if len(set(numbers)) != len(numbers):
            raise ValueError('Library driver numbers must be unique')
        if any(re.fullmatch(HASH_PATTERN, value) is None for value in self.source_hashes.values()):
            raise ValueError('Source checksums must be SHA256 hex digests')
        required = {f'drivers?session_key={self.session_key}', f'laps?session_key={self.session_key}'}
        for driver in self.drivers:
            if driver.available:
                required.add(f'car_data?driver_number={driver.driver_number}&session_key={self.session_key}')
            if any(lap.pit_entry_status == 'checked_not_pit_in' for lap in driver.laps):
                required.add(f'pit?session_key={self.session_key}')
        if not required.issubset(self.source_hashes):
            raise ValueError('Library is missing required source hashes')
        if self.default_selection:
            selected = self.default_selection
            if (selected.driver_a, selected.lap_a) == (selected.driver_b, selected.lap_b):
                raise ValueError('Default comparison cannot select one lap twice')
            for number, lap in ((selected.driver_a, selected.lap_a), (selected.driver_b, selected.lap_b)):
                self.entry(number, lap)
        return self

    def entry(self, driver_number: int, lap_number: int) -> LapEntry:
        for driver in self.drivers:
            if driver.driver_number == driver_number:
                for lap in driver.laps:
                    if lap.lap_number == lap_number:
                        return lap
        raise KeyError(f'No available telemetry for driver {driver_number} lap {lap_number}')


def _identity(rows: list[dict], spec: ReplaySpec, endpoint: str) -> None:
    if any(row.get('session_key') != spec.session_key or row.get('meeting_key') != spec.meeting_key
           for row in rows):
        raise ValueError(f'{endpoint} source belongs to a different session or meeting')


def _write_lap(root: Path, lap: LapTelemetry, pit_checked: bool) -> LapEntry:
    payload = gzip.compress(lap.model_dump_json().encode(), mtime=0)
    digest = hashlib.sha256(payload).hexdigest()
    filename = f'driver-{lap.driver_number}-lap-{lap.lap_number}-{digest}.json.gz'
    destination = root / filename
    temporary = destination.with_suffix('.tmp')
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return LapEntry(
        **{key: getattr(lap, key) for key in (
            'lap_number', 'start_utc', 'lap_duration_seconds', 'integrated_distance_m',
            'maximum_sample_gap_seconds', 'source_sample_count', 'bounded_point_count',
            'interpolated_boundary_count')},
        pit_entry_status='checked_not_pit_in' if pit_checked else 'unverified',
        filename=filename, sha256=digest,
    )


def build_library(session_slug: str, *, cache_root: Path = RAW_ROOT,
                  output_root: Path | None = None, offline: bool = True) -> LapLibrary:
    """Index each driver's timestamps once, then validate bounded windows per lap.

    Missing car-data caches remain explicit unavailable entries for all roster
    drivers. Optional pit checks use local cache only, even during an online run.
    """
    spec = SESSIONS[session_slug]
    root = output_root or LIBRARY_ROOT / session_slug
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    with OpenF1Client(cache_root, offline=offline) as client:
        roster = client.get('drivers', session_key=spec.session_key)
        laps = client.get('laps', session_key=spec.session_key)
        _identity(roster, spec, 'drivers')
        _identity(laps, spec, 'laps')
        numbers = [int(row['driver_number']) for row in roster]
        if len(numbers) != len(set(numbers)):
            raise ValueError('Duplicate source driver identity')
        if any(row.get('driver_number') not in numbers for row in laps):
            raise ValueError('Lap source references a driver absent from roster')
        with OpenF1Client(cache_root, offline=True) as pit_client:
            try:
                pits = pit_client.get('pit', session_key=spec.session_key)
            except FileNotFoundError:
                pits = None
            if pits is not None:
                _identity(pits, spec, 'pit')
                client.hashes.update(pit_client.hashes)
        pit_laps = {(row['driver_number'], row['lap_number']) for row in pits or []}
        for identity in sorted(roster, key=lambda row: int(row['driver_number'])):
            number = int(identity['driver_number'])
            driver_laps = [row for row in laps if row['driver_number'] == number]
            lap_numbers = [int(row['lap_number']) for row in driver_laps]
            if len(set(lap_numbers)) != len(lap_numbers):
                raise ValueError(f'Duplicate source lap identity for driver {number}')
            accepted: list[LapEntry] = []
            rejected: list[RejectedLap] = []
            unavailable = None
            try:
                rows = client.get('car_data', session_key=spec.session_key, driver_number=number)
            except FileNotFoundError:
                rows = []
                unavailable = 'car_data source is not cached'
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                rows = []
                unavailable = 'provider returned HTTP 404 for car_data'
            if unavailable is None:
                _identity(rows, spec, 'car_data')
                if any(row.get('driver_number') != number for row in rows):
                    raise ValueError('car_data source contains a different driver')
                indexed = sorted((_aware_timestamp(row.get('date'), 'car_data.date'), index, row)
                                 for index, row in enumerate(rows))
                times = [item[0] for item in indexed]
                if len(set(times)) != len(times):
                    raise ValueError(f'Duplicate car_data timestamp for driver {number}')
                for source in sorted(driver_laps, key=lambda row: int(row['lap_number'])):
                    lap_number = int(source['lap_number'])
                    try:
                        if (number, lap_number) in pit_laps:
                            raise ValueError('Known pit-in lap excluded')
                        start = _aware_timestamp(source.get('date_start'), 'laps.date_start')
                        duration = float(source.get('lap_duration'))
                        end = start + timedelta(seconds=duration)
                        padding = timedelta(seconds=DEFAULT_MAX_SAMPLE_GAP_SECONDS)
                        window = [item[2] for item in indexed[
                            bisect_left(times, start - padding):bisect_right(times, end + padding)]]
                        lap = build_lap_telemetry(window, source, session_key=spec.session_key,
                                                  meeting_key=spec.meeting_key, driver_number=number)
                        accepted.append(_write_lap(root, lap, pits is not None))
                    except (ValueError, TypeError, OverflowError) as exc:
                        rejected.append(RejectedLap(lap_number=lap_number, reason=str(exc)))
            entries.append(DriverEntry(
                driver_number=number, name=identity['full_name'], acronym=identity['name_acronym'],
                available=bool(accepted), unavailable_reason=None if accepted else (
                    unavailable or 'No laps satisfy the telemetry validity contract'),
                laps=tuple(accepted), rejected_laps=tuple(rejected)))
        default = COMPARISONS.get(session_slug)
        available = {(driver.driver_number, lap.lap_number) for driver in entries for lap in driver.laps}
        selection = None
        if default and {(default.driver_a, default.lap_a), (default.driver_b, default.lap_b)} <= available:
            selection = LapSelection(driver_a=default.driver_a, lap_a=default.lap_a,
                                     driver_b=default.driver_b, lap_b=default.lap_b)
        library = LapLibrary(session_slug=session_slug, session_key=spec.session_key,
                             meeting_key=spec.meeting_key, source_hashes=client.hashes,
                             drivers=tuple(entries), default_selection=selection)
    temporary = root / 'manifest.json.tmp'
    temporary.write_text(library.model_dump_json(indent=2) + '\n')
    temporary.replace(root / 'manifest.json')
    return library


def load_library(root: Path, session_slug: str) -> LapLibrary:
    library = LapLibrary.model_validate_json((root / 'manifest.json').read_bytes())
    if library.session_slug != session_slug:
        raise ValueError('Library does not belong to the requested session')
    return library


def load_lap(root: Path, library: LapLibrary, driver_number: int, lap_number: int) -> LapTelemetry:
    entry = library.entry(driver_number, lap_number)
    path = root / entry.filename
    if path.resolve().parent != root.resolve():
        raise ValueError('Lap file escapes the library root')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != entry.sha256:
        raise ValueError('Lap artifact checksum mismatch')
    lap = LapTelemetry.model_validate_json(gzip.decompress(payload))
    if (lap.session_key, lap.meeting_key, lap.driver_number, lap.lap_number) != (
            library.session_key, library.meeting_key, driver_number, lap_number):
        raise ValueError('Lap artifact identity mismatch')
    for key in ('start_utc', 'lap_duration_seconds', 'integrated_distance_m',
                'maximum_sample_gap_seconds', 'source_sample_count', 'bounded_point_count',
                'interpolated_boundary_count'):
        if getattr(lap, key) != getattr(entry, key):
            raise ValueError(f'Lap artifact disagrees with catalog field {key}')
    if lap.is_pit_out_lap or lap.maximum_sample_gap_seconds > DEFAULT_MAX_SAMPLE_GAP_SECONDS + 1e-6:
        raise ValueError('Lap artifact violates library eligibility')
    return lap


def compare_library_laps(root: Path, library: LapLibrary, selection: LapSelection) -> LapComparison:
    if (selection.driver_a, selection.lap_a) == (selection.driver_b, selection.lap_b):
        raise ValueError('A lap cannot be compared with itself')
    a = load_lap(root, library, selection.driver_a, selection.lap_a)
    b = load_lap(root, library, selection.driver_b, selection.lap_b)
    resources = {f'laps?session_key={library.session_key}',
                 f'car_data?driver_number={a.driver_number}&session_key={library.session_key}',
                 f'car_data?driver_number={b.driver_number}&session_key={library.session_key}'}
    pit = f'pit?session_key={library.session_key}'
    if pit in library.source_hashes:
        resources.add(pit)
    return compare_laps(a, b, source_hashes={key: library.source_hashes[key] for key in resources})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sessions = parser.add_mutually_exclusive_group()
    sessions.add_argument('--session', choices=sorted(SESSIONS), default='monza-2025')
    sessions.add_argument('--all', action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--offline', action='store_true', help='Only use cached responses (default)')
    mode.add_argument('--online', action='store_true', help='Explicitly fetch missing driver data, paced')
    args = parser.parse_args()
    summaries = []
    for slug in SESSIONS if args.all else [args.session]:
        library = build_library(slug, offline=not args.online)
        summaries.append({'session_slug': slug, 'drivers': len(library.drivers),
                          'available_drivers': sum(driver.available for driver in library.drivers),
                          'accepted_laps': sum(len(driver.laps) for driver in library.drivers),
                          'rejected_laps': sum(len(driver.rejected_laps) for driver in library.drivers),
                          'manifest': str(LIBRARY_ROOT / slug / 'manifest.json')})
    print(json.dumps({'libraries': summaries}, indent=2))


if __name__ == '__main__':
    main()
