# Neural Qualifying extension (EXPLORATORY)

Status label: **exploratory**. The 2026 failure of the existing ensemble was already known when this was written, so 2026 is not a fresh confirmatory test. Only rounds that finish after commit of `models/neural_qualifying.py` can be treated as confirmatory later.

## Predeclared design (`src/f1_racelab/models/neural_qualifying.py`)
* `neural_mlp`: 5 seeds (42, 7, 123, 2024, 99) of a 2x64 GELU MLP (dropout 0.2, AdamW, 80 full-batch epochs, Huber loss) on the existing features and target, fitted only on earlier events.
* `ensemble_regime`, `neural_regime`: shrink toward the latest-practice gap by w = n/(n+6), n = earlier events in the same era (2022-2025 vs 2026+).
* Same 48 events (2024-2026), same walk-forward and paired event bootstrap as the existing ensemble. Command: `uv sync --extra dl && uv run python -m f1_racelab.models.neural_qualifying`; artifacts under git-ignored `data/processed/neural_qualifying/`.

## Results (real data; position MAE, lower is better; delta vs latest practice [95% CI over events])
| Window | ensemble | ensemble_regime | neural_mlp | neural_regime |
|---|---|---|---|---|
| 2024 (18) | -0.311 [-0.829, 0.098] | -0.329 [-0.680, -0.029] | -0.320 [-0.872, 0.085] | -0.387 [-0.899, -0.004] |
| 2025 (18) | -0.237 [-0.440, -0.045] | -0.253 [-0.407, -0.109] | -0.213 [-0.417, -0.029] | -0.196 [-0.364, -0.050] |
| 2026 (12) | +0.052 [-0.030, 0.136] | -0.017 [-0.116, 0.076] | +0.110 [-0.016, 0.248] | -0.040 [-0.129, 0.045] |
| pooled (48) | -0.192 [-0.404, -0.015] | -0.223 [-0.372, -0.092] | -0.173 [-0.399, 0.010] | -0.228 [-0.433, -0.065] |

Direct paired comparison against the existing ensemble (`bootstrap_vs_ensemble.csv`): every interval includes zero in every window (pooled: ensemble_regime -0.030 [-0.104, 0.056], neural_mlp +0.020 [-0.060, 0.105], neural_regime -0.036 [-0.108, 0.039]).

## Interpretation
* The neural MLP is not better than the existing ensemble; in 2026 it is slightly worse (+0.110).
* Regime shrinkage moves 2026 from slightly worse than latest practice to roughly equal (-0.017 and -0.040, both intervals include zero). It removes the loss but creates **no gain**: in 2026 nothing here beats latest practice.
* The variants also look slightly better in 2024-2025. That is general shrinkage toward the latest-practice gap (the models are somewhat over-dispersed), not evidence of a regime effect; it is not significant against the ensemble.
* Conclusion: no neural or regime-aware variant is established as an improvement. Keep the ensemble as the served model; revisit with post-commit 2026 rounds.
