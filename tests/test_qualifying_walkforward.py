import numpy as np
import pandas as pd

from f1_racelab.models import qualifying_walkforward as wf


def synthetic(events: int = 16, drivers: int = 10, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(events):
        year, rnd = 2022 + e // 8, e % 8 + 1
        for k in range(drivers):
            pace = k * 0.12 + rng.normal(0, 0.04)
            row = {
                "year": year, "round": rnd, "event": f"GP{rnd}", "driver": f"D{k:02d}",
                "team": f"T{k // 2}", "q1_gap_pct": max(pace + rng.normal(0, 0.03), 0.0),
                "final_position": k + 1, "fp3_best_seconds": 80 + pace,
            }
            for i, fp in enumerate(("fp1", "fp2", "fp3")):
                gap = max(pace + rng.normal(0, 0.05) + 0.02 * (2 - i), 0.0)
                row[f"{fp}_gap_pct"], row[f"{fp}_rank"] = gap, float(k + 1)
            row["fp1_to_fp3_improvement_pct"] = row["fp1_gap_pct"] - row["fp3_gap_pct"]
            row["fp2_to_fp3_improvement_pct"] = row["fp2_gap_pct"] - row["fp3_gap_pct"]
            rows.append(row)
    return pd.DataFrame(rows)


def test_context_features_use_same_weekend_practice_and_prior_track_history():
    raw = synthetic()
    raw.loc[(raw.year == 2023) & (raw["round"] == 1), "q1_gap_pct"] = 9.0
    frame = wf.build_frame(raw)
    first = frame[(frame.year == 2022) & (frame["round"] == 1)]
    assert first.track_history_q1_gap.isna().all()  # nothing earlier at this circuit
    # 2023 R1 carries 2022 R1 history, never its own (sentinel) target.
    later = frame[(frame.year == 2023) & (frame["round"] == 1)]
    earlier = first.set_index("driver").q1_gap_pct
    assert np.allclose(later.set_index("driver").track_history_q1_gap.sort_index(), earlier.sort_index())
    # Team-best is the minimum over the team's drivers in that weekend.
    group = later.groupby("team").latest_gap.min()
    assert np.allclose(later.set_index("team").team_best_latest_gap.groupby(level=0).first(), group)


def test_event_predictions_ignore_the_evaluated_event_labels():
    frame = wf.build_frame(synthetic())
    events = list(frame[wf.GROUP].drop_duplicates().itertuples(index=False, name=None))
    year, rnd = events[-1]
    mask = (frame.year == year) & (frame["round"] == rnd)
    train, test = frame.loc[~mask], frame.loc[mask]
    baseline = wf._predict_event(train, test)
    poisoned = test.assign(q1_gap_pct=99.0, final_position=test.final_position[::-1].to_numpy())
    again = wf._predict_event(train, poisoned)
    pd.testing.assert_frame_equal(baseline, again)


def test_monte_carlo_probabilities_are_proper_distributions():
    mu = np.array([0.0, 0.1, 0.2, 0.5, 0.9])
    mc = wf.monte_carlo_ranks(mu, np.full(5, 0.15), draws=2000)
    assert np.isclose(mc["p_pole"].sum(), 1.0)
    assert np.isclose(mc["p_top3"].sum(), 3.0)
    assert mc["p_pole"].argmax() == 0 and mc["expected_rank"].argmin() == 0
    assert (mc["rank_p10"] <= mc["rank_p90"]).all()
    again = wf.monte_carlo_ranks(mu, np.full(5, 0.15), draws=2000)
    assert all(np.array_equal(mc[k], again[k]) for k in mc)  # seeded


def test_residual_scale_is_causal_and_needs_history():
    scale = wf.ResidualScale()
    assert not scale.ready()
    rng = np.random.default_rng(0)
    for _ in range(wf.MIN_RESIDUAL_EVENTS):
        mu = np.sort(rng.random(8))
        scale.update(mu, mu + rng.normal(0, 0.1, 8), np.arange(1, 9))
    assert scale.ready()
    sigma = scale.sigma(np.array([0.0, 1.0]))
    assert (sigma > 0).all() and sigma[1] > sigma[0]  # slower cars less predictable


def test_walk_forward_end_to_end_beats_chance_and_reports_audit():
    result = wf.run(synthetic(events=20), warmup_events=8, draws=300)
    pred = result["predictions"]
    assert set(pred.model) == set(wf.MODELS)
    # Warm-up events are never scored.
    assert pred.event_index.min() == 8
    ens = pred[(pred.model == "ensemble") & pred.p_pole.notna()]
    assert len(ens) > 0
    per_event = ens.groupby(wf.GROUP).p_pole.sum()
    assert np.allclose(per_event, 1.0)
    # Synthetic order is nearly deterministic, so the ensemble should do well.
    summary = result["summary"].set_index(["model", "year"])
    assert summary.loc[("ensemble", 2024), "position_mae"] < 3.0
