import copy

import numpy as np
import pandas as pd
import pytest

from f1_racelab.ml.common.guards import LeakageError, assert_no_forbidden_columns
from f1_racelab.ml.pace import dataset as ds

T0 = pd.Timestamp("2025-01-01 13:00:00")


def synthetic_resources(laps=14, drivers=(1, 2), sc=None):
    """Two cars, 90 s laps, soft->hard stop at lap 8 for car 1 (lap 8 = in-lap, 9 = out-lap)."""
    rows, stints = [], []
    for d in drivers:
        t = T0 + pd.Timedelta(seconds=d)
        for n in range(1, laps + 1):
            dur = 90.0 + 0.05 * n + 0.01 * d
            out = d == 1 and n == 9
            rows.append({"driver_number": d, "lap_number": n, "date_start": (t).isoformat() + "+00:00",
                         "lap_duration": dur + (20 if out else 0), "is_pit_out_lap": out})
            t += pd.Timedelta(seconds=dur)
        if d == 1:
            stints += [{"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 8,
                        "compound": "SOFT", "tyre_age_at_start": 0},
                       {"driver_number": 1, "stint_number": 2, "lap_start": 9, "lap_end": laps,
                        "compound": "HARD", "tyre_age_at_start": 0}]
        else:
            stints.append({"driver_number": d, "stint_number": 1, "lap_start": 1, "lap_end": laps,
                           "compound": "MEDIUM", "tyre_age_at_start": 2})
    control = []
    if sc:
        a, b = sc
        control = [{"date": (T0 + pd.Timedelta(seconds=a)).isoformat() + "+00:00", "category": "SafetyCar",
                    "flag": None, "message": "SAFETY CAR DEPLOYED"},
                   {"date": (T0 + pd.Timedelta(seconds=b)).isoformat() + "+00:00", "category": "SafetyCar",
                    "flag": None, "message": "SAFETY CAR IN THIS LAP"}]
    weather = [{"date": (T0 + pd.Timedelta(seconds=s)).isoformat() + "+00:00", "track_temperature": 30 + s / 100,
                "air_temperature": 20.0, "humidity": 50.0, "wind_speed": 1.0, "rainfall": 0}
               for s in (0, 300, 600, 900)]
    return {"laps": rows, "stints": stints, "pit": [], "weather": weather, "race_control": control,
            "intervals": [{"date": (T0 + pd.Timedelta(seconds=s)).isoformat() + "+00:00", "driver_number": d,
                           "interval": 1.5, "gap_to_leader": 1.5 * d} for d in (1, 2) for s in (0, 400, 800)]}


def build(res):
    return ds.build_race_frame(res, race_id="r", year=2025, circuit="Test")


def row(frame, driver, lap):
    return frame[(frame.driver_number == driver) & (frame.lap == lap)].iloc[0]


def test_target_is_next_lap_and_anchor_uses_only_history():
    frame = build(synthetic_resources())
    r = row(frame, 2, 6)
    assert r.next_lap_seconds == pytest.approx(90.0 + 0.05 * 7 + 0.02)
    assert r.anchor_seconds == pytest.approx(np.median([90.0 + 0.05 * n + 0.02 for n in (4, 5, 6)]))
    assert r.delta_seconds == pytest.approx(r.next_lap_seconds - r.anchor_seconds)
    assert r.tyre_age_next == 2 + 6 and r.compound_next == "MEDIUM"


def test_changing_the_future_never_changes_features_at_the_cutoff():
    base = build(synthetic_resources())
    future = synthetic_resources()
    for lap in future["laps"]:
        if lap["driver_number"] == 2 and lap["lap_number"] >= 7:  # lap 7 is the target of L=6
            lap["lap_duration"] += 13.0
    changed = build(future)
    feature_cols = ds.NUMERIC + ds.CATEGORICAL + ["anchor_seconds"]
    a, b = row(base, 2, 6), row(changed, 2, 6)
    # Weather/intervals/regime use as-of merges; none may see laps >= 7's durations.
    for col in feature_cols:
        assert a[col] == b[col] or (pd.isna(a[col]) and pd.isna(b[col])), col
    assert b.next_lap_seconds == pytest.approx(a.next_lap_seconds + 13.0)


def test_weather_and_intervals_are_asof_the_cutoff():
    frame = build(synthetic_resources())
    r = row(frame, 2, 6)  # cutoff = T0 + 2 + sum of first 6 laps ~ 543 s
    assert r.weather_age_s == pytest.approx((r.cutoff - (T0 + pd.Timedelta(seconds=300))).total_seconds())
    assert r.track_temp == pytest.approx(33.0)  # the 300 s observation, not the later 600 s one
    assert r.intervals_age_s == pytest.approx((r.cutoff - (T0 + pd.Timedelta(seconds=400))).total_seconds())
    assert (frame.weather_age_s >= 0).all() and (frame.intervals_age_s >= 0).all()


def test_pit_laps_and_safety_car_are_not_green_clean_targets():
    frame = build(synthetic_resources(sc=(500, 560)))
    # Car 1: lap 8 is the in-lap (next lap 9 is the out-lap) -> L=7 targets the in-lap, L=8 the out-lap.
    assert not row(frame, 1, 7).eligible_green_next and row(frame, 1, 7).next_is_in_lap
    assert not row(frame, 1, 8).eligible_green_next and row(frame, 1, 8).next_is_out_lap
    assert not frame.loc[frame.regime_next == "sc_vsc", "eligible_green_next"].any()
    assert (frame.regime_next == "sc_vsc").any()
    assert row(frame, 2, 3).eligible_green_next  # lap 4 is before the SC and clean
    # Neutralisation counters rise only after the SC laps have been driven (as-of, never before).
    assert row(frame, 2, 3).neutral_in_last3 == 0
    assert frame[frame.lap >= 8].neutral_in_last3.max() > 0


def test_forbidden_target_columns_are_not_among_features():
    assert_no_forbidden_columns(ds.NUMERIC + ds.CATEGORICAL + ds.IDENTITY, ds.FORBIDDEN_AS_FEATURES)
    with pytest.raises(LeakageError):
        assert_no_forbidden_columns(ds.NUMERIC + ["delta_seconds"], ds.FORBIDDEN_AS_FEATURES)
    assert copy.deepcopy(ds.FEATURES)[0].available_at
