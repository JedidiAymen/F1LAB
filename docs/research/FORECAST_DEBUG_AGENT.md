# Forecast-debugging agent: batch vs live discrepancies

Goal: an LLM agent that investigates why batch (nightly) and live (on-demand) forecasts disagree, using
**read-only tools**, and proposes the most likely **root cause with cited evidence**; plus an **evaluation framework**
that measures how often it finds the correct cause on **known issues**.

## Pieces

| Module | Role |
|---|---|
| `agents/forecast_debug/scenarios.py` | Synthetic warehouse shaped like F1Lab next-lap pace forecasts (`laps`, `features_batch/live`, `batch_forecasts`, `live_forecasts`, `model_registry`, `pipeline_config`) with **one planted root cause** per scenario. The seed randomizes magnitude and affected races; ground truth is never written to a table. |
| `agents/forecast_debug/tools.py` | Read-only tools on in-memory DuckDB: `list_tables`, `describe_table`, `run_sql` (single SELECT/WITH only, write keywords rejected, external file access disabled, 50-row cap), `compare_forecasts` (batch vs live per group: coverage, matched keys, mean \|live-batch\|, bias vs actuals), `config_diff`. |
| `agents/forecast_debug/agent.py` | JSON-protocol agent loop: action `{"action", "args"}` or final `{"root_cause", "evidence", "explanation", "confidence"}`. Each tool call gets an id (`t1`, `t2`, ...); cited ids that were never produced are dropped, unknown labels become `invalid_label`, and a step budget ends in `undetermined`. |
| `agents/forecast_debug/llm.py` | `OllamaChat` (any local model, e.g. `qwen3:8b`), `ScriptedChat` (tests), robust JSON extraction (handles `<think>` blocks and code fences). |
| `agents/forecast_debug/reference.py` | Deterministic checklist using only the same tools. It is a **solvability check**, written knowing the taxonomy, not a competitor. |
| `agents/forecast_debug/evaluate.py` | Runs scenarios x seeds; reports root-cause accuracy (overall and per label), correct-and-grounded rate, grounded-answer rate, undetermined/invalid rate, steps, tool errors and confusions. Writes `results.json`, `report.md`, `traces.jsonl`. |

## Root-cause taxonomy (8)

`regime_shift`, `stale_model_version`, `feature_skew`, `missing_live_data`, `unit_mismatch`, `config_drift`,
`lap_misalignment`, and the control `no_material_discrepancy`. `regime_shift` reproduces the pattern found in the real
2026 forecast review (batch and live agree, both biased against actuals in the new season).

## Commands

```
uv sync --extra engines                                   # duckdb
uv run python -m f1_racelab.agents.forecast_debug.evaluate --agent reference --seeds 25
ollama pull qwen3:8b
uv run python -m f1_racelab.agents.forecast_debug.evaluate --agent ollama --model qwen3:8b --seeds 3
```

## Results

| Solver | Scenarios | Root-cause accuracy | Grounded |
|---|---:|---:|---:|
| Reference checklist (solvability check) | 200 (8 causes x 25 seeds) | 100% | 100% |
| LLM agent (`qwen3:8b` via Ollama) | 24 | _not yet run_ | _not yet run_ |

The reference result only shows that every planted cause is identifiable from tool evidence; it says nothing about
how an LLM performs. Record the LLM row from `data/processed/agents/forecast_debug/<model>/report.md` after running.

## Limits

* Synthetic scenarios with a single planted cause each; real incidents can have several interacting causes.
* The taxonomy is closed (the agent picks one of 8 labels); open-ended diagnosis is not measured.
* Grounding checks that cited tool calls exist, not that they logically support the conclusion; read
  `traces.jsonl` to judge reasoning quality.
* Tests run without a model (scripted replies) and skip without `duckdb`; CI without the `engines` extra skips them.
