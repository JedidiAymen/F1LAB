"""Walk-forward qualifying forecaster with calibrated rank probabilities.

Contract (see docs/ML_WALKFORWARD.md):

* Events are processed in chronological ``(year, round)`` order. The models that
  score event *i* are fitted ONLY on events ``< i``; nothing is tuned on the
  evaluated seasons (hyper-parameters are fixed constants below).
* Every feature is pre-qualifying: same-weekend practice summaries, or labels
  from strictly earlier weekends (see ``features.historical_qualifying``).
* ``ensemble`` is declared the candidate before any result is inspected, so
  there is no model selection on the held-out years.
* Uncertainty: the ensemble's gap forecast (percent of event-best Q1 pace) is
  perturbed by Gaussian noise whose scale is estimated from *earlier* events'
  out-of-sample residuals. A seeded Monte Carlo turns it into per-driver
  P(pole), P(top-3), expected rank and an 80% rank interval, which are audited
  with Brier score, reliability bins and interval coverage.

Units: ``*_gap_pct`` are percent of the event-best lap; ranks are 1-based among
eligible drivers of the event.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRanker, LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from f1_racelab.features.historical_qualifying import (
    add_historical_features,
    feature_names,
)
from f1_racelab.models.qualifying_backtest import (
    COMMON_FEATURES,
    GROUP,
    LABEL,
    TARGET,
    evaluate,
    paired_event_bootstrap,
    scored_positions,
)

ROOT = Path(__file__).resolve().parents[3]
DATA_FILE = ROOT / "data/processed/qualifying_mixed_2022_2023_2024_2025.parquet"
OUT = ROOT / "data/processed/qualifying_walkforward"

CONTEXT_FEATURES = [
    "practice_gap_mean", "practice_gap_min", "practice_rank_mean",
    "latest_gap", "latest_rank", "n_practice_sessions",
    "team_best_latest_gap", "teammate_delta_latest", "field_spread_latest",
    "track_history_q1_gap",
]
NUMERIC = COMMON_FEATURES + CONTEXT_FEATURES + feature_names()
MODELS = ("latest_practice", "ridge", "lightgbm", "lambdarank", "ensemble")
SEED = 42
MC_DRAWS = 4000
MIN_RESIDUAL_EVENTS = 3
RANKER_LEVELS = 20  # relevance = clip(n_drivers - rank, 0, 20)


def add_weekend_context_features(df: pd.DataFrame) -> pd.DataFrame:
    """Same-weekend practice summaries and as-of track history.

    Everything here is observable before qualifying: it reads FP1/2/3 columns of
    the *same* weekend, or ``q1_gap_pct`` of strictly earlier seasons at the same
    event name (``shift(1)`` inside a driver/event group, ordered by year).
    """
    out = df.copy()
    gaps = out[["fp1_gap_pct", "fp2_gap_pct", "fp3_gap_pct"]]
    ranks = out[["fp1_rank", "fp2_rank", "fp3_rank"]]
    out["practice_gap_mean"] = gaps.mean(axis=1)
    out["practice_gap_min"] = gaps.min(axis=1)
    out["practice_rank_mean"] = ranks.mean(axis=1)
    out["n_practice_sessions"] = gaps.notna().sum(axis=1).astype(float)
    # Latest available session wins (FP3 > FP2 > FP1).
    out["latest_gap"] = out["fp3_gap_pct"].fillna(out["fp2_gap_pct"]).fillna(out["fp1_gap_pct"])
    out["latest_rank"] = out["fp3_rank"].fillna(out["fp2_rank"]).fillna(out["fp1_rank"])

    key = GROUP + ["team"]
    team = out.groupby(key)["latest_gap"]
    out["team_best_latest_gap"] = team.transform("min")
    total, count = team.transform("sum"), team.transform("count")
    mate_mean = (total - out["latest_gap"]) / (count - 1)
    out["teammate_delta_latest"] = (out["latest_gap"] - mate_mean).where(count >= 2)
    out["field_spread_latest"] = out.groupby(GROUP)["latest_gap"].transform("std")

    out = out.sort_values(["driver", "event", "year", "round"], kind="stable")
    out["track_history_q1_gap"] = out.groupby(["driver", "event"])["q1_gap_pct"].shift(1)
    return out.sort_values(GROUP + ["driver"], kind="stable").reset_index(drop=True)


def build_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Raw mixed-provider rows -> modelling frame (eligible rows only)."""
    enriched = add_historical_features(raw)
    enriched["team"] = enriched["team"].astype("string").fillna("__UNKNOWN__").astype(str)
    # Eligibility needs only *some* practice signal (latest available gap), not
    # an FP3 lap, so sprint-like or FP3-less weekends are not discarded.
    frame = add_weekend_context_features(
        enriched.assign(
            q1_gap_pct=pd.to_numeric(enriched["q1_gap_pct"], errors="coerce"),
            final_position=pd.to_numeric(enriched["final_position"], errors="coerce"),
        )
    )
    for column in NUMERIC:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    frame["year"] = frame["year"].astype(int)
    frame["round"] = frame["round"].astype(int)
    frame = frame.dropna(subset=[TARGET, LABEL, "latest_gap"])
    frame = frame.loc[(frame[LABEL] > 0) & (frame[TARGET] >= 0)]
    sizes = frame.groupby(GROUP)["driver"].transform("count")
    return frame.loc[sizes >= 8].sort_values(GROUP + [LABEL], kind="stable").reset_index(drop=True)


def _regressor_pipeline(kind: str) -> Pipeline:
    numeric = Pipeline([
        ("fill", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    if kind == "ridge":
        pre = ColumnTransformer([
            ("num", numeric, NUMERIC),
            ("cat", Pipeline([
                ("fill", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]), ["team"]),
        ])
        return Pipeline([("pre", pre), ("model", Ridge(alpha=30.0))])
    pre = ColumnTransformer([("num", numeric, NUMERIC)])
    model = LGBMRegressor(
        n_estimators=180, learning_rate=0.03, num_leaves=8, min_child_samples=30,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=8.0,
        verbosity=-1, random_state=SEED, n_jobs=2,
    )
    return Pipeline([("pre", pre), ("model", model)])


def _fit_ranker(train: pd.DataFrame):
    """LambdaRank on within-event ordering; returns (preprocessor, ranker)."""
    train = train.sort_values(GROUP + [LABEL], kind="stable")
    pre = Pipeline([
        ("fill", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    x = pre.fit_transform(train[NUMERIC])
    n = train.groupby(GROUP)[LABEL].transform("count").to_numpy()
    rank = train.groupby(GROUP)[LABEL].rank(method="first").to_numpy()
    relevance = np.clip(n - rank, 0, RANKER_LEVELS).astype(int)
    groups = train.groupby(GROUP, sort=False).size().to_numpy()
    ranker = LGBMRanker(
        objective="lambdarank", n_estimators=150, learning_rate=0.04, num_leaves=8,
        min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.7,
        reg_lambda=8.0, label_gain=list(range(RANKER_LEVELS + 2)),
        verbosity=-1, random_state=SEED, n_jobs=2,
    )
    ranker.fit(x, relevance, group=groups)
    return pre, ranker


def _zscore(values: np.ndarray) -> np.ndarray:
    spread = values.std()
    return (values - values.mean()) / (spread if spread > 1e-9 else 1.0)


def _predict_event(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """Fit on strictly earlier events and score one event. Lower score = faster."""
    ridge = _regressor_pipeline("ridge").fit(train[NUMERIC + ["team"]], train[TARGET])
    boosted = _regressor_pipeline("lgbm").fit(train[NUMERIC], train[TARGET])
    pre, ranker = _fit_ranker(train)

    ridge_gap = ridge.predict(test[NUMERIC + ["team"]])
    lgbm_gap = boosted.predict(test[NUMERIC])
    rank_score = -ranker.predict(pre.transform(test[NUMERIC]))  # higher relevance = faster
    z = np.mean([_zscore(ridge_gap), _zscore(lgbm_gap), _zscore(rank_score)], axis=0)
    # Put the ensemble on the gap scale of the ridge so residuals are comparable.
    ensemble_gap = ridge_gap.mean() + ridge_gap.std() * z
    return pd.DataFrame({
        "latest_practice": test["latest_gap"].to_numpy(),
        "ridge": ridge_gap, "lightgbm": lgbm_gap,
        "lambdarank": rank_score, "ensemble": ensemble_gap,
    }, index=test.index)


def monte_carlo_ranks(mu: np.ndarray, sigma: np.ndarray, *, draws: int = MC_DRAWS,
                      seed: int = SEED) -> dict[str, np.ndarray]:
    """Rank distribution from independent Gaussian gap perturbations."""
    rng = np.random.default_rng(seed)
    sample = mu[None, :] + sigma[None, :] * rng.standard_normal((draws, len(mu)))
    ranks = sample.argsort(axis=1).argsort(axis=1) + 1
    return {
        "p_pole": (ranks == 1).mean(axis=0),
        "p_top3": (ranks <= 3).mean(axis=0),
        "expected_rank": ranks.mean(axis=0),
        "rank_p10": np.quantile(ranks, 0.10, axis=0),
        "rank_p90": np.quantile(ranks, 0.90, axis=0),
    }


class ResidualScale:
    """Relative error scale learned from earlier events only.

    ``sigma_i = ratio * (0.5 + predicted_gap_i)``: slower cars are less
    predictable. ``ratio`` is the standard deviation of earlier out-of-sample
    ``residual / (0.5 + predicted_gap)`` values.
    """

    MULTIPLIERS = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2)

    def __init__(self) -> None:
        self._ratios: list[np.ndarray] = []
        self._history: list[tuple[np.ndarray, np.ndarray]] = []  # (mu, actual_rank)
        self._events = 0

    def ready(self) -> bool:
        return self._events >= MIN_RESIDUAL_EVENTS

    def _base_sigma(self, predicted_gap: np.ndarray, ratio: float) -> np.ndarray:
        return np.maximum(ratio * (0.5 + np.clip(predicted_gap, 0, None)), 0.02)

    def multiplier(self) -> float:
        """Noise multiplier minimising earlier events' top-3 Brier score.

        The residual scale is measured on the Q1-gap target, while the outcome
        is the final classification rank; the multiplier absorbs that mismatch.
        Only events already finished contribute, so no future leakage.
        """
        ratio = float(np.concatenate(self._ratios).std())
        best, best_score = 1.0, np.inf
        for k in self.MULTIPLIERS:
            scores = []
            for mu, actual_rank in self._history:
                mc = monte_carlo_ranks(mu, k * self._base_sigma(mu, ratio), draws=300, seed=SEED)
                scores.append(np.mean((mc["p_top3"] - (actual_rank <= 3)) ** 2))
            score = float(np.mean(scores))
            if score < best_score:
                best, best_score = k, score
        return best

    def sigma(self, predicted_gap: np.ndarray) -> np.ndarray:
        ratio = float(np.concatenate(self._ratios).std())
        return self.multiplier() * self._base_sigma(predicted_gap, ratio)

    def update(self, predicted_gap: np.ndarray, actual_gap: np.ndarray,
               actual_rank: np.ndarray) -> None:
        self._history.append((predicted_gap.copy(), actual_rank.copy()))
        self._ratios.append((actual_gap - predicted_gap) / (0.5 + np.clip(predicted_gap, 0, None)))
        self._events += 1


def walk_forward(frame: pd.DataFrame, *, warmup_events: int = 12,
                 draws: int = MC_DRAWS) -> pd.DataFrame:
    """Score every event after ``warmup_events`` using only earlier events."""
    events = list(frame[GROUP].drop_duplicates().itertuples(index=False, name=None))
    if len(events) <= warmup_events:
        raise ValueError(f"Need more than {warmup_events} events, got {len(events)}")
    order = {event: i for i, event in enumerate(events)}
    index = pd.Series([order[(y, r)] for y, r in zip(frame.year, frame["round"])], index=frame.index)
    scale = ResidualScale()
    pieces: list[pd.DataFrame] = []
    for i in range(warmup_events, len(events)):
        train, test = frame.loc[index < i], frame.loc[index == i]
        scores = _predict_event(train, test)
        pieces_for_event = []
        for name in MODELS:
            piece = scored_positions(test, scores[name].to_numpy(), name)
            piece["event_index"] = i
            pieces_for_event.append(piece)
        event_frame = pd.concat(pieces_for_event, ignore_index=True)
        mu = scores["ensemble"].to_numpy()
        actual = test[TARGET].to_numpy()
        if scale.ready():
            sigma = scale.sigma(mu)
            mc = monte_carlo_ranks(mu, sigma, draws=draws, seed=SEED + i)
            ens = event_frame["model"] == "ensemble"
            # scored_positions sorts by predicted score; align by driver label.
            by_driver = pd.DataFrame(mc, index=test["driver"].to_numpy())
            by_driver["sigma"] = sigma
            for column in by_driver.columns:
                event_frame.loc[ens, column] = event_frame.loc[ens, "driver"].map(by_driver[column]).to_numpy()
        scale.update(mu, actual, test[LABEL].rank(method='first').to_numpy())
        pieces.append(event_frame)
    return pd.concat(pieces, ignore_index=True)


def _brier(prob: np.ndarray, outcome: np.ndarray) -> float:
    return float(np.mean((prob - outcome) ** 2))


def probability_audit(predictions: pd.DataFrame) -> dict:
    """Brier scores vs uniform climatology, reliability bins, interval coverage."""
    ens = predictions.loc[(predictions.model == "ensemble") & predictions.p_pole.notna()].copy()
    if ens.empty:
        return {"events": 0}
    n = ens.groupby(GROUP)["driver"].transform("count").to_numpy()
    pole = (ens.actual_rank == 1).to_numpy(float)
    top3 = (ens.actual_rank <= 3).to_numpy(float)
    covered = ((ens.actual_rank >= ens.rank_p10) & (ens.actual_rank <= ens.rank_p90)).to_numpy(float)
    reliability = []
    for target, column, outcome in (("pole", "p_pole", pole), ("top3", "p_top3", top3)):
        bins = pd.cut(ens[column], [0, .02, .05, .1, .2, .35, .5, .75, 1.0], include_lowest=True)
        table = pd.DataFrame({"bin": bins, "p": ens[column], "y": outcome}).groupby("bin", observed=True).agg(
            n=("p", "size"), mean_predicted=("p", "mean"), observed=("y", "mean")).reset_index()
        table["bin"] = table["bin"].astype(str)
        table.insert(0, "target", target)
        reliability.append(table)
    rel = pd.concat(reliability, ignore_index=True)
    return {
        "events": int(ens[GROUP].drop_duplicates().shape[0]),
        "driver_rows": len(ens),
        "brier_pole": _brier(ens.p_pole.to_numpy(), pole),
        "brier_pole_uniform": _brier(1.0 / n, pole),
        "brier_top3": _brier(ens.p_top3.to_numpy(), top3),
        "brier_top3_uniform": _brier(np.minimum(3.0 / n, 1.0), top3),
        "rank_interval_nominal": 0.80,
        "rank_interval_coverage": float(covered.mean()),
        "mean_rank_interval_width": float((ens.rank_p90 - ens.rank_p10).mean()),
        "reliability": rel,
    }


def summarise(predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    by_event = evaluate(predictions)
    summary = by_event.groupby(["model", "year"], as_index=False).agg(
        events=("round", "count"), position_mae=("position_mae", "mean"),
        spearman=("spearman", "mean"), pole_hit_rate=("pole_hit", "mean"),
        top3_overlap=("top3_overlap", "mean"))
    boots = []
    for label, part in (("2024", by_event[by_event.year == 2024]),
                        ("2025", by_event[by_event.year == 2025]),
                        ("2024-2025", by_event[by_event.year >= 2024])):
        if part.empty:
            continue
        table = paired_event_bootstrap(part, baseline="latest_practice")
        table.insert(0, "window", label)
        boots.append(table)
    return by_event, summary, pd.concat(boots, ignore_index=True)


def run(raw: pd.DataFrame, *, warmup_events: int = 12, draws: int = MC_DRAWS) -> dict:
    frame = build_frame(raw)
    predictions = walk_forward(frame, warmup_events=warmup_events, draws=draws)
    evaluated = predictions.loc[predictions.year >= 2024]
    by_event, summary, bootstrap = summarise(evaluated)
    audit = probability_audit(evaluated)
    return {"frame": frame, "predictions": predictions, "by_event": by_event,
            "summary": summary, "bootstrap": bootstrap, "audit": audit}


def _plot(audit: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rel = audit["reliability"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), dpi=140)
    for ax, target in zip(axes, ("pole", "top3")):
        part = rel[rel.target == target]
        ax.plot([0, 1], [0, 1], color="#888", lw=1, ls="--")
        ax.scatter(part.mean_predicted, part.observed, s=20 + part.n * 0.6, color="#e10600")
        ax.set(xlabel="forecast probability", ylabel="observed frequency",
               title=f"P({target}) reliability", xlim=(0, 1), ylim=(0, 1))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATA_FILE)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--warmup-events", type=int, default=12)
    parser.add_argument("--draws", type=int, default=MC_DRAWS)
    args = parser.parse_args()
    if not args.dataset.exists():
        parser.error(f"Missing dataset {args.dataset}")
    result = run(pd.read_parquet(args.dataset), warmup_events=args.warmup_events, draws=args.draws)
    args.out.mkdir(parents=True, exist_ok=True)
    result["by_event"].to_csv(args.out / "events.csv", index=False)
    result["summary"].to_csv(args.out / "summary.csv", index=False)
    result["bootstrap"].to_csv(args.out / "bootstrap.csv", index=False)
    audit = result["audit"]
    audit["reliability"].to_csv(args.out / "reliability.csv", index=False)
    result["predictions"].to_parquet(args.out / "predictions.parquet", index=False)
    if audit.get("events"):
        _plot(audit, args.out / "reliability.png")
    experiment = {
        "candidate": "ensemble", "baseline": "latest_practice",
        "models": list(MODELS), "features": NUMERIC, "target": TARGET, "label": LABEL,
        "warmup_events": args.warmup_events, "mc_draws": args.draws, "seed": SEED,
        "evaluated_years": [2024, 2025],
        "events_total": int(result["frame"][GROUP].drop_duplicates().shape[0]),
        "dataset": str(args.dataset),
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "predictions_sha256": hashlib.sha256((args.out / "predictions.parquet").read_bytes()).hexdigest(),
        "audit": {k: v for k, v in audit.items() if k != "reliability"},
    }
    (args.out / "experiment.json").write_text(json.dumps(experiment, indent=2))
    print(result["summary"].sort_values(["year", "position_mae"]).to_string(index=False))
    print(result["bootstrap"].to_string(index=False))
    print(json.dumps(experiment["audit"], indent=2))


if __name__ == "__main__":
    main()
