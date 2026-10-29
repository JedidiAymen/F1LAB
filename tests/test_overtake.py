import numpy as np
import pandas as pd

from f1_racelab.ml.overtake import benchmark, dataset


def _frame(swap=True, pit_on_l1=False, neutral=0):
    """Two drivers, laps 1-3. Driver 2 starts 0.5 s behind driver 1 and passes during lap 2 if `swap`."""
    rows = []
    for lap in (1, 2, 3):
        for driver, base in ((1, 10.0), (2, 10.5)):
            gap = base if lap == 1 else (base if not swap else (10.6 if driver == 1 else 10.2))
            rows.append({"race_id": "r", "year": 2025, "event": "x", "circuit": "c", "race_start": pd.Timestamp("2025-03-01"),
                         "lap": lap, "driver_number": driver, "gap_to_leader": gap,
                         "interval_ahead": 0.5 if driver == 2 else 0.0, "anchor_seconds": 90.0, "last1": 0.0,
                         "tyre_age_next": 5.0, "compound_next": "MEDIUM", "laps_remaining": 40.0,
                         "next_is_in_lap": pit_on_l1 and lap == 1 and driver == 1, "next_is_out_lap": False,
                         "neutral_in_last3": neutral, "yellow_in_last1": 0, "regime_next": "green",
                         "intervals_age_s": 0.1})
    return pd.DataFrame(rows)


def test_swap_is_labelled_positive_and_no_swap_negative():
    pairs = dataset.build(_frame(swap=True))
    row = pairs[(pairs.lap == 1) & (pairs.driver_number == 2)]
    assert len(row) == 1 and int(row.overtake.iloc[0]) == 1
    flat = dataset.build(_frame(swap=False))
    assert flat[(flat.lap == 1) & (flat.driver_number == 2)].overtake.iloc[0] == 0


def test_pit_involved_and_neutralised_pairs_are_dropped_not_labelled_negative():
    assert dataset.build(_frame(pit_on_l1=True)).query("lap == 1").empty
    assert dataset.build(_frame(neutral=1)).empty


def test_circuit_prior_rate_uses_only_earlier_races():
    pairs = pd.DataFrame({"circuit": ["c"] * 3, "race_id": ["a", "b", "c"], "overtake": [1, 0, 1],
                          "race_start": pd.to_datetime(["2024-01-01", "2024-06-01", "2025-01-01"])})
    prior = dataset._prior_circuit_rate(pairs)
    assert np.isnan(prior.iloc[0]) and prior.iloc[1] == 1.0 and prior.iloc[2] == 0.5


def test_ece_zero_for_perfectly_calibrated_and_positive_otherwise():
    y = np.array([0, 1] * 50)
    assert benchmark.ece(y, np.full(100, 0.5)) < 1e-9
    assert benchmark.ece(y, np.full(100, 0.9)) > 0.3


def test_summary_endpoint_503_without_results(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from f1_racelab.api import create_app
    monkeypatch.setattr(benchmark, "OUT", tmp_path)
    response = TestClient(create_app()).get("/api/v1/overtake/summary")
    assert response.status_code == 503 and "Run:" in response.json()["detail"]
