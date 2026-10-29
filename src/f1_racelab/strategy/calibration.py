"""Calibrate strategy model parameters from a real race pack.

Reads lap times, stint assignments and pit stop data from a local replay pack
(the same .json.gz files used for the replay UI) and computes:
1. Per-stint tyre degradation: lap time vs stint age after removing fuel trend.
2. Per-circuit pit stop statistics: lane duration and stationary time.
3. Base race lap time: median of clean-air non-pit-out laps from the top-N drivers.

All output is clearly labelled with the source session, driver and lap ranges.
No invented values are returned; missing data results in None or raises ValueError.

Limitations:
- Fuel consumption rate and sensitivity are assumed (not measured from telemetry).
- Lap time variation from traffic, weather, SC and personal effort is not removed.
- A single-driver fit may not generalize to the full field.
- Coefficients are illustrative; use them as priors, not ground truth.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from statistics import median

from f1_racelab.strategy.models import (
    Compound,
    FuelModel,
)

PACK_ROOT = Path(__file__).resolve().parents[3] / 'data/processed/replay_packs'


def _load_pack(session_slug: str, pack_root: Path = PACK_ROOT) -> dict:
    path = list(pack_root.glob(f'{session_slug.replace("-", "_")}_race.json.gz'))
    if not path:
        raise FileNotFoundError(f'No race pack found for {session_slug!r}')
    return json.loads(gzip.decompress(path[0].read_bytes()))


def _laps_by_driver(pack: dict) -> dict[str, list[tuple[int, float]]]:
    result: dict[str, list[tuple[int, float]]] = {}
    for e in pack['events']:
        if e['type'] == 'lap':
            d = e['payload']['driver_id']
            ln = e['payload']['lap_number']
            dur = e['payload'].get('lap_duration_seconds')
            if isinstance(dur, (int, float)) and dur > 0:
                result.setdefault(d, []).append((ln, float(dur)))
    return {d: sorted(laps) for d, laps in result.items()}


def _stints_by_driver(pack: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for e in pack['events']:
        if e['type'] == 'stint':
            d = e['payload'].get('driver_id', '')
            p = e['payload']
            result.setdefault(d, []).append({
                'stint': p.get('stint_number', 1),
                'compound': p.get('compound', 'UNKNOWN'),
                'start': p.get('lap_start'),
                'end': p.get('lap_end'),
            })
    return result


def _pit_laps(pack: dict) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for e in pack['events']:
        if e['type'] == 'pit_stop':
            d = e['payload']['driver_id']
            ln = e['payload']['lap_number']
            result.setdefault(d, set()).add(ln)
    return result


def calibrate_base_lap_time(
    session_slug: str,
    pack_root: Path = PACK_ROOT,
    top_n_drivers: int = 5,
    exclude_laps: int = 3,
) -> float:
    """Median clean-air lap time from the top-N drivers (excluding first/pit-out/pit-in laps).

    This is the pace reference for the base_lap_time_s in RaceSpec.
    """
    pack = _load_pack(session_slug, pack_root)
    laps = _laps_by_driver(pack)
    pits = _pit_laps(pack)
    scheduled = pack.get('scheduled_laps', max(
        (max(ln for ln, _ in v) for v in laps.values()), default=50))

    all_times = []
    for driver_id, driver_laps in laps.items():
        pit_lns = pits.get(driver_id, set())
        clean = [t for ln, t in driver_laps
                 if ln > exclude_laps and ln < scheduled
                 and ln not in pit_lns
                 and (ln - 1) not in pit_lns]
        all_times.extend(clean)

    if not all_times:
        raise ValueError(f'No clean laps found for {session_slug!r}')
    all_times.sort()
    # Use the fastest 40%–60% percentile to avoid outliers
    lo = int(len(all_times) * 0.40)
    hi = int(len(all_times) * 0.60)
    subset = all_times[lo:hi + 1] if hi > lo else all_times[lo:lo + 1]
    return round(median(subset), 3)


def calibrate_pit_model(
    session_slug: str,
    pack_root: Path = PACK_ROOT,
) -> dict:
    """Compute lane/stationary duration statistics from all pit events.

    Returns a dict with 'mean_lane_s', 'median_lane_s', 'mean_stationary_s',
    'count' and 'circuit_name' suitable for constructing a PitModel.
    """
    pack = _load_pack(session_slug, pack_root)
    pit_events = [e for e in pack['events'] if e['type'] == 'pit_stop']
    if not pit_events:
        return {'circuit_name': pack.get('circuit_name', ''), 'count': 0}

    lane_durations = [e['payload']['lane_duration_seconds'] for e in pit_events
                      if isinstance(e['payload'].get('lane_duration_seconds'), (int, float))]
    stationary = [e['payload']['stop_duration_seconds'] for e in pit_events
                  if isinstance(e['payload'].get('stop_duration_seconds'), (int, float))]
    return {
        'circuit_name': pack.get('circuit_name', ''),
        'count': len(pit_events),
        'mean_lane_s': round(sum(lane_durations) / len(lane_durations), 3) if lane_durations else None,
        'median_lane_s': round(sorted(lane_durations)[len(lane_durations) // 2], 3) if lane_durations else None,
        'mean_stationary_s': round(sum(stationary) / len(stationary), 3) if stationary else None,
        'median_stationary_s': round(sorted(stationary)[len(stationary) // 2], 3) if stationary else None,
    }


def calibrate_tyre_degradation(
    session_slug: str,
    driver_id: str,
    compound: Compound,
    fuel_model: FuelModel,
    pack_root: Path = PACK_ROOT,
) -> dict:
    """Fit a linear degradation model for one driver/compound stint.

    Steps:
    1. Extract lap times for the specified compound stint.
    2. Remove fuel effect: adjusted = raw_lap - fuel.lap_time_delta(lap).
    3. Fit a linear regression: adjusted_pace vs stint_age.
    4. Return slope (degradation per lap) and intercept (fresh tyre pace offset).

    Returns a dict with 'driver_id', 'compound', 'stint_laps', 'base_lap_s',
    'linear_s_per_lap', 'r2' and 'limits'.
    """
    pack = _load_pack(session_slug, pack_root)
    all_laps = dict(_laps_by_driver(pack).get(driver_id, []))
    stints = _stints_by_driver(pack).get(driver_id, [])
    pits = _pit_laps(pack).get(driver_id, set())

    target_stints = [s for s in stints if s['compound'] == compound]
    if not target_stints:
        raise ValueError(f'No {compound} stint found for driver {driver_id} in {session_slug}')

    stint = target_stints[0]
    start_lap = stint['start']
    end_lap = stint.get('end')
    scheduled = pack.get('scheduled_laps', 60)

    data: list[tuple[int, float, float]] = []
    for lap_number in range(start_lap, (end_lap or scheduled) + 1):
        if lap_number not in all_laps:
            continue
        if lap_number in pits or (lap_number - 1) in pits:
            continue
        raw_time = all_laps[lap_number]
        stint_age = lap_number - start_lap + 1
        fuel_delta = fuel_model.lap_time_delta(lap_number)
        adjusted = raw_time - fuel_delta
        data.append((stint_age, adjusted, raw_time))

    if len(data) < 4:
        raise ValueError(f'Not enough clean laps for {compound} regression: found {len(data)}')

    ages = [d[0] for d in data]
    times = [d[1] for d in data]

    # OLS linear regression: times = intercept + slope * age
    n = len(ages)
    mean_age = sum(ages) / n
    mean_time = sum(times) / n
    ss_xy = sum((a - mean_age) * (t - mean_time) for a, t in zip(ages, times))
    ss_xx = sum((a - mean_age) ** 2 for a in ages)
    slope = ss_xy / ss_xx if ss_xx > 0 else 0.0
    intercept = mean_time - slope * mean_age

    # R^2
    ss_res = sum((t - (intercept + slope * a)) ** 2 for a, t in zip(ages, times))
    ss_tot = sum((t - mean_time) ** 2 for t in times)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return {
        'session_slug': session_slug,
        'driver_id': driver_id,
        'compound': compound,
        'start_lap': start_lap,
        'end_lap': end_lap,
        'stint_laps': len(data),
        'base_lap_s': round(intercept, 4),
        'linear_s_per_lap': round(slope, 5),
        'r2': round(r2, 4),
        'fuel_sensitivity_assumed': fuel_model.lap_time_sensitivity_s_per_kg,
        'limits': (
            'Fuel consumption rate is assumed, not measured from telemetry.',
            'Traffic, SC, weather and personal effort variation are not removed.',
            'Linear model may underfit late-stint cliff behaviour.',
            'Single driver; may not represent field mean or other compounds.',
        ),
    }


def sanity_check_monza(pack_root: Path = PACK_ROOT) -> dict:
    """Run all calibration routines on Monza 2025 and return a summary dict.

    This is the real-data sanity check required by the P5 acceptance gate.
    """
    from f1_racelab.strategy.models import CIRCUIT_FUEL, RACE_SPECS

    slug = 'monza-2025'
    fuel = CIRCUIT_FUEL[slug]

    base = calibrate_base_lap_time(slug, pack_root)
    pit_stats = calibrate_pit_model(slug, pack_root)
    med_deg = calibrate_tyre_degradation(slug, '1', 'MEDIUM', fuel, pack_root)
    hard_deg = calibrate_tyre_degradation(slug, '1', 'HARD', fuel, pack_root)

    spec = RACE_SPECS[slug]
    return {
        'session_slug': slug,
        'base_lap_time_calibrated_s': base,
        'base_lap_time_model_s': spec.base_lap_time_s,
        'base_lap_time_delta_s': round(base - spec.base_lap_time_s, 3),
        'pit': pit_stats,
        'medium_degradation': med_deg,
        'hard_degradation': hard_deg,
    }


if __name__ == '__main__':
    import json as _json
    result = sanity_check_monza()
    print(_json.dumps(result, indent=2))
