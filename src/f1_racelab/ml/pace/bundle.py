"""LightGBM median + quantile bundle. Lives in its own module so pickles reference an importable path
(a class defined in ``__main__`` cannot be unpickled by the inference service)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

SEED = 42
LGBM_PARAMS: dict[str, Any] = dict(  # noqa: C408 - keyword form mirrors LGBMRegressor arguments
    n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=40,
                   subsample=0.7, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0,
                   verbosity=-1, n_jobs=4)


def _lgbm_frame(frame: pd.DataFrame, numeric: list[str], categorical: list[str],
                categories: dict[str, list] | None = None) -> pd.DataFrame:
    out = frame[numeric].astype(float).copy()
    for col in categorical:
        known = categories[col] if categories else sorted(frame[col].astype(str).unique())
        out[col] = pd.Categorical(frame[col].astype(str), categories=known)
    return out


class LgbmBundle:
    """Median + 10%/90% quantile LightGBM models sharing one feature schema."""

    def __init__(self, numeric: list[str], categorical: list[str], seed: int = SEED, quantiles: bool = True):
        self.numeric, self.categorical, self.seed, self.quantiles = numeric, categorical, seed, quantiles

    def fit(self, frame: pd.DataFrame, y: np.ndarray) -> LgbmBundle:
        self.categories = {c: sorted(frame[c].astype(str).unique()) for c in self.categorical}
        x = _lgbm_frame(frame, self.numeric, self.categorical, self.categories)
        self.median = LGBMRegressor(objective="l1", random_state=self.seed, **LGBM_PARAMS).fit(x, y)
        if self.quantiles:
            self.q10 = LGBMRegressor(objective="quantile", alpha=0.1, random_state=self.seed, **LGBM_PARAMS).fit(x, y)
            self.q90 = LGBMRegressor(objective="quantile", alpha=0.9, random_state=self.seed, **LGBM_PARAMS).fit(x, y)
        return self

    def _x(self, frame: pd.DataFrame) -> pd.DataFrame:
        return _lgbm_frame(frame, self.numeric, self.categorical, self.categories)

    def predict(self, frame: pd.DataFrame) -> dict[str, np.ndarray]:
        x = self._x(frame)
        out: dict[str, np.ndarray] = {"median": np.asarray(self.median.predict(x))}
        if self.quantiles:
            low, high = self.q10.predict(x), self.q90.predict(x)
            out["q10"], out["q90"] = np.minimum(low, out["median"]), np.maximum(high, out["median"])
        return out

    def contributions(self, frame: pd.DataFrame) -> np.ndarray:
        """Per-feature additive contributions to the median delta (LightGBM TreeSHAP) + bias last."""
        return np.asarray(self.median.predict(self._x(frame), pred_contrib=True))
