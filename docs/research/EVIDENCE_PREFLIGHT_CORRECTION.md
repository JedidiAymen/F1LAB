# Evidence preflight correction — 2026-11-01

PR #1, branch `feat/agent-incident-triage-review`, starting head
`5a95ba26395cf8f7395a8396297409db17ebe02e`. Correctness patch, not a new LLM
experiment or a causal classifier. No merge/promotion authorized.

## Implemented contracts

`triage.summarize` schema 2 compares only known finite values. Unknown model
identities, missing columns/values, blank strings, NaN/infinity and invalid
numeric feature text produce explicit coverage counts. Two unknown identities
never become a known disagreement. Prediction mean/max gaps use finite pairs
only; pair counts and input-quality denominators are emitted. Tyre age is
numeric (lap units); compound is categorical and green eligibility is a flag.
Feature mismatches concern observed comparable pairs; unknown pairs are neither
matches nor mismatches. Missing core join keys fail with a clear contract error;
duplicate keys still reject rather than multiply joins. Inputs remain unchanged.

`triage.config_evidence` separates known differences, unknown values and
conflicts. The warehouse diagnostic schema expects model_version,
green_laps_only and output_unit; that is an explicit schema expectation, not an
inferred universal provider configuration. A missing key, table, pipeline column
or entire pipeline yields unknown evidence. Conflicting duplicate declarations
remain conflicting; the tool does not pick a convenient value.
`tools.config_diff` uses the same policy instead of an inner SQL join that hid
missing metadata; its existing `differences` key remains compatible and gains
unknown/conflict/coverage fields. The SQL execution boundary is unchanged.

Season bias uses observed finite targets and explicit green flags only. All
outputs remain descriptive; no root-cause label or calibrated confidence is
returned. Alignment is a clue, not a causal assertion. A clean difference list
without coverage is insufficient evidence of health.

## Evidence and reproduction

Existing eight single-fault fixtures pass, as do missing/unknown/conflicting
metadata, nonfinite predictions, numeric/categorical feature absence, input
immutability, duplicate rejection and actual bounded DuckDB tool integration.
Focused suite: 57 passed in 5.27 s. Clean seed-1 serialized summary is 2,095
characters, within the existing 4,000-character observation budget. This size
is a nominal fixture observation, not a universal bound for arbitrary tables.

```bash
PYTHONPATH=/tmp/f1lab-pr1-review/src /home/aymmzn/Documents/projects/F1LAB/.venv/bin/pytest -q tests/test_forecast_triage.py tests/test_forecast_debug_agent.py tests/test_forecast_sql_limits.py -W ignore
/home/aymmzn/Documents/projects/F1LAB/.venv/bin/ruff check src tests scripts
/home/aymmzn/Documents/projects/F1LAB/.venv/bin/mypy src/f1_racelab
```

The explicit source path isolates this review checkout from the owner's shared
editable environment; a normal checkout/venv can use the usual project commands.
Baseline branch full verification: 280 passed/19 skipped in 26.13 s (local
artifacts absent in isolated checkout). Root PR #3 baseline: 308 passed32.54 s,
mypy100; web lint/build and16 units pass. All three original PR CI sets were green.

No model invocation/training, no new accuracy or semantic-support measurement.
PR #3's historical candidate remains exactly 5a95ba2 and 6/16; its preserved
artifacts must not be relabeled as evaluation of this correction. The old 2/8
LLM and 200/200 scripted reference remain separate. Corrected preflight needs
a separately frozen hybrid/LLM evaluation before any promotion.

## Independent PR review status

PR #1: these missing-data objections are corrected; broader ambiguous/multi-fault
LLM validation remains outstanding. PR #3: frozen evidence is retained, including
5/16 supported explanations per arm; ID existence does not establish support.
PR #4: persistence5.2198 s beats standard TCN8.1130 s; no promotion. Its
no-context variant removes prior-context inputs from the neural head **but still
adds its correction to last-lap persistence**, so the complete forecast is not
context-free. Model/data/source integrity and serving/UI were previously checked;
new source-quality audit remains necessary before expanded research.

All PRs remain independent/draft/unmerged. This patch is on PR #1's own branch;
no unmerged implementation is silently copied into foundation or the other PRs.

Final local PR #1 verification: **298 passed,19 skipped in27.25 s**, Ruff
clean, mypy99 files. Skips are explicit absent optional/local-artifact tests in
this isolated older-base checkout; they are not passes. No frontend source
changed. Existing frontend CI was green before edits; new PR CI will rerun
Python/web/clean Compose. Known placeholder identity strings are also unknown.
The corrected tool output is not covered by the historical6/16 evaluation.
