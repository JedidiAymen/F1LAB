# Forecast Debug Agent — fixed-protocol paired evaluation

Issue [#2](https://github.com/JedidiAymen/F1LAB/issues/2), section A. This work
uses a separate branch and PR targeting `feat/foundation`. PR #1 stays unmerged.

## Review completed before evaluation

Reviewed draft [PR #1](https://github.com/JedidiAymen/F1LAB/pull/1), exact head
`5a95ba26395cf8f7395a8396297409db17ebe02e`, five changed files / 229 additions.
[CI run 41225692954](https://github.com/JedidiAymen/F1LAB/actions/runs/41225692954)
passed Python, web and clean-data Compose jobs. Isolated detached checkout
`/tmp/f1lab-pr1-review` imported its own source explicitly; focused tests:

```bash
PYTHONPATH=/tmp/f1lab-pr1-review/src .venv/bin/pytest -q \
  /tmp/f1lab-pr1-review/tests/test_forecast_triage.py \
  /tmp/f1lab-pr1-review/tests/test_forecast_debug_agent.py \
  /tmp/f1lab-pr1-review/tests/test_forecast_sql_limits.py -W ignore
```

43 passed in 2.87 s. Input immutability, duplicate-key rejection, finite output,
eight complete single-fault scenarios and read-only SQL integration pass.
There is no LLM improvement evidence in PR #1 itself; it correctly preserves 2/8.
No approval, comment or merge was submitted on the owner's review PR.

Two independently reproduced review findings matter for incomplete evidence:

1. **Unknown model versions are counted as disagreements.** In `triage.py:53`,
   comparing missing values with `!=` counts all 3,972 matched rows as version
   disagreements when both version columns are NaN. Version sets are both empty.
   Unknown identity should remain unknown, rather than becoming positive evidence
   that two known model identities differ. This can mislead a diagnostic agent.
2. **Missing configuration keys disappear.** `triage.py:58` drops rows without
   both pipeline values. Removing live `green_laps_only` from a clean seed-4
   warehouse yields `config_differences=[]`. A consumer cannot distinguish absent
   metadata from equal known configuration. If a pipeline column is entirely
   missing, this path can raise instead of returning partial evidence.

These do not change the eight complete-data generator cases, but prevent treating
the tool as validated for incomplete evidence. They remain findings on the
unchanged proposed revision, not silently fixed inputs to this comparison.

## Protocol frozen before model calls

- Baseline source: `5cdac66677e6abb513f84e3ede5f74dd74d00bb6`; candidate:
  PR #1 head above. The baseline agent/tools are unchanged from the earlier
  2/8 study. Candidate changes both prompt and available `incident_checks` tool;
  this comparison cannot isolate which of those changes causes any difference.
- Same eight existing fault families, synthetic seeds **1 and 4**, 16 paired
  cases / 32 model investigations. Seed 1 is a replication; seed 4 is another
  draw from known families, not an unseen failure mechanism or a fresh real-data
  holdout. Scenario source SHA-256 must match between implementations:
  `aa17e40530b4adc9433a80cfadaca70320c68d1bcdb54a8c9c74a17ac663b53c`.
- Same installed `qwen3:8b`, full digest
  `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.
  No download or fine-tuning. Temperature 0, explicit model seed 42,
  `think=false`, 4096 context, 512 output tokens, two inference threads,
  six-step budget, 180-second HTTP timeout and 240-second worker wall limit.
  The old saved run did not explicitly set a model seed, so it is preserved
  separately rather than substituted for a new paired baseline.
- One shared warmup, excluded from scored latency. Arm order alternates across
  cases. Each arm imports its own frozen source in a separate process using the
  same Python environment, avoiding Python module-cache contamination. Generated
  table fingerprints must match within each pair. Relevant source changes or a
  changed model digest invalidate resume; completed cases are never overwritten.
- Capture per-case diagnoses, examined observations, model replies, invocation
  times, source/model/data fingerprints, tool errors, false citation IDs,
  invalid/undetermined answers, false no-discrepancy decisions and transport/
  worker failures. Failures remain in the denominator. Atomic case checkpoints
  permit resuming an interrupted run with the same protocol.
- Report root-cause accuracy and paired accuracy change, with seed-42 5,000-draw
  bootstrap over **fault families**, keeping both seeds in each resampled family.
  Eight families are a small, known taxonomy; no broad generalization claim.
  Latency includes the agent/tool loop and excludes Python process startup;
  worker wall time is separately recorded. No causal speed claim from one run.
- Citation-ID existence is reported separately from support. After inference,
  review each explanation against its **cited** observations and record
  `supported`, `contradicted` or `insufficient`, with specific evidence and a
  reason. This engineering adjudication is inspectable, not a blinded independent
  human annotation study or an automatic semantic-entailment guarantee.

Actual execution is reported below. Existing 2/8 LLM and scripted
200/200 solvability results remain untouched and non-equivalent. Multi-fault,
ambiguous/incomplete evidence and real forecast-manifest investigations are
separate subsequent gates.

Primary implementation references: [Ollama API specification](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml)
and [Ollama API options](https://github.com/ollama/ollama/blob/main/docs/api.md).

## Model and dataset card

Inference-only use of the already installed quantized Qwen3 8B; no parameters
were trained or fine-tuned. The upstream [Qwen3-8B card](https://huggingface.co/Qwen/Qwen3-8B)
and [license](https://huggingface.co/Qwen/Qwen3-8B/blob/main/LICENSE) identify
Apache-2.0. Model weights are not redistributed. Ollama's installed digest,
engine version, source hashes, dependency versions and CPU count are captured in
`protocol.json`; this local execution does not establish GPU performance.

The dataset is generated solely by the repository's `scenarios.py`: eight known
single-fault families, seeds 1/4, 4,320 lap records per warehouse before forecast
filtering. There are no broadcast assets, actual racing telemetry or external
dataset records in the publication bundle. No third-party dataset license is
assigned to these generated fixtures. Raw tool-call message logs remain ignored
in the local run directory; the committed result contains the model's diagnosis
and exact tool observations. The public API projects observations and explanations
without exposing the model's intermediate thought field.

Intended use: research regression comparison and manual incident replay. Not
validated for operational diagnosis, unseen faults, incomplete metadata, multiple
simultaneous causes or production incident response. Source hashes/checksums
detect accidental mismatches; they are not cryptographic publisher signatures.

## Reproduction

Use a Linux host with Python/uv, the installed matching Ollama model and enough
RAM for Qwen3 8B. The UI replay needs neither Ollama nor raw F1 data. Do not run
another model workload during timing. The source checkouts must stay frozen:

```bash
uv sync --frozen --dev --extra engines
git worktree add --detach /tmp/f1lab-agent-baseline 5cdac66677e6abb513f84e3ede5f74dd74d00bb6
git worktree add --detach /tmp/f1lab-agent-candidate 5a95ba26395cf8f7395a8396297409db17ebe02e
.venv/bin/python -m f1_racelab.agents.forecast_debug.paired \
  --baseline-root /tmp/f1lab-agent-baseline \
  --candidate-root /tmp/f1lab-agent-candidate \
  --out data/processed/forecast_debug/paired_reproduction
# Add --resume only with the exact same runner, source/model and protocol.
.venv/bin/pytest -q tests/test_agent_paired.py tests/test_agent_paired_service.py -W ignore
cd apps/web
npm run lint && npm run test:unit && npm run build
npx playwright test e2e/research.spec.ts
```

The runner imports each arm in a subprocess and records the actual imported
file path. The original baseline used the repository at its frozen 5cdac66 HEAD,
and the candidate used `/tmp/f1lab-pr1-review`; those local paths are execution
evidence, not a portable path requirement. Numeric determinism across Ollama
versions/hardware is not guaranteed. Adjudications are explicit inspectable
engineering labels; a rerun requires fresh review of its actual cited evidence.

Timing caveat: this was an ordinary shared desktop, with concurrent software
checks during part of the run, not an isolated inference benchmark. Near the
final controls, `free -h` reported 15 GiB RAM, about 2.0 GiB available and 9.3 GiB
swap used. Preserve slow cases/timeouts instead of silently dropping or rerunning
them. Arm order alternates but does not eliminate system-load confounding.

## Actual results — EXP-AGENT-PAIRED-01

Completed 32/32 actual local investigations, no worker/transport failure. Exact
protocol identity `f7cd231e07c20471f0330acc713a4cfa14b966ef203304c1617aaff519c1908d`,
Ollama 0.31.1, Python 3.12.13, DuckDB 2.0.0, numpy 2.5.3, pandas 2.3.3,
httpx 0.28.1. Output bundle: `evidence/forecast_debug_paired_20261031/`.

| Measurement | Foundation | PR #1 |
|---|---:|---:|
| Correct root causes | 6/16 (37.5%) | 6/16 (37.5%) |
| False no-material-discrepancy | 8 | 7 |
| Undetermined / invalid label | 0 / 0 | 3 / 0 |
| Tool invocations / errors | 47 / 0 | 41 / 2 |
| Mean / p95 loop latency (s) | 16.2647 / 22.9168 | 16.6963 / 34.7472 |
| Nonexistent citation IDs | 0 | 0 |
| Supported / contradicted / insufficient explanations | 5 / 6 / 5 | 5 / 7 / 4 |

Paired accuracy change **0.0 percentage points**, 95% fault-family bootstrap
**[−37.5, +37.5] points**. This does not establish improvement or equivalence.
Known-family seed-1 accuracy is 3/8 in both arms, seed-4 3/8 in both. This is a
new fixed-seed paired baseline, not replacement of the earlier 2/8 result.

| Fault family (two cases each) | Foundation correct | PR #1 correct |
|---|---:|---:|
| Regime shift | 0/2 | 0/2 |
| Stale version | 0/2 | 2/2 |
| Feature skew | 0/2 | 0/2 |
| Missing live data | 2/2 | 0/2 |
| Unit mismatch | 0/2 | 0/2 |
| Configuration drift | 2/2 | 2/2 |
| Lap misalignment | 0/2 | 0/2 |
| Clean control | 2/2 | 2/2 |

PR #1 trades missing-data successes for version successes. It used fewer tool
calls overall (2.5625 versus 2.9375 per case), but did not improve accuracy;
correct cases per tool invocation are 6/41 versus 6/47, a descriptive ratio,
not a quality promotion criterion. Three step-budget exhaustions occurred for
feature skew seed 1 and both misalignments. Two SQL calls hallucinated absent
`forecast_comparison`/`forecasts` tables and returned bounded catalog errors.

Zero nonexistent IDs concealed substantial semantic failures. Examples:
PR #1 claimed no missing-data evidence despite 668/661 batch-only keys; denied
feature skew despite 4,320 tyre-age mismatches; described 10,061/15,005-second
mean forecast gaps as expected noise. Both implementations dismissed the 2026
bias shift. Correct configuration labels can also overstate causal support:
one PR #1 explanation wrongly treated similar green-lap bias as corroboration
of a filter difference. All 32 engineering verdicts include exact cited IDs and
case-specific reasons. A supported verdict concerns material claims in that
explanation, not proof that every possible cause has been excluded.

The PR #1 clean-control seed-1 latency was 63.84 s during observed memory
pressure; it is retained. No inference speed gain is claimed. No model was
trained, no real incident was diagnosed, and no PR was merged. The review
findings and equal aggregate score justify further investigation rather than
promotion. Next gates: incomplete/multiple/ambiguous faults with abstention,
actual real-manifest evidence, then a separately frozen prompt/tool revision.

Published SHA-256:

- Protocol file: `8d39310222122d6c73e3923fa5b9d13d42d7ea6e8f90b11d7e1a3175ba4be350`
- Results: `dd0b5cc7601d07e84ee3dc76f1252f0c1e7a96850877e32bcf6aed479620c97e`
- Adjudications: `d22d67e3b9e1a168ce2b6a0984bf2957f166e1c454870460b9df224665791051`

`GET /api/v1/research/agent-paired` verifies checksums, protocol/result binding,
recomputes paired scores and binds every annotation to the result hash. It
returns 503 on invalid evidence and has no query/model execution endpoint.
The existing Research & reliability workspace adds paired-case selection,
either-agent-failed filtering, side-by-side trace disclosure, support reasons
and fingerprints. Compose bundles only these small synthetic-warehouse results;
raw F1 artifacts and model weights remain optional.

Publication verified: implementation `a84259489aae8364a25bcabddb4e5a4e4a712e35`
pushed normally to `feat/issue-2-agent-paired-evaluation`; `git ls-remote`
matched exactly. Draft [PR #3](https://github.com/JedidiAymen/F1LAB/pull/3)
targets `feat/foundation`, unmerged. [PR CI 41229788889](https://github.com/JedidiAymen/F1LAB/actions/runs/41229788889)
passed Python, web and clean-data Compose. Exact Python CI result: **247 passed,
30 skipped in 9.28 s**, default dependency set; mypy 100 files. This differs from
local all-extras verification (307 full-run passes before the final added binding
regression, then 5 focused service passes; 308-test local inventory). Web CI has
16 unit passes, build/lint pass. Compose CI actually builds and checks the bundled
32-case API without raw F1 data. Browser evidence remains local, not a CI job.
PR #1 stays at `5a95ba26395cf8f7395a8396297409db17ebe02e`; foundation stays at
`5cdac66677e6abb513f84e3ede5f74dd74d00bb6`. No PR/main merge or attribution change.
After testing, removed disposable build cache (Docker reported 2.956 GB; shared
runtime layers remain), restoring about 3.2 GiB free; no images/volumes/data deleted.
