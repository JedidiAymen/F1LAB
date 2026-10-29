"""Leakage and split guards. Each raises ``LeakageError`` so tests and training fail loudly."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd


class LeakageError(ValueError):
    """Raised when a split, feature or timestamp would let the future inform a forecast."""


def assert_disjoint_groups(train: Iterable, test: Iterable, *, name: str = "group") -> None:
    overlap = set(train) & set(test)
    if overlap:
        raise LeakageError(f"{len(overlap)} {name}(s) appear in both train and test: {sorted(overlap)[:5]}")


def assert_chronological(train_times: Sequence, test_times: Sequence) -> None:
    """Every training time must be strictly earlier than every test time."""
    if len(train_times) and len(test_times) and max(train_times) >= min(test_times):
        raise LeakageError(f"train ends {max(train_times)} but test starts {min(test_times)}")


def assert_no_forbidden_columns(columns: Iterable[str], forbidden: Iterable[str]) -> None:
    bad = sorted(set(columns) & set(forbidden))
    if bad:
        raise LeakageError(f"forbidden (target/future) columns used as features: {bad}")


def assert_as_of(observed_at: pd.Series, cutoff: pd.Series | pd.Timestamp, *, name: str = "feature") -> None:
    """Every feature observation must be at or before its forecast cutoff."""
    late = observed_at > cutoff
    if bool(late.any()):
        raise LeakageError(f"{int(late.sum())} {name} observation(s) are after the forecast cutoff")


def chronological_group_folds(groups: pd.DataFrame, *, group_col: str, time_col: str,
                              min_train: int, step: int = 1) -> list[tuple[list, list]]:
    """Expanding-window folds: train on every earlier group, test on the next ``step``.

    ``groups`` has one row per group (e.g. race). Returns [(train_ids, test_ids)].
    """
    ordered = groups.sort_values(time_col)[group_col].tolist()
    if len(ordered) <= min_train:
        raise ValueError(f"Need more than {min_train} groups, got {len(ordered)}")
    folds = []
    for start in range(min_train, len(ordered), step):
        folds.append((ordered[:start], ordered[start:start + step]))
    return folds
