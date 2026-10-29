import numpy as np
import pytest

from f1_racelab.engines import run as engine_run
from f1_racelab.engines import transforms
from f1_racelab.ml.common import metrics

NAMES = sorted(transforms.PANDAS)


def test_mape_and_bias_definitions():
    y, p = np.array([100.0, 200.0, 0.0]), np.array([110.0, 180.0, 5.0])
    assert metrics.mape(y, p) == pytest.approx(10.0)           # zero target excluded
    assert metrics.bias(y, p) == pytest.approx((10 - 20 + 5) / 3)


def test_registry_declares_a_supported_engine_for_every_transform():
    assert set(transforms.REGISTRY) == set(NAMES)
    assert set(transforms.REGISTRY.values()) <= set(transforms.ENGINES)


@pytest.mark.parametrize("name", NAMES)
def test_duckdb_matches_pandas(name):
    pytest.importorskip("duckdb")
    df = engine_run.sample_frame()
    assert transforms.frames_equal(transforms.run(name, df, "pandas"), transforms.run(name, df, "duckdb"), rtol=1e-9)


@pytest.mark.parametrize("name", NAMES)
def test_spark_matches_pandas_and_duckdb(name):
    pytest.importorskip("pyspark")
    pytest.importorskip("duckdb")
    df = engine_run.sample_frame(rows=2000)
    spark = transforms.run(name, df, "spark")
    assert transforms.frames_equal(transforms.run(name, df, "pandas"), spark, rtol=1e-6)
    assert transforms.frames_equal(transforms.run(name, df, "duckdb"), spark, rtol=1e-6)


def test_unknown_engine_rejected():
    with pytest.raises(ValueError):
        transforms.run("race_summary", engine_run.sample_frame(10), "excel")


def test_delta_round_trip_preserves_result(tmp_path):
    pytest.importorskip("deltalake")
    out = transforms.run("race_summary", engine_run.sample_frame(), "pandas")
    version = transforms.write_delta(out, tmp_path / "t")
    assert version == 0 and transforms.frames_equal(out, transforms.read_delta(tmp_path / "t"))


def test_forecast_review_matches_metrics_module():
    pytest.importorskip("duckdb")
    import pandas as pd

    from f1_racelab.engines import forecast_review
    rng = np.random.default_rng(1)
    truth = rng.normal(90, 1, 200)
    pred = truth + rng.normal(0.2, 0.5, 200)
    df = pd.DataFrame({"year": 2025, "model": "m", "pred_seconds": pred, "next_lap_seconds": truth,
                       "eligible_green_next": True})
    row = forecast_review.review(df).iloc[0]
    assert row.mae_s == pytest.approx(metrics.mae(truth, pred))
    assert row.bias_s == pytest.approx(metrics.bias(truth, pred))
    assert row.mape_pct == pytest.approx(metrics.mape(truth, pred))
    assert "| 2025 | m | 200 |" in forecast_review.to_markdown(forecast_review.review(df))
