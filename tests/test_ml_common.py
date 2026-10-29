import numpy as np
import pandas as pd
import pytest

from f1_racelab.ml.common import guards, metrics
from f1_racelab.ml.common.contracts import (
    FeatureSpec,
    ModelCard,
    SplitSpec,
    dependency_versions,
    fingerprint_frame,
    now_utc,
    read_card,
)
from f1_racelab.ml.common.registry import (
    ArtifactUnavailable,
    load_artifact,
    save_artifact,
)


def card(**kw):
    base = dict(model_id="m", version="1", task="t", target="y", dataset_fingerprint="f" * 64,
                dataset_rows=3, features=[FeatureSpec(name="a", unit="s", available_at="prior lap")],
                split=SplitSpec(policy="chrono", train_groups=2, test_groups=1, group_key="race"),
                hyperparameters={}, seed=1, metrics={"mae": 1.0}, dependencies=dependency_versions("numpy"),
                data_license="x", data_provenance="y", limitations=["z"], intended_use="research",
                created_at_utc=now_utc())
    return ModelCard(**{**base, **kw})


def test_fingerprint_ignores_row_order_but_not_values_or_columns():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
    assert fingerprint_frame(df) == fingerprint_frame(df[["b", "a"]])
    assert fingerprint_frame(df) != fingerprint_frame(df.assign(a=[1, 2, 4]))
    assert fingerprint_frame(df) != fingerprint_frame(df.rename(columns={"a": "c"}))


def test_guards_reject_future_and_overlapping_data():
    with pytest.raises(guards.LeakageError):
        guards.assert_disjoint_groups(["r1", "r2"], ["r2", "r3"], name="race")
    with pytest.raises(guards.LeakageError):
        guards.assert_chronological([1, 5], [5, 6])
    guards.assert_chronological([1, 4], [5, 6])
    with pytest.raises(guards.LeakageError):
        guards.assert_no_forbidden_columns(["lap_number", "next_lap_duration"], ["next_lap_duration"])
    times = pd.Series(pd.to_datetime(["2025-01-01", "2025-01-03"]))
    with pytest.raises(guards.LeakageError):
        guards.assert_as_of(times, pd.Timestamp("2025-01-02"))


def test_chronological_folds_expand_and_never_overlap():
    groups = pd.DataFrame({"race": list("abcdef"), "t": [3, 1, 2, 6, 5, 4]})
    folds = guards.chronological_group_folds(groups, group_col="race", time_col="t", min_train=3)
    assert folds[0] == (["b", "c", "a"], ["f"])
    for train, test in folds:
        guards.assert_disjoint_groups(train, test)
    with pytest.raises(ValueError):
        guards.chronological_group_folds(groups, group_col="race", time_col="t", min_train=6)


def test_registry_round_trip_and_tamper_detection(tmp_path):
    save_artifact(tmp_path, "m", {"weights": [1, 2, 3]}, card())
    model, loaded = load_artifact(tmp_path, "m", reproduce="make")
    assert model == {"weights": [1, 2, 3]} and loaded.model_id == "m"
    (tmp_path / "m.joblib").write_bytes(b"corrupt")
    with pytest.raises(ArtifactUnavailable, match="SHA-256"):
        load_artifact(tmp_path, "m", reproduce="make")
    with pytest.raises(ArtifactUnavailable, match="not trained"):
        load_artifact(tmp_path, "missing", reproduce="make train")
    assert read_card(tmp_path / "m.card.json").schema_version == 1


def test_metrics_and_cluster_bootstrap():
    y, p = np.array([1.0, 2.0, 4.0]), np.array([1.0, 3.0, 2.0])
    assert metrics.mae(y, p) == 1.0 and np.isclose(metrics.rmse(y, p), np.sqrt(5 / 3))
    assert metrics.pinball(np.array([2.0]), np.array([1.0]), 0.9) == pytest.approx(0.9)
    assert metrics.interval_coverage(y, p - 1, p + 1) == pytest.approx(2 / 3)
    rng = np.random.default_rng(0)
    clusters = np.repeat(np.arange(12), 20)
    better = np.abs(rng.normal(0, 0.5, 240))
    worse = better + 0.3
    out = metrics.cluster_bootstrap_delta(better, worse, clusters)
    assert out["mean_delta"] == pytest.approx(-0.3) and out["ci_high"] < 0 and out["clusters"] == 12
