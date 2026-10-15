# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.6
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # F1LAB — 03 Historical form ablation
#
# **Question:** do driver/team historical features improve ranking beyond FP3 and current-weekend practice?
#
# Train **2022–23** → choose using **2024** → untouched test **2025**. No retraining or feature decisions made from test numbers.

# %%
import json
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

root = Path.cwd()
if root.name == "notebooks": root = root.parent
results = root / "data" / "processed" / "qualifying_ablation"
assert (results / "validation.csv").exists(), "Run python -m f1_racelab.models.qualifying_ablation first"
val = pd.read_csv(results / "validation.csv")
test = pd.read_csv(results / "test.csv")
coverage = pd.read_csv(results / "feature_coverage.csv")
sample_coverage = pd.read_csv(results / "sample_coverage.csv")
validation_delta = pd.read_csv(results / "validation_bootstrap.csv")
test_delta = pd.read_csv(results / "test_bootstrap.csv")
experiment = json.loads((results / "experiment.json").read_text())
assert experiment["selection_year"] == 2024 and experiment["held_out_year"] == 2025
print("Dataset:", experiment["dataset"])
print("Practice feature set:", experiment["feature_set"])
print("Eligible driver rows by year:")
display(sample_coverage.groupby("year")[["source_rows", "evaluated_rows"]].sum())

# %% [markdown]
# ## 1 — Choose based on validation only
#
# The model with the **lowest average position MAE** in 2024 is selected. The final test is not used to tune.

# %%
display(val.sort_values("position_mae"))

# %% [markdown]
# ## 2 — Held-out 2025 test
#
# These numbers answer whether historical form improved performance on unseen, later events. Do **not** retune the same held-out set after inspecting it.

# %%
display(test.sort_values("position_mae"))

# %% [markdown]
# ## 3 — Compare visualization

# %%
compare = val[["model", "position_mae"]].merge(test[["model", "position_mae"]], on="model", suffixes=("_validation", "_test"))
plot = compare.set_index("model")["position_mae_validation position_mae_test".split()].rename(
    columns={"position_mae_validation": "2024 validation", "position_mae_test": "2025 held-out test"}
)
ax = plot.plot(kind="bar", figsize=(11,5), title="Average qualifying-position MAE — lower is better")
ax.set_ylabel("Absolute position error")
ax.set_xlabel("Model")
plt.xticks(rotation=25)
plt.tight_layout()
plt.savefig(results / "mae_validation_test.png", dpi=160)
plt.show()

# %% [markdown]
# ## 3b — Paired event differences against FP3
#
# A negative MAE delta is better than FP3. The interval resamples entire Grand
# Prix weekends, preserving dependence among drivers within the same event.

# %%
display(validation_delta.sort_values("mean_delta"))
display(test_delta.sort_values("mean_delta"))

# %% [markdown]
# ## 4 — Is historical feature data actually available?
#
# Missingness must be audited before we claim that teammate features were tested.

# %%
display(coverage.sort_values("fraction_available"))
print("Team label coverage:", experiment["team_label_coverage"])

# %% [markdown]
# ## 5 — Race-level performance
#
# Check whether one unusual race explains the aggregate result.

# %%
events = pd.read_csv(results / "test_events.csv")
errors = events.pivot(index="event", columns="model", values="position_mae")
display(errors.sort_index())

# %% [markdown]
# ## Questions
#
# - Did either historical model beat FP3 on validation? On test?
# - Which features are missing often? Was team metadata enriched?
# - Does the winner fail on specific circuits?
# - Could current practice better predict Q1 than final Q3 ranking?
# - Should the next step be *better data* rather than a larger model?
