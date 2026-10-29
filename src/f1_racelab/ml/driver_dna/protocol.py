"""Driver DNA evaluation protocol, fixed before any model is scored.

Task A (cross-circuit identity): leave one circuit out. Train on laps from the other two circuits, test on
the held-out circuit, over the drivers present in all three races (chance = 1/K). Laps are z-scored per circuit
and grid point using only that circuit's own laps and no labels, which removes the track shape.
Caveat: some drivers changed team between races (e.g. HAM, SAI), others did not, so a car signature can leak
identity for the non-movers; accuracy is therefore also reported for movers and non-movers separately.

Task B (teammate discrimination): inside one race, classify which of two teammates drove a lap. The car is
shared, so a gain over 50% is driver signal. Train on laps up to the 60th percentile of lap number, skip a
gap of ``GAP_LAPS`` laps, test on laps after that. Pairs with fewer than ``MIN_PER_CLASS`` laps per side in
either split are dropped. Uncertainty: bootstrap over teammate pairs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

GAP_LAPS = 3
MIN_PER_CLASS = 8
TRAIN_FRACTION = 0.6


def normalise_per_circuit(x: np.ndarray, meta: pd.DataFrame) -> np.ndarray:
    out = np.empty_like(x)
    for circuit in meta.circuit.unique():
        idx = np.flatnonzero((meta.circuit == circuit).to_numpy())
        block = x[idx]
        mean, std = block.mean(axis=0, keepdims=True), block.std(axis=0, keepdims=True) + 1e-6
        out[idx] = (block - mean) / std
    return out


def shared_drivers(meta: pd.DataFrame) -> list[str]:
    return sorted(set.intersection(*[set(g.driver) for _, g in meta.groupby("circuit")]))


def circuit_folds(meta: pd.DataFrame, drivers: list[str]) -> list[tuple[np.ndarray, np.ndarray, str]]:
    """[(train_idx, test_idx, held_out_circuit)] over shared drivers only."""
    pool = meta.driver.isin(drivers).to_numpy()
    folds = []
    for circuit in sorted(meta.circuit.unique()):
        test = np.flatnonzero(pool & (meta.circuit == circuit).to_numpy())
        train = np.flatnonzero(pool & (meta.circuit != circuit).to_numpy())
        assert set(meta.circuit.iloc[train]).isdisjoint(set(meta.circuit.iloc[test]))
        folds.append((train, test, circuit))
    return folds


def teammate_splits(meta: pd.DataFrame) -> list[dict]:
    """One entry per teammate pair per race with blocked, gapped train/test index arrays."""
    out = []
    for (session, team), part in meta.groupby(["session_key", "team"]):
        drivers = sorted(part.driver.unique())
        if len(drivers) != 2:
            continue
        cut = part.lap_number.quantile(TRAIN_FRACTION)
        train = part[part.lap_number <= cut]
        test = part[part.lap_number > cut + GAP_LAPS]
        if min(train.groupby("driver").size().min(), test.groupby("driver").size().min()) < MIN_PER_CLASS \
                or train.driver.nunique() < 2 or test.driver.nunique() < 2:
            continue
        assert train.lap_number.max() + GAP_LAPS < test.lap_number.min()
        out.append({"session_key": int(session), "circuit": part.circuit.iloc[0], "team": team, "drivers": drivers,
                    "train": train.index.to_numpy(), "test": test.index.to_numpy()})
    return out


def bootstrap_mean(values: np.ndarray, draws: int = 5000, seed: int = 42) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(draws, len(values))).mean(axis=1)
    return float(values.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))
