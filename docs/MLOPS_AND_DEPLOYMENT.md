# Local deployment, provenance and reliability

Checkpoint 2026-10-31; starting source `129e4b106a7ad06afec124be44095c6f091e66e2`,
branch `feat/foundation`. This is an integrated operations/research milestone,
not completion of the advanced research mandate. Publication SHA is recorded
in `CHATGPT_HANDOFF.md` after normal push verification.

## Startup and scope

```bash
docker compose up --build --wait api web
# Open http://127.0.0.1:8080
docker compose --profile mlops up -d --wait mlflow
docker compose --profile observability up -d prometheus
docker compose --profile inference up -d --wait inference
```

Only `api` and `web` start by default. The application reads existing artifacts
from `./data/processed:/app/data/processed:ro`; images contain no real F1 raw
data, telemetry, models, secrets, host virtualenv or node_modules. The only
bundled research sample is the actual local Ollama run on **synthetic warehouse
faults**, under `docs/research/evidence/forecast_debug_20261031/`. A clean
checkout can inspect that incident replay without downloading a model.
Real-data workspaces clearly report unavailable files until their documented
pipelines have been run. No protected broadcasts or audio were downloaded.

Profiles are independent: `mlops` runs MLflow 3.6.0 with SQLite metadata and
proxied artifacts in a named volume; `observability` runs Prometheus with
7-day/256 MB retention; `inference` is a separately health-checked **HTTP
replica**, not a batch queue or worker scheduler. `storage` retains the prior
PostgreSQL/MinIO services and named volumes; neither is required for offline
research. Storage containers were not newly validated in this checkpoint.
No Jenkins, Kubernetes, remote storage or cloud deployment was introduced.

All published ports bind to `127.0.0.1`. Defaults are API 8000, web 8080,
inference 8001, MLflow 5000 and Prometheus 9090; override `F1LAB_*_PORT` in
`.env`. Optional services can be stopped independently. `docker compose down`
stops the project without deleting named volumes. Local development defaults
are not production credentials; public deployment/auth/TLS remain out of scope.

## Runtime contracts

`infra/api.Dockerfile` locks Python and uv base images by digest, installs the
frozen dependency graph without dev/DL/engine extras and runs as UID 10001.
It retains `/app/src` with `PYTHONPATH=/app/src`: the existing artifact resolvers
derive `/app/data` from source paths. Changing that layout to installed-wheel
paths silently breaks those contracts. The runtime has `libgomp1` for LightGBM.
Build-time uv download cache is a disposable BuildKit mount.

`infra/web.Dockerfile` builds the locked React application with Node 22, then
copies static files into digest-pinned unprivileged Nginx. Nginx serves SPA
fallbacks and immutable hashed assets, proxies `/api/` to FastAPI, and forwards
WebSocket upgrades under `/ws/`. Production never runs Vite's dev server.
API/web have read-only root filesystems, bounded tmpfs, dropped capabilities,
no-new-privileges, CPU/memory/PID limits, bounded logs and graceful stop time.
This is a local deployment template, not a claim of hardened public hosting.

First startup failed because `data/fastf1_source.py` created and enabled the
FastF1 cache at **import time**. Cache initialization now happens only inside
`load_session`, honors `FASTF1_CACHE_DIR`, and has an explicit regression test.
This fixes a genuine conflict between read-only serving and ingestion.
Application lifespan stops existing simulated-live ingest tasks on shutdown.

| Endpoint | Meaning |
| --- | --- |
| `/healthz` | Process liveness, independent of research data |
| `/api/v1/readiness` | Explicit **presence-only** replay/model inventory; not integrity validation |
| `/api/v1/pace/health` | Load trusted local pace artifact; validate SHA-256, feature schema, dependency versions; 503 on failure |
| `/metrics` | Per-process Prometheus request counts and duration histograms |
| `/api/v1/research/reliability` | Checksum-verified saved research report, model card, available run provenance |
| `/api/v1/research/agent-evaluation` | Read-only saved LLM diagnoses, examined tool observations and source hashes |

HTTP metrics use bounded method/route-template/status labels: arbitrary URLs,
driver IDs, query strings, request IDs and bodies are not metric labels. Durations
are monotonic seconds. `X-Request-ID` accepts at most 64 safe characters or is
regenerated; unavailable requests log route/status/duration and correlation ID.
Metrics are per process, so scrape each replica. WebSocket frame metrics,
background-job spans, distributed tracing and production alert validation are
not implemented. Request correlation is not a full OpenTelemetry deployment.

## Training, artifact import and MLflow

`ml/common/registry.py:save_artifact` preserves existing joblib/card/SHA contracts
and calls `tracking.record_artifact`. Every registry save now writes an atomic
local `.run.json`: model/card/checksum hashes, dependencies, dataset fingerprint,
source SHA/dirty state, evidence type, metrics, run kind and tracking outcome.
The snapshot fingerprint is row-order-sensitive with canonical column order;
only its misleading docstring/test title changed, not any stored fingerprint.

Set `MLFLOW_TRACKING_URI` to opt into the existing HTTP REST client. The basic
app and training do not import the MLflow SDK. The adapter creates/locates an
experiment, creates a run, records named model comparisons/hyperparameters,
uploads model/card/checksum/provenance through the proxied artifact endpoint,
and closes the run. Failed sync is explicit in the local manifest and logs;
it does not discard a successfully trained model. The import CLI exits nonzero
when sync fails. The optional server is local and unauthenticated.

```bash
# Import an existing artifact without calling it a new training experiment:
.venv/bin/python -m f1_racelab.ml.common.tracking \
  --root data/processed/models/race_pace --name race_pace_lightgbm \
  --tracking-uri http://127.0.0.1:5000

# Refit from the existing real frame, log the new training save:
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
  .venv/bin/python -m f1_racelab.ml.pace.benchmark --refit-only
```

Both operations were executed. Artifact import run ID:
`f9dea1bad08b4c7aba837ce5a43c6edf`; real refit training run ID:
`1fe56e63be0a4da1ba4ed29e1fdd0ae1`. The prior model/card/run were preserved at
`data/processed/models/race_pace_before_20261031/`. The refit reproduced the
model binary SHA `98b611f35f949c8b515316f48367b7d244435aec5160b354a207b76378adf8c2`;
the new timestamped card SHA is
`156e43b71e2377f4c02b7677c566205268daf09685bf869e4d3a8b2354c46cf5`.
Its validation metrics are inherited from the existing saved walk-forward
evaluation, not new in-sample performance or a fresh holdout. Import-source SHA
identifies the importing code, **not** the original training source. Source was
the stated base SHA with a modified worktree during execution.

No dataset-versioning service was added: existing source manifests, table
fingerprints and SHA-256 snapshots already identify this small local workload.
Immutable run directories, retry/deduplication across concurrent writers,
remote auth and a model promotion/rollback registry remain future work.

## Reliability study and UI

```bash
.venv/bin/python -m f1_racelab.ml.common.reliability
```

Inputs: existing `race_pace/predictions.parquet` (323,035 candidate rows) and
`pace_frame.parquet` (83,523 rows, 85 races). Output:
`data/processed/reliability/pace.json` and SHA sidecar. The API verifies the
report checksum; generating it also hashes both input snapshots. This lineage
identifies generation inputs; the API does not continuously rehash/retrain on
changing source Parquets. Rebuild the report after changing inputs.

`compare` rejects duplicate `(race_id, driver_number, lap, model)` keys and
disagreeing target values. Model candidates pair against last-lap persistence
on identical keys; unmatched rows are counted. Error = forecast minus truth
(seconds); MAE = mean absolute error. Seed-42, 5,000-draw bootstrap resamples
race clusters. The 57,679 scored green-clean laps span 65 races. LightGBM MAE
0.5749016 s vs persistence 0.5929278 s; paired delta −0.0180262 s,
95% interval [−0.0572999, +0.0294185]. **No reliable gain established.**

Drift uses all prepared rows: 67,120 in 2023–2025, 16,403 in 2026. Reference
deciles plus missing-value bin, 0.5-count smoothing:
`PSI = Σ (p_current − p_reference) log(p_current / p_reference)`.
Constant reference features receive a separate equal-value bin. Anchor pace
PSI 0.28498; track temperature 1.35004; air temperature 1.59088. These values
describe changed inputs and calendar/circuit/weather mix; they do not prove
that regulations caused errors. No hypothesis-test or alert threshold claim.

The lazy-loaded Research & reliability workspace exposes paired model errors,
season bias, sorted feature drift/missingness, season-filtered race failure
selection, model/feature availability, source fingerprints and the actual saved
LLM incident replay. All units and outcome-filtering caveats are visible.
The existing Three.js viewer now imports code only after the user opens it;
the initial JS chunk falls from 1,443.87 KB to 516.23 KB (build size, **not**
a measured page-load latency claim). The 929.70 KB Three.js and ~372 KB research
chunks remain large but deferred. Qualifying/strategy/session clocks are unchanged.

Design follows existing Geist, carbon/slate surfaces, semantic colors and
compact research tables; the negative paired result anchors the page. It uses
existing shadcn Button/Badge/Select, Recharts, and the existing circuit renderer.
No general UI redesign, fabricated telemetry or replacement replay was added.

## Verification, failures and resources

Initial audit: remote branch equals base SHA; owner Git identity retained; two
untracked `ml/features/` helpers untouched. Hardware: 20 logical CPUs, 15 GiB
RAM, 9 GiB swap; initially ~3.3 GiB available RAM and 6.5 GiB free disk.
NVIDIA driver unavailable (`nvidia-smi` failed). No GPU-training claim.
Host Python 3.12.13, uv 0.12.17, Node 22.23.2, npm 10.9.8, Docker client
29.2.1/server 29.9.0, Compose 5.1.0. Digest-pinned container Python is 3.12.16.

Baseline: 271 Python tests, full Ruff, mypy (94 source files), five Node test
files, web lint/build, 20 Chromium scenarios (58.0 s). `uv sync --frozen --dev`
removed optional packages; `uv sync --frozen --dev --all-extras` restored them
from cache before full verification. Browser/TestClient/Spark checks needed
the runtime's network/event-loop access. These are environment constraints,
not silently skipped tests.

Container experiments exposed import-time writes (fixed), tight storage
(build caches and superseded images created here were reclaimed), and an early
browser `ENOSPC` failure during overlapping builds (rerun required). No prior
images/volumes or user data were deleted. First images measured ~1.23 GB API
and 55.5 MB web; scientific dependencies include a large XGBoost/NCCL runtime
even though this demonstration uses LightGBM. A cold build temporarily needs
several additional GiB; avoid concurrent large builds/downloads on a full disk.
Web install reported existing npm advisories; no automatic major upgrades or
forced audit fixes were applied. See `TEST_EVIDENCE.md` for final gate results.

```bash
uv sync --frozen --dev --all-extras
.venv/bin/ruff check src tests scripts
.venv/bin/mypy src/f1_racelab
.venv/bin/pytest -q -W ignore
cd apps/web
npm run lint
npm run test:unit
npm run build
npm run test:e2e
F1LAB_E2E_BASE_URL=http://127.0.0.1:8080 npm run test:e2e
# Repository root:
.venv/bin/python scripts/smoke_compose.py --require-data
```

GitHub Actions remains primary CI. The added Compose job builds/starts only
basic services with absent real-data artifacts, checks SPA/API/tracing contracts,
prints diagnostics, and cleans up disposable containers. Local success does
not imply a green remote workflow; verify the published run separately.

Primary references examined 2026-10-31: [Docker profiles](https://docs.docker.com/compose/how-tos/profiles/),
[Compose service controls](https://docs.docker.com/reference/compose-file/services/),
[uv Docker guidance](https://docs.astral.sh/uv/guides/integration/docker/),
[MLflow REST API](https://mlflow.org/docs/latest/api_reference/rest-api.html).
Configuration/client code is independently written; dependencies retain upstream
licenses. No vendor source or visual assets were copied.
