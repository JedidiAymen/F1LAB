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
| Prior local LLM artifact (`qwen3:8b`, discovered during 2026-10-31 audit) | 24 | 33.3% | Existing citation IDs only; semantic support unscored |
| Fresh local LLM run (2026-10-31, bounded non-thinking protocol below) | 8 | **25.0%** | 100% cite existing IDs; this does not imply support |

The reference result only shows that every planted cause is identifiable from tool evidence; it says nothing about
how an LLM performs. Record the LLM row from `data/processed/agents/forecast_debug/<model>/report.md` after running.

## Limits

* Synthetic scenarios with a single planted cause each; real incidents can have several interacting causes.
* The taxonomy is closed (the agent picks one of 8 labels); open-ended diagnosis is not measured.
* Grounding checks that cited tool calls exist, not that they logically support the conclusion; read
  `traces.jsonl` to judge reasoning quality.
* Tests run without a model (scripted replies) and skip without `duckdb`; CI without the `engines` extra skips them.

## EXP-AGENT-02 — actual local Ollama evaluation, 2026-10-31

Base source `129e4b106a7ad06afec124be44095c6f091e66e2`, modified worktree on
`feat/foundation`. Installed model `qwen3:8b`, ID `500a1f067a9f` (5.2 GB);
no new model download. NVIDIA driver unavailable at audit; no GPU latency claim.
Protocol: temperature 0, context 4096, maximum 512 output tokens per reply,
two inference threads, `think=false`, 180-second HTTP timeout, six-step budget,
one seed per each of eight existing fault labels. This is a small exploratory
evaluation and differs from the earlier saved 24-case protocol; do not infer a
statistically significant regression from 33.3% to 25%.

```bash
.venv/bin/python -m f1_racelab.agents.forecast_debug.evaluate \
  --agent ollama --model qwen3:8b --seeds 1 --max-steps 6 \
  --num-ctx 4096 --num-predict 512 --timeout 180 \
  --out data/processed/agents/forecast_debug/20261031
```

Result: **2/8 correct (25%)**, invalid/undetermined labels 0/8, six incorrect
diagnoses, 24 tool calls, mean four steps, no tool errors, no nonexistent citation
IDs. Mean latency **17.4275 s**, maximum 35.39 s, total 139.42 s (includes first
case/model loading). Every case ran `list_tables`, `compare_forecasts` grouped
by race, and `config_diff`, then concluded; none used SQL to inspect versions,
features or shifted lap keys. Correct cases were config drift and the clean
control. All six remaining faults were dismissed as no material discrepancy.

Engineering trace review (not independent/blinded annotation): two conclusions
are supported by their cited observations; six are contradicted or insufficiently
investigated. For example, the regime-shift trace shows roughly +0.4 s bias in
2026 even though batch and live agree. Equality between batch/live does not imply
both are accurate. The stale-model trace shows consistent 0.12–0.15 s disagreement,
but the model never checks `model_version`; the lap-misalignment trace shows
key-coverage loss and all-row errors above 2 s. The clean control only establishes
agreement within these supplied tables, not absence of every possible fault.
The automatic `grounded_rate` name is retained for compatibility but the report
now calls it **existing citation IDs**, explicitly not logical support. Confidence
0.95 on all eight cases is poorly justified; no calibrated-confidence claim.

Committed, small, synthetic-data evidence for independent review and fresh-clone
demo: `docs/research/evidence/forecast_debug_20261031/{results.json,traces.jsonl,report.md}`.
SHA-256: results `1bcb6aa3bd68101acf7a149f72e7e31c6cd48d98c045d4698bc46f0c25798e7c`;
traces `736f42b7c066d87713271b8919f50a293a324d4c5e6ccf3e9e8796f7ab1c05fa`.
No real telemetry, protected media or provider data are bundled in this sample.

`GET /api/v1/research/agent-evaluation` reads the saved run (local artifact,
or bundled fallback). The Research & reliability UI selects an incident,
shows expected/diagnosed causes, explanation, cited IDs, tool arguments,
examined observations and source hashes. It executes **no LLM calls or SQL**.
The model's internal `thought` field is omitted from the API projection.

## SQL boundary improvements

`tools.ForecastTools.run_sql` now parses statements using DuckDB and requires
one SELECT; the existing conservative keyword guard remains. Queries have a
12,000-character limit, one engine thread, 128 MB engine memory, no temp-file
spill, no external access or automatic extension install/load, and locked
configuration. A two-second cooperative interrupt covers parsing/execution/fetch;
cancelled timers are joined before the next query so they cannot interrupt it.
Only **51 rows** are fetched to determine whether a 50-row response was truncated,
instead of materializing the full query into pandas. At most 32 uniquely named
columns and 1,000 characters per string cell are returned. Truncated `row_count`
is a lower bound, explicitly marked `row_count_is_exact=false`.

Tests execute a billion-row range with bounded fetch, interrupt an expensive
aggregate and verify connection recovery, reject external file/network readers,
multiple statements, oversized queries and duplicate columns. Evaluations close
each scenario connection. Memory limits do not cover every Python/engine
allocation, and interruption is cooperative: this is defense in depth for a
local read-only agent, **not** a multitenant hostile-code sandbox. Use a separate
resource-limited process/container before exposing arbitrary public SQL.
References: [DuckDB security controls](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview),
[Python parsing, interrupt and bounded fetch APIs](https://duckdb.org/docs/stable/clients/python/reference/).

Remaining: multi-fault, incomplete/ambiguous evidence and unseen-taxonomy
scenarios; richer evidence-support annotation; transport-failure-resilient
checkpointing; an actual read-only live warehouse connector. No production-readiness
or improvement over the scripted checklist is claimed.
