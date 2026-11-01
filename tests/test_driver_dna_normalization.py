import hashlib
import json

import numpy as np
import pytest

from f1_racelab.ml.driver_dna.protocol import (
    apply_train_normalization,
    fit_train_normalization,
)


def test_service_checks_optional_study_hash(tmp_path):
    from f1_racelab.ml.driver_dna.service import DnaUnavailable, summary

    base = {"models": {"logistic": {"task_a": {"accuracy": 0.4, "chance": 0.1},
                                     "task_b": {"mean_accuracy": 0.8, "ci": [0.7, 0.9],
                                                "mean_majority_baseline": 0.5}}}, "task_b_controls": {}}
    (tmp_path / "baselines.json").write_text(json.dumps(base))
    (tmp_path / "dataset_summary.json").write_text(json.dumps({"laps": 10, "per_session": {},
                                                                "shared_drivers_all_sessions": []}))
    (tmp_path / "nets.json").write_text(json.dumps({"task_a": {}, "task_b": {}, "seeds": [42], "device": "cpu"}))
    assert summary(tmp_path)["normalization_study"] is None
    path = tmp_path / "normalization_study.json"
    path.write_text('{"schema_version":1,"evidence":"synthetic"}')
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    assert summary(tmp_path)["normalization_study"]["evidence"] == "synthetic"
    path.write_text("{}")
    with pytest.raises(DnaUnavailable, match="Invalid normalization"):
        summary(tmp_path)


def test_held_out_poisoning_cannot_change_training_normalization():
    x = np.random.default_rng(42).normal(size=(20, 6, 32)).astype(np.float32)
    train = np.arange(12)
    first = fit_train_normalization(x, train)
    changed = x.copy()
    changed[12:] += 100000
    second = fit_train_normalization(changed, train)
    assert np.array_equal(first.mean, second.mean) and np.array_equal(first.scale, second.scale)
    assert not first.mean.flags.writeable and first.train_rows == 12
    assert np.allclose(apply_train_normalization(x[train], first).mean(0), 0, atol=1e-6)
    assert np.array_equal(apply_train_normalization(x[:2], first),
                          apply_train_normalization(changed[:2], second))


@pytest.mark.parametrize("indices", [np.array([], dtype=int), np.array([0, 0]), np.array([-1]),
                                     np.array([20]), np.array([1.5])])
def test_invalid_fit_indices_fail_closed(indices):
    with pytest.raises(ValueError):
        fit_train_normalization(np.ones((20, 2)), indices)


def test_transform_rejects_shape_mismatch_and_nonfinite_inputs():
    x = np.ones((5, 3))
    stats = fit_train_normalization(x, np.arange(3))
    assert np.isfinite(apply_train_normalization(x, stats)).all()
    with pytest.raises(ValueError):
        apply_train_normalization(np.ones((2, 4)), stats)
    with pytest.raises(ValueError):
        apply_train_normalization(np.full((2, 3), np.nan), stats)
