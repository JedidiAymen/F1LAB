# Driver DNA — inductive remaining-lap study

Issue #2, section B. Branch `feat/issue-2-dna-future-segment` starts at fetched
foundation `5cdac66677e6abb513f84e3ede5f74dd74d00bb6`; it does not depend on or
merge review PRs #1/#3. Baseline verification: 297 Python tests (32.38 s),
Ruff/mypy 99 files, web lint/build and 16 unit tests pass before source edits.

## Protocol frozen before new telemetry or model scoring

This is a supervised future-performance task, not a driver-identity score or
proof of innate driving style. Decision point: **20 elapsed seconds after the
provider's lap start**. Target: remaining completed-lap duration, in seconds.
Inputs: telemetry dated no later than the decision point, current lap number,
and previously completed laps known by that cutoff. No whole-lap distance/time
normalization, current-lap duration/sector outcomes, race-median quality filter,
held-out cohort moments, driver identity, team identity or calendar year inputs.
Provider observation time is assumed usable retrospectively; publication time
has not been established, so this does not claim live operational availability.

Frozen chronological sessions:

- Train: Monaco 2023 (9094), Brazil 2024 (9636), Monza 2025 (9912), already cached.
- Validation / epoch selection: Abu Dhabi 2025 (9839), new telemetry.
- Test: Australia 2026 (11234), Japan 2026 (11253), new telemetry and circuits.

These sessions are held out from this task's training/preprocessing, not globally
untouched facts: lap times from some events may appear in prior pace research.
New circuits and the season/regulation boundary are confounded; two test races
cannot establish broad circuit generalization. Report both races separately.
Preserve original three-race/transductive identification experiments unchanged.

Input window: six existing channels (speed km/h, throttle/brake %, gear, rpm,
DRS-open indicator), sampled at 64 time-grid positions over 0–20 s. Only prefix
coverage/gap/finite checks determine telemetry eligibility. Prior-lap context uses
only completed prior laps with end <= decision time. Require a completed target
lap and finite duration >20 s; report attrition, including target availability.
Do not filter later pit-in/SC/slow outcomes: future disruptions are part of the
forecasting difficulty. Censored/incomplete laps cannot be scored by this target.

Comparators fixed in advance: last completed lap, rolling-three-lap median,
context-only Ridge, handcrafted-prefix Ridge, handcrafted-prefix LightGBM,
TCN with prior context (seeds 7/42/123), context ablation, and exploratory masked
prefix pretraining (seed 42). Predict corrections to last-lap persistence;
preprocessing and target scaling fit training sessions only. Reuse the existing
PyTorch temporal encoder; no neural promotion merely for technical complexity.
Fixed neural budget: at most 25 supervised epochs, patience 5 on validation MAE,
AdamW lr 0.001/weight decay 0.001, batch 64, two CPU threads; masked pretraining
at most 10 epochs on training prefixes only. Classical settings and exact source
hashes will accompany artifacts before test scoring. No tuning against test.

Metrics: MAE, median absolute error, RMSE (seconds), per-session/per-driver
failures, seed variation and paired error differences against persistence.
Resample drivers with both test sessions retained for conditional uncertainty;
this is not an interval for new-circuit population performance. Any embedding
retrieval uses training references only and is descriptive, not causal style
interpretation. Report negatives, held-out failures and actual trained artifact
hashes. Frontend plots must use saved model output and observed prefixes.

## Source and resource gate

OpenF1 [historical API](https://openf1.org/docs/), approximately 3.7 Hz car data;
[repository license](https://github.com/br-g/openf1/blob/main/LICENSE), reviewed
2026-10-31, CC BY-NC-SA 4.0. Non-commercial local research, provider attribution,
raw responses stay ignored; broader upstream timing/commercial rights are not
established. No footage, audio or broadcast material. No new license is assigned
to upstream data. Dataset/model cards retain provider restrictions.

Existing 60 car files use about 362 MiB. Planned 60 new driver/session requests
are estimated at 360 MiB from that observed cohort, not guaranteed storage.
Before fetching: enforce **24 MiB decoded payload per response**, **600 MiB new
payload budget** and **1 GiB free-disk floor**; stream/abort oversized responses,
pace requests with the existing retry/rate-limit client, reuse cached responses.
Current disk after disposable build-cache cleanup: about 3.2 GiB available.
NVIDIA driver unavailable; CPU execution only. No paid data/live subscription.

Actual downloads, cohort, trained model metrics and reproduction will be filled
only after execution. This protocol does not mark section B complete.

Before scoring, fixed classical settings: Ridge alpha=10, training-only
StandardScaler; LightGBM 200 estimators, 15 leaves, min_child_samples=30,
learning_rate=0.03, seed 42, two threads. Neural encoder reuses `Encoder` with
width 16 / output 32, mean+max pooling to 64 dimensions; head 32 GELU, dropout
0.1, scalar residual, SmoothL1 loss. Training-only residual mean/std scaling.
Ablation removes prior context; masked variant reconstructs six prefix channel
means from 50%-masked training-prefix inputs for ten epochs before supervised
fit. This is limited self-supervision, not dense temporal reconstruction.
Neural test-row poisoning regression verifies identical fitted weights after
changing held-out telemetry/context/targets. Seven focused new tests pass in
5.84 s; bounded-client integration has 14 passes in 0.61 s; static checks pass.

## Pre-training amendment — real 2026 schema audit

Six-channel build failed before any training/scoring: `drs` is null on every
inspected row for driver 16 in Australia (31,180 samples) and Japan (34,764);
the prefix gate rejects nonfinite channels. Preserve the failed `build.log`.
Use **five shared observed channels** (speed/throttle/brake/gear/rpm) in all
sessions, dropping DRS globally, without imputing an off state. Encoder input
channels=5 and masked decoder output=5. Handcrafted descriptors are five channel
means/stds plus brake-onset, gear-change and throttle-change counts (13 total).
All prior split/model budgets remain fixed. No metrics were inspected to make
this data-schema amendment. Original identification study is unchanged.

## Target-coverage gate failure, before test scoring

Five-channel build yielded train=3,199, validation=880, test=820 rows, but all
test rows were Japan. Cached Australia `laps` had only 45 rows and zero kept
targets. The initial builder checked split presence instead of every registered
session. Stopped the active runner after the first seed fit, before test-score
reporting/MLflow logging. Partial model files and the failed-attempt dataset
are preserved locally; these are not a completed six-session benchmark. A fresh
Australia API audit uses a separate cache, retaining original response bytes.
The builder must require every registered session or fail with quality evidence.

## Executed result — EXP-DNA-FUTURE-01

Completed CPU study: **5,676 prefixes**, 3,199 train / 880 validation / 1,597
test, **777 Australia + 820 Japan**. Kept counts by source: Monaco 1,442,
Brazil 1,033, Monza 724, Abu Dhabi 880. 329.9 MiB new car payload; all original
training caches reused. No original source response, old identity tensor or
pace artifact overwritten. The fresh Australia lap response had 1,008 rows
instead of the preserved cache's 45; SHA-256 changed from
`a6e52b3e34c806dfd507340086ef89c43ade9dfb832aad8654af24d0ba45d8b8`
to `2a3fd6867dac686c4324573d65ca9c39b22ea822aaa1c724111490d1e4c536dd`.
A separate symlink overlay selects the audited response. This exposes a cache
completeness risk for prior ingestion; older studies were not recomputed.

| Candidate | Test MAE (s) | Delta vs persistence (s) | Conditional driver-bootstrap 95% interval (s) |
|---|---:|---:|---|
| last_completed_lap | 5.2198 | +0.0000 | [+0.0000, +0.0000] |
| recent_three_median | 5.7955 | +0.5757 | [-0.8158, +1.3198] |
| context_ridge | 28.1765 | +22.9567 | [+21.5201, +24.7049] |
| prefix_ridge | 38.3523 | +33.1325 | [+30.4333, +36.0124] |
| prefix_lightgbm | 22.1297 | +16.9100 | [+15.2321, +18.9802] |
| tcn_seed7 | 8.1130 | +2.8933 | [+2.2122, +3.5112] |
| tcn_seed42 | 10.2547 | +5.0349 | [+4.6484, +5.4740] |
| tcn_seed123 | 11.0882 | +5.8684 | [+5.1686, +6.6849] |
| tcn_no_context_seed42 | 6.7989 | +1.5792 | [+1.2678, +1.9090] |
| tcn_masked_seed42 | 8.0249 | +2.8052 | [+1.7168, +3.5927] |

**No trained replacement beats persistence.** Standard TCN seed variation is
8.1130–11.0882 s MAE; context removal gives 6.7989 s, masked seed 42 gives
8.0249 s, both still worse than persistence. Single-seed ablation differences
are exploratory, not proof that masking or context removal generalizes better.
Ridge/LightGBM fail strongly across the new circuit/season boundary. No tuning,
retraining or promotion followed inspection of the test scores.

Persistence MAE Australia/Japan: 6.7027/3.8146 s; median AE 0.458/0.322 s.
Australia RMSE 49.6216 s reflects severe completed-lap disruptions. Future
pit/SC delays are retained, so aggregate error and median behavior differ.
The TCN's best seed has Australia/Japan MAE 9.0529/7.2224 s. Learned correction
transfer is poor; this does not establish a causal explanation for that failure.

Independent `scripts/verify_dna_future.py` recomputes ten models' test metrics
with pandas and reloads eight trained artifacts for eight seeded point checks.
Classical predictions match exactly; largest neural reload difference
0.0000119843 s (below the 0.001 s verification threshold). This is an independent
implementation/reload check of saved evaluation, not an independent human study
or a second held-out dataset. Full result in the evidence bundle.

Eight real training runs synced to local MLflow (experiment IDs 2–9):
- `context_ridge.run`: `1c51a54eb43a4b42bf79543dc19ffacf`
- `prefix_lightgbm.run`: `6f1bdd2f960b41f19348d678998516e7`
- `prefix_ridge.run`: `00242aa4b65f4a8fbd2e97e793c200a7`
- `tcn_masked_seed42.run`: `6eb4a4b2df1b419b92bc2d08125c90f6`
- `tcn_no_context_seed42.run`: `82d04f9f3e2745d0975fb6a72874287e`
- `tcn_seed123.run`: `7e37c8893bc64232b1f81ab4abc552e0`
- `tcn_seed42.run`: `d91e651915544bed908b6b5ab459e9c4`
- `tcn_seed7.run`: `c88a8a60df2a45f3a4cc90cc6c9cbbf8`

Model artifacts total about 966 KB, including three classical pipelines, five
PyTorch checkpoints, training-only normalization, standard `ModelCard` JSON,
checksums and tracking manifests. They remain in the ignored local
`data/processed/driver_dna_future/verified/models/`. Torch loading uses
`weights_only=True`. MLflow logs `.pt`, card/checksum and required preprocessing;
existing joblib contracts/checks remain unchanged by the optional suffix support.
No neural inference is required by the basic app. No model is deployed/promoted.

## Reproduction and demo

```bash
uv sync --frozen --dev --extra dl
python -m f1_racelab.ml.driver_dna.future_data --fetch
# If a registered session fails coverage, preserve and audit its cached laps:
python scripts/audit_dna_future_cache.py --session 11234
python -m f1_racelab.ml.driver_dna.future_data \
  --cache data/processed/driver_dna_future/audited_cache \
  --out data/processed/driver_dna_future/verified
docker compose --profile mlops up -d --wait mlflow  # optional tracking service
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
  python -m f1_racelab.ml.driver_dna.future_study \
  --out data/processed/driver_dna_future/verified
python scripts/verify_dna_future.py
pytest -q -W ignore
cd apps/web
npm ci
npm run lint && npm run test:unit && npm run build && npm run test:e2e
```

Run from a normal checkout/venv. This session used an isolated worktree and
`PYTHONPATH=/tmp/f1lab-dna-future/src` with the owner's shared venv/cache. Avoid
re-running into an existing dataset/study: use a new output directory and preserve
previous files. A fresh source may differ; manifests/data hashes make that visible.
The initial failed-attempt dataset/partial seed fit remain outside `verified/`;
none of those files contributes to the published scores.

GET-only `/api/v1/driver-dna/future-study` exposes checksummed saved comparisons;
`/{case_id}` validates dataset hashes and allows held-out prefixes only. Driver
DNA adds lazy-loaded model/circuit selectors, error-ranked lap selection, five
synchronized measured prefix charts and validation curves. This is no new race
clock and no live inference. Original identity/transductive results stay separate.
Clean checkout/container bundles aggregate results and training curves only,
clearly labels missing individual telemetry/weights, and permits benchmark
comparison. Local mounts enable real-lap inspection. No raw telemetry or footage
is redistributed; existing provider/non-commercial caveats remain.

Still partial: driver-identity expansion/retraining, representation retrieval,
more varied session/circuit holdouts, full masked sequence reconstruction,
corner-linked intelligence and prospective operational availability. The
conditional two-event intervals do not establish broad circuit generalization.

Failure-label audit: the test cohort has one reported remaining duration above
300 s: Australia ALO lap 13, lap duration 1,069.531 s. The next lap starts
1,069.534 s later (3 ms difference) and is marked pit-out. The following lap
inherits this very long prior-lap baseline, causing the two largest persistence
errors (~947/971 s). This supports an extended lap interval rather than an
arbitrary numerical outlier, but does not independently establish its sporting
cause. It is retained in the registered all-completed-lap target. No favorable
post-hoc filtered score replaces the primary result.

Publication: implementation `7477f70fb540b4b8e37c66bbe98fd631a599549f` pushed
normally and remote-SHA verified. Draft [PR #4](https://github.com/JedidiAymen/F1LAB/pull/4)
targets foundation, unmerged. [CI 41250905883](https://github.com/JedidiAymen/F1LAB/actions/runs/41250905883)
passed Python, web and the **actual clean Dockerfile build/start/smoke** without
research data/optional services. Exact Python CI: **247 passed, 31 skipped in
14.47 s**, default dependencies; mypy 103 files. Local all-extras count is 309;
16 frontend units pass. Browser evidence is local, not a CI job. Seven executed
model/data source hashes match the committed implementation; training occurred
on base 5cdac66 with a modified worktree, as honestly recorded in run provenance.
Publication source/CI proof is distinct from the base training SHA.
PR #3 remains `810b90e8fefd877015eb90cb9d5f947fe0b9584b` with CI 41230058581 green;
PR #1 remains `5a95ba2`; foundation remains `5cdac66`. No merges/force pushes.
