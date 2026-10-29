import numpy as np
import pandas as pd
import pytest

from f1_racelab.ml.driver_dna import dataset, handcrafted, protocol


def _meta():
    rows = []
    for circuit, session in (("A", 1), ("B", 2), ("C", 3)):
        for team, drivers in (("T1", ("X", "Y")), ("T2", ("Z", "W"))):
            for driver in drivers:
                for lap in range(2, 42):
                    rows.append({"session_key": session, "circuit": circuit, "team": team, "driver": driver,
                                 "lap_number": lap, "lap_seconds": 90.0})
    return pd.DataFrame(rows)


def test_circuit_folds_never_share_a_circuit():
    meta = _meta()
    folds = protocol.circuit_folds(meta, protocol.shared_drivers(meta))
    assert len(folds) == 3
    for train, test, held_out in folds:
        assert set(meta.circuit.iloc[test]) == {held_out} and held_out not in set(meta.circuit.iloc[train])


def test_teammate_split_is_blocked_with_gap_and_balanced():
    splits = protocol.teammate_splits(_meta())
    assert len(splits) == 6
    meta = _meta()
    for s in splits:
        assert meta.lap_number.loc[s["train"]].max() + protocol.GAP_LAPS < meta.lap_number.loc[s["test"]].min()
        assert set(meta.driver.loc[s["train"]]) == set(meta.driver.loc[s["test"]]) == set(s["drivers"])


def test_per_circuit_normalisation_uses_no_labels_and_zeroes_means():
    meta = _meta()
    x = np.random.default_rng(0).normal(5, 2, (len(meta), 6, 16)).astype(np.float32)
    out = protocol.normalise_per_circuit(x, meta)
    for circuit in "ABC":
        block = out[(meta.circuit == circuit).to_numpy()]
        assert abs(block.mean(0)).max() < 1e-4


def test_resample_lap_rejects_gaps_and_short_laps_and_returns_fixed_grid():
    start = pd.Timestamp("2025-01-01 12:00:00")
    n = 300
    dates = start + pd.to_timedelta(np.arange(n) * 0.27, unit="s")
    frame = pd.DataFrame({"date": dates, "speed": 200.0, "throttle": 100, "brake": 0, "n_gear": 7, "rpm": 11000,
                          "drs": 0})
    lap = dataset.resample_lap(frame, dates[0], dates[-1])
    assert lap.shape == (6, dataset.GRID) and np.allclose(lap[0], 200.0)
    gapped = frame.drop(index=range(100, 110))
    assert dataset.resample_lap(gapped, dates[0], dates[-1]) is None
    assert dataset.resample_lap(frame.head(50), dates[0], dates[49]) is None


def test_handcrafted_descriptors_shape_and_values():
    x = np.zeros((2, 6, 64), dtype=np.float32)
    x[:, 0], x[:, 1], x[:, 3] = 250.0, 100.0, 6
    out = handcrafted.describe(x, dataset.SCALES)
    assert out.shape == (2, len(handcrafted.NAMES))
    assert out[0, handcrafted.NAMES.index("full_throttle")] == 1.0


def test_networks_forward_and_determinism():
    torch = pytest.importorskip("torch")
    from f1_racelab.ml.driver_dna import nets
    x = np.random.default_rng(0).normal(size=(40, 6, 64)).astype(np.float32)
    y = np.arange(40) % 4
    first = nets.predict_logits(nets.fit_classifier(x, y, 4, seed=1, epochs=2), x)
    second = nets.predict_logits(nets.fit_classifier(x, y, 4, seed=1, epochs=2), x)
    assert first.shape == (40, 4) and torch.isfinite(torch.as_tensor(first)).all()
    assert nets.embed(nets.fit_contrastive(x, seed=1, epochs=1), x).shape[0] == 40
    assert np.allclose(first, second, atol=1e-3)
