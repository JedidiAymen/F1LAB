import numpy as np
import pandas as pd
import pytest

from f1_racelab.ml.driver_dna.future_data import prefix, prior_context


def samples():
    t = np.arange(0, 31, 0.25)
    return pd.DataFrame({"date": pd.Timestamp("2025-01-01") + pd.to_timedelta(t, unit="s"),
                         "speed": 100 + t, "throttle": 50, "brake": 0, "n_gear": 4, "rpm": 9000, "drs": 12})


def test_future_telemetry_cannot_change_prefix_and_discrete_channels_hold():
    frame = samples()
    frame["drs"] = None  # globally excluded, never imputed to an off state
    start = frame.date.iloc[0]
    before, reason = prefix(frame, start)
    assert reason == "kept" and before.shape == (5, 64)
    frame.loc[frame.date > start + pd.Timedelta(seconds=20), "speed"] = 1e9
    after, _ = prefix(frame, start)
    np.testing.assert_array_equal(before, after)
    assert set(before[3]) == {4}


def test_prefix_rejects_missing_coverage_and_internal_gap():
    frame = samples()
    start = frame.date.iloc[0]
    assert prefix(frame.iloc[5:], start)[0] is None
    frame = frame.drop(frame.index[20:28])
    assert prefix(frame, start)[0] is None


def test_prior_context_excludes_unfinished_and_future_laps():
    start = pd.Timestamp("2025-01-01")
    laps = pd.DataFrame({"lap_number": [1, 2, 3, 4], "lap_duration": [90., 95., 9999., 80.],
                         "start": [start] * 4,
                         "end": [start - pd.Timedelta(seconds=30), start - pd.Timedelta(seconds=10),
                                 start + pd.Timedelta(seconds=21), start - pd.Timedelta(seconds=1)]})
    row = pd.Series({"start": start, "lap_number": 4})
    assert prior_context(laps, row) == (95., 92.5)
    laps.loc[2:, "lap_duration"] = 1e8
    assert prior_context(laps, row) == (95., 92.5)


def test_builder_requires_each_registered_session_not_just_split_names(tmp_path, monkeypatch):
    from f1_racelab.ml.driver_dna import future_data

    monkeypatch.setattr(future_data, "SESSIONS", {1: ("A", 2025, "train"), 2: ("B", 2026, "test")})
    def get(self, endpoint, **params):
        if endpoint == "drivers":
            return [{"driver_number": 1, "name_acronym": "AAA"}]
        if endpoint == "laps":
            return [{"driver_number": 1, "lap_number": lap, "lap_duration": 90.,
                     "date_start": (pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(seconds=90*(lap-1))).isoformat()}
                    for lap in ((1, 2) if params["session_key"] == 1 else (1,))]
        frame = samples()
        shifted = frame.copy()
        shifted["date"] += pd.Timedelta(seconds=90)
        frame = pd.concat([frame, shifted])
        frame["date"] = frame.date.map(lambda value: value.isoformat() + "+00:00")
        return frame.to_dict("records")
    monkeypatch.setattr(future_data.OpenF1Client, "get", get)
    with pytest.raises(ValueError, match="Every registered session"):
        future_data.build(tmp_path, tmp_path / "out")
    assert not (tmp_path / "out/prefixes.npz").exists()
