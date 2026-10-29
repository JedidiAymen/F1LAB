import numpy as np
import pandas as pd
import pytest

from f1_racelab.models import neural_qualifying as nq
from f1_racelab.models import qualifying_walkforward as wf


def test_era_and_shrink_weight_predeclared_rules():
    assert nq.era(2025) == 0 and nq.era(2026) == 1
    assert nq.shrink_weight(0) == 0.0                     # first event of an era = pure latest practice
    assert nq.shrink_weight(6) == pytest.approx(0.5) and nq.shrink_weight(54) == pytest.approx(0.9)


def test_mlp_is_seeded_and_uses_only_training_rows():
    pytest.importorskip("torch")
    rng = np.random.default_rng(0)
    train = pd.DataFrame(rng.normal(size=(60, len(wf.NUMERIC))), columns=wf.NUMERIC)
    train[wf.TARGET] = train[wf.NUMERIC[0]] * 0.5 + rng.normal(0, 0.05, 60)
    test = pd.DataFrame(rng.normal(size=(5, len(wf.NUMERIC))), columns=wf.NUMERIC)
    first, second = nq._mlp_predict(train, test), nq._mlp_predict(train, test)
    assert first.shape == (5,) and np.allclose(first, second, atol=1e-5) and np.isfinite(first).all()
