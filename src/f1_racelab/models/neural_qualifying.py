"""Neural + regime-aware qualifying extension (EXPLORATORY).

Predeclared before running (fixed constants, no tuning on any evaluated event):

* ``neural_mlp``: 5-seed average of a 2x64 MLP (dropout 0.2, AdamW, 80 full-batch epochs, Huber loss) on the same
  features and target as the existing models, fitted on strictly earlier events only.
* ``ensemble_regime`` / ``neural_regime``: shrink the model's gap forecast toward the latest-practice gap by
  ``w = n / (n + K)`` where ``n`` is the number of earlier events in the same regulation era (2022-2025 vs 2026+)
  and ``K = 6``. The first event of a new era is therefore pure latest practice.

Status label: **exploratory**. The 2026 failure of the existing ensemble was already known when this was written,
so 2026 here is not a fresh confirmatory test; only rounds that finish after this file's commit could be.

Command: ``uv run python -m f1_racelab.models.neural_qualifying`` (needs ``uv sync --extra dl``).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from f1_racelab.models import qualifying_walkforward as wf
from f1_racelab.models.qualifying_backtest import scored_positions

SEEDS = (42, 7, 123, 2024, 99)
SHRINK_K = 6
NEW_ERA_FROM = 2026
OUT = wf.ROOT / "data/processed/neural_qualifying"
MODELS = ("latest_practice", "ensemble", "ensemble_regime", "neural_mlp", "neural_regime")


def era(year: int) -> int:
    return int(year >= NEW_ERA_FROM)


def shrink_weight(n_in_era: int, k: int = SHRINK_K) -> float:
    return n_in_era / (n_in_era + k)


def _mlp_predict(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    import torch
    from torch import nn

    imputer, scaler = SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler()
    x = scaler.fit_transform(imputer.fit_transform(train[wf.NUMERIC]))
    xt = scaler.transform(imputer.transform(test[wf.NUMERIC]))
    y = train[wf.TARGET].to_numpy(np.float32)
    outputs = []
    for seed in SEEDS:
        torch.manual_seed(seed)
        net = nn.Sequential(nn.Linear(x.shape[1], 64), nn.GELU(), nn.Dropout(0.2), nn.Linear(64, 64), nn.GELU(),
                            nn.Dropout(0.2), nn.Linear(64, 1))
        opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=1e-2)
        xa, ya = torch.as_tensor(x, dtype=torch.float32), torch.as_tensor(y)
        for _ in range(80):
            net.train()
            loss = nn.functional.huber_loss(net(xa).squeeze(-1), ya, delta=1.0)
            opt.zero_grad()
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            outputs.append(net(torch.as_tensor(xt, dtype=torch.float32)).squeeze(-1).numpy())
    return np.mean(outputs, axis=0)


def run(raw: pd.DataFrame, *, warmup_events: int = 12) -> dict:
    frame = wf.build_frame(raw)
    events = list(frame[wf.GROUP].drop_duplicates().itertuples(index=False, name=None))
    order = {event: i for i, event in enumerate(events)}
    index = pd.Series([order[(y, r)] for y, r in zip(frame.year, frame["round"], strict=True)], index=frame.index)
    pieces = []
    for i in range(warmup_events, len(events)):
        year = events[i][0]
        if year < wf.EVALUATION_START_YEAR:
            continue
        train, test = frame.loc[index < i], frame.loc[index == i]
        scores = wf._predict_event(train, test)
        mlp = _mlp_predict(train, test)
        n_in_era = sum(1 for y, _ in events[:i] if era(y) == era(year))
        w = shrink_weight(n_in_era)
        latest = scores["latest_practice"].to_numpy()
        candidates = {"latest_practice": latest, "ensemble": scores["ensemble"].to_numpy(),
                      "ensemble_regime": w * scores["ensemble"].to_numpy() + (1 - w) * latest,
                      "neural_mlp": mlp, "neural_regime": w * mlp + (1 - w) * latest}
        for name, score in candidates.items():
            piece = scored_positions(test, score, name)
            piece["shrink_weight"] = w
            pieces.append(piece)
    predictions = pd.concat(pieces, ignore_index=True)
    by_event, summary, bootstrap = wf.summarise(predictions)
    return {"predictions": predictions, "by_event": by_event, "summary": summary, "bootstrap": bootstrap,
            "events_scored": int(predictions[wf.GROUP].drop_duplicates().shape[0])}


def main() -> None:
    result = run(pd.read_parquet(wf.DATA_FILE))
    OUT.mkdir(parents=True, exist_ok=True)
    result["predictions"].to_parquet(OUT / "predictions.parquet", index=False)
    result["summary"].to_csv(OUT / "summary.csv", index=False)
    result["bootstrap"].to_csv(OUT / "bootstrap.csv", index=False)
    (OUT / "manifest.json").write_text(json.dumps({
        "status": "exploratory", "models": list(MODELS), "seeds": list(SEEDS), "shrink_k": SHRINK_K,
        "new_era_from": NEW_ERA_FROM, "events_scored": result["events_scored"],
        "dataset": str(Path(wf.DATA_FILE).name)}, indent=2))
    pd.set_option("display.width", 200)
    print(result["summary"].round(3).to_string(index=False))
    print(result["bootstrap"].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
