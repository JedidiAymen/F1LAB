import numpy as np
import pytest

torch = pytest.importorskip("torch")

from f1_racelab.ml.driver_dna.future_nets import fit, predict


def test_test_rows_never_affect_fitted_weights_or_training_predictions():
    rng = np.random.default_rng(4)
    x = rng.normal(size=(40, 5, 64)).astype(np.float32)
    context = rng.normal(size=(40, 3)).astype(np.float32)
    y = rng.normal(size=40).astype(np.float32)
    train, val = np.arange(24), np.arange(24, 32)
    a, _ = fit(x, context, y, train, val, seed=42)
    changed_x, changed_c, changed_y = x.copy(), context.copy(), y.copy()
    changed_x[32:], changed_c[32:], changed_y[32:] = 1e4, -1e4, 1e8
    b, _ = fit(changed_x, changed_c, changed_y, train, val, seed=42)
    for key, value in a.state_dict().items():
        assert torch.equal(value, b.state_dict()[key]), key
    before, z = predict(a, x[:4], context[:4])
    after, _ = predict(b, x[:4], context[:4])
    np.testing.assert_array_equal(before, after)
    assert z.shape == (4, 64) and np.isfinite(before).all()
