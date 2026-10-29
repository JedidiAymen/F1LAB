"""Regression, interval and clustered-bootstrap metrics (all recomputable from predictions)."""
from __future__ import annotations

import numpy as np


def mae(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))


def mape(y: np.ndarray, p: np.ndarray) -> float:
    """Mean absolute percentage error in percent; zero targets are excluded (undefined)."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    keep = y != 0
    return float(np.mean(np.abs((y[keep] - p[keep]) / y[keep])) * 100)


def bias(y: np.ndarray, p: np.ndarray) -> float:
    """Mean signed error, prediction minus truth (positive = over-forecast), in the target's units."""
    return float(np.mean(np.asarray(p, float) - np.asarray(y, float)))


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))


def pinball(y: np.ndarray, q: np.ndarray, tau: float) -> float:
    diff = np.asarray(y) - np.asarray(q)
    return float(np.mean(np.maximum(tau * diff, (tau - 1) * diff)))


def interval_coverage(y: np.ndarray, low: np.ndarray, high: np.ndarray) -> float:
    y = np.asarray(y)
    return float(np.mean((y >= np.asarray(low)) & (y <= np.asarray(high))))


def cluster_bootstrap_delta(errors_a: np.ndarray, errors_b: np.ndarray, clusters: np.ndarray, *,
                            draws: int = 5000, seed: int = 42) -> dict:
    """Mean(errors_a − errors_b) with a 95% interval, resampling whole clusters (e.g. races).

    Per-lap errors in one race are dependent; resampling laps would understate
    uncertainty. Negative delta favours model A.
    """
    errors_a, errors_b, clusters = map(np.asarray, (errors_a, errors_b, clusters))
    labels, inverse = np.unique(clusters, return_inverse=True)
    sums = np.bincount(inverse, weights=errors_a - errors_b, minlength=len(labels))
    counts = np.bincount(inverse, minlength=len(labels)).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(labels), size=(draws, len(labels)))
    means = sums[pick].sum(axis=1) / counts[pick].sum(axis=1)
    return {"mean_delta": float((errors_a - errors_b).mean()), "ci_low": float(np.quantile(means, 0.025)),
            "ci_high": float(np.quantile(means, 0.975)), "clusters": len(labels),
            "draws": draws, "seed": seed}
