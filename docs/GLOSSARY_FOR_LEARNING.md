# Learning chronology and glossary

This follows the path from provider data to a qualifying experiment and then
to the planned race workstation.

1. **FastF1 cache and OpenF1 archive.** FastF1 loads official timing streams
   into Python `Session` objects and caches responses; a cache hit can work
   even when the origin later denies access. OpenF1 exposes historical sessions
   as JSON endpoints. In this run, the FastF1 2022 cache was usable; uncached
   F1 2023 returned 401, so OpenF1 supplied 2023–2025 session results.
2. **ETL and dataframe.** Extract, transform, load turns session-shaped source
   records into a table with one row per `(year, round, driver)`. pandas handles
   current feature/model code. Polars is installed but is not in this path;
   adding it here would duplicate transformations without a measured benefit.
3. **Parquet, SQL and MinIO.** Parquet is compact columnar storage for local
   event data and model artifacts. PostgreSQL will own relational metadata and
   indexes; MinIO can hold large versioned objects. They serve different access
   patterns and are not interchangeable simply because all store data.
4. **Timedelta and seconds.** FastF1 `LapTime`, `Q1`, `Q2`, `Q3` are pandas
   durations; `.dt.total_seconds()` converts them before numerical equations.
   OpenF1 already returns seconds. A 1.5-second gap is a duration, while
   `100 × (91.5 / 90.0 − 1) = 1.667%` is an event-relative pace feature.
5. **Event normalization.** Lap times from Monaco and Monza cannot be compared
   directly. Dividing by the fastest lap in the *same event/session* produces a
   percent gap. The normalizer must never look at future weekends. It does not
   remove fuel load, wind, tow or track evolution.
6. **Feature leakage and as-of time.** A pre-Q input must exist before Q begins.
   Today's Q1 time and final position are targets/labels, never predictors.
   Historical form uses `groupby(driver).shift(1)` before rolling: at round 5,
   the window sees at most rounds 1–4. Team means are formed once per weekend,
   then shifted, so a current teammate cannot leak today's Q1 result.
7. **Regression, Ridge and LightGBM.** Regression predicts a continuous Q1
   percent gap. Ridge is a linear model that penalizes large coefficients with
   an L2 term `αΣβ²`; LightGBM sums small decision trees to capture nonlinear
   interactions. Both are compared with the simple FP3 order, not assumed to
   be superior because they are more complex.
8. **Train, validation, test and overfitting.** Fit on 2022–2023, choose the
   model on 2024, and report 2025 after the choice. Looking repeatedly at 2025
   to adjust features would turn the held-out year into another validation set.
   All drivers from one GP stay together because they share conditions.
9. **MAE and Spearman.** Position MAE is the mean absolute rank error within a
   GP, then averaged over GPs. Spearman measures monotonic rank agreement.
   A model can improve Q1 time prediction yet lose final-position ranking due
   to Q2/Q3 progression; both target and evaluation label must be named.
10. **Paired event bootstrap.** Candidate minus FP3 MAE is computed per GP;
    entire GPs are resampled with replacement. This preserves within-weekend
    dependence and gives a descriptive interval for the observed calendar.
11. **RaceState and one clock.** The new Python reducer applies ordered
    `SessionEvent`s to one canonical state and supports deterministic seeking.
    A real 2025 Monza pack now adds positions, laps, pit and stints to the
    race-control message sample. `ReplaySource.state_at(t)` returns all
    available fields at one session time, using event checkpoints and indexed
    location/interval samples. The local UI draws 2D, timing and race control
    from that same API state; the telemetry chart derives its cursor from that
    state's session time. 3D remains unconnected. Drawing frames must not
    invent extra race time.
12. **Distance alignment.** Two lap telemetry streams can be interpolated to
    matching estimated distances before comparing speed or braking. Equal
    timestamps can represent different physical places. F1LAB now has one
    real two-lap example with speed-integrated distance and a cursor tied to
    canonical replay time; it is not GPS/surveyed alignment.
13. **Tyre degradation and undercut.** A race simulator will model lap time as
    baseline pace plus fuel/tyre/weather and other effects in seconds. An
    undercut pits earlier to gain time on fresh tyres while the rival remains
    out. Traffic, pit loss and safety-car timing can reverse it. No strategy
    equation has yet been calibrated in F1LAB.
14. **Monte Carlo and common worlds.** A future simulator will sample uncertain
    lap, pit and race events with a seed. Candidate strategies should share
    exogenous random worlds where valid, reducing noise in their comparison;
    traffic that depends on a strategy remains branch-specific. These samples
    would express model-conditional uncertainty, not guaranteed win odds.
15. **Measured versus estimated position.** An OpenF1 coordinate is an
    approximate provider observation, marked measured only in the sense that
    it came directly from that response. A car point between two nearby
    samples is linearly interpolated and marked estimated. Neither coordinate
    can override the provider's official position or lap timing. The coordinate
    origin and unit are not known, so the first circuit outline is a trace,
    not a surveyed engineering map.
16. **Playback clock versus state sample.** The UI transport advances a
    single time in seconds and fetches a canonical Python `RaceState` up to
    five times per second. All data panels show the latest returned state;
    a visible update indicator covers request lag. The circuit line is a
    fixed approximate provider trace. No independent timing or map clock
    is used.
17. **Unavailable versus empty provider table.** HTTP 404 for Monaco's
    historical `pit` resource means the resource is unavailable. A successful
    HTTP response with zero rows would mean the provider supplied an empty
    result. Treating both as zero pit stops would create a false sporting
    conclusion; the candidate audit records the first as `null`.
18. **Anchored playback.** A clock remembers session time `t₀` and
    monotonic wall milliseconds `w₀`. At rate `r`, its current time is
    `t₀ + (w−w₀)r/1000`, bounded by pack duration. Pause first saves the
    current value; a rate change saves it before changing `r`. A slow
    display tick therefore cannot slow the race clock. F1LAB samples at
    5 Hz and all data panels use the same returned state.
19. **Golden replay references and event boundaries.** The three local
    reference races cover dry, mixed-tyre and SC/VSC/red-flag source cases.
    Checking one millisecond before, at and after every normalized event
    verifies which side of a clock cutoff owns it. Shuffled seeking then
    checks that prior navigation cannot change the answer. This proves
    deterministic code on these packs; it cannot certify every upstream
    measurement.
20. **Browser tests with real local data.** Playwright starts the local API
    and frontend, operates actual controls and checks map/timing/focus/control
    timestamps. The browser tests do not replace provider data with mock
    payloads. Separate unit tests use artificial timestamps to isolate clock
    arithmetic, including pause and seek after end.
21. **Observation age and as-of display.** A source row keeps its provider
    session timestamp. At replay time `t`, its age is `t - t_observed`. A
    seek before the row makes it future data and it is hidden; a sufficiently
    old row is stale and its values are hidden. F1LAB currently displays
    weather through age 120 seconds. This is a UI policy, not a provider
    promise or a new measurement.
22. **Rainfall presence versus track grip.** OpenF1's boolean says whether
    rain was reported. It contains no amount or intensity, and cannot prove
    that the road is wet or estimate tyre grip. Missing is not the same as
    `false`; the panel displays “No rain reported” only for an explicit false.
23. **Track status versus race-control text.** Many source messages are
    local to one driver or sector. A global status needs global scope and a
    conservative phrase mapping. “Safety Car in this lap” means an ending
    phase; it does not certify that the track is already green. A session
    restart without a new global flag is shown as running/unknown.
24. **Tyre stint as-of history.** A stint start says which compound and lap
    start are known at that source time. The history closes an open stint only
    as lap events arrive or a later stint-start event appears. Adding the
    provider's eventual end lap to an earlier state would leak future
    information. `RaceState` schema 3 holds this derived history while stored
    events and packs remain schema 2.
25. **Mapped stint overlap.** A provider can report two stint starts with the
    same lap number (Monaco 2023 car 27). Separate lanes preserve both source
    records and show where mapped lap ranges overlap. The display does not
    guess which row is erroneous or invent unreported laps.
26. **Visual transform interpolation.** The map animates SVG `transform`
    between nearby forward state samples. CSS changes only the appearance;
    canonical state and the session clock remain on the 5 Hz API samples.
    Exact seeks and reduced-motion settings remove the transition, so visual
    movement never rewrites source coordinates or creates a new observation.
27. **Speed-integrated distance.** Between two speed samples, approximate
    distance is average speed multiplied by elapsed time. With speed in km/h,
    divide by 3.6 to get metres per second. Sparse readings, rounding and an
    approximate lap start make this axis an estimate rather than surveyed
    track position.
28. **Distance-aligned lap delta.** Two laps can be sampled at the same
    estimated distance even when their timestamps differ. F1LAB reports
    `elapsed_B - elapsed_A` in seconds; a negative value means B reached that
    estimated point earlier. This comparison coordinate does not itself
    advance or replace the canonical replay clock.
29. **Prediction cutoff.** The time at which a forecast is intended to be
    made. This qualifying experiment uses FP1/FP2/FP3 and is labeled
    immediately before qualifying. Its stored `available_at` is scheduled Q
    start, not the exact time every provider field was published.
30. **Feature registry.** A record of each model input's unit and source
    session. It helps reviewers check that a feature could exist by the stated
    cutoff. It is not a substitute for per-value observation timestamps.
31. **Validation versus holdout.** Validation data may select among candidate
    models; the 2024 weekends serve that role. The 2025 holdout measures the
    already selected model and should not drive tuning. Looking at its result
    repeatedly would weaken the independence of the estimate.
32. **Paired event bootstrap.** Re-sample whole Grand Prix event errors, with
    candidate and baseline kept together, to show how the average difference
    varies across the observed weekends. The 2025 interval crosses zero, so it
    does not establish that Ridge is reliably better than FP3.
33. **Phase-aware forecast snapshot.** A historical input set limited to the
    practices completed by a chosen point: after FP1, after FP2 or before Q.
    The current dataset has only session-level fields, so this is not a
    timestamped live feature stream.
34. **Scheduled practice-end cutoff.** The schedule's planned end time for
    the latest practice used in a snapshot. It gives a reproducible session
    boundary, but it does not show when the provider actually published each
    practice result. The phase lab exposes this limitation.
35. **Eligible-cohort rank.** Position after ordering only the drivers with
    the measured baseline and target required for that research phase. If
    official P1/P2 are missing, the eligible leader can be official P3. F1LAB
    shows eligible rank and official qualifying position separately; its
    current rank-error and leader/top-three metrics use the eligible cohort.


## Geometry and observation checkpoint learning notes

**Driving line versus surveyed circuit:** a driver's measured XY path describes
where that car was reported on one lap. It does not establish track edges,
pit-lane shape, physical track width or the official timing line. F1LAB retains
unknown provider units and marks this display geometry estimated.

**Closure ratio:** endpoint separation divided by source polyline length. A
small ratio identifies a nearly closed trace; appending the first point creates
an explicit inferred closing segment. It does not repair missing circuit arcs
or prove correct physical geometry.

**Normalization and arc distance:** subtracting the bounding-box midpoint and
dividing both axes by the largest span centers/scales the trace without changing
aspect ratio. Summed Euclidean segment lengths are polyline arc distance in
provider units, distinct from telemetry distance in meters.

**Displacement heading:** `atan2(dy,dx)` estimates direction from two connected
location samples. It is not measured car yaw. SVG flips Y, so its display angle
has the opposite sign. A trailing window uses only source points at or before
the canonical state time; dropouts create separate path segments.

**RAF versus painted FPS:** requestAnimationFrame callback intervals describe
browser scheduling opportunities. They do not count completed GPU/compositor
frames. F1LAB's bounded benchmark also records synchronized DOM state, request
latencies and unforced-GC JS heap; these quantities need distinct interpretation.

Temporal detail: measured trail vertices are at or before requested time `t`.
The canonical estimated endpoint may use a later source sample as the existing
historical interpolation bracket; this is retrospective reconstruction, not
proof that data had been published live by `t`. Without `focus_driver`, the API
returns strict canonical `RaceState` schema 3. Focused `location_context` is a
view extension of that same state response; it does not change the canonical
state schema or create another position/clock authority.


## Multi-channel telemetry learning notes

**Common distance versus full lap duration:** two laps can have different
speed-integrated lengths. The comparison grid stops at the shorter length, so
its last reference-A elapsed time may precede A's own lap finish. A cursor after
that grid end is unavailable even while A is still in the source lap.

**Discrete source channel:** gear, brake-source values and DRS codes use the
previous retained sample between timestamps. A blend such as gear 4.5 would
invent a state. Continuous speed, throttle and RPM can interpolate when both
endpoints exist; a missing endpoint remains unknown.

**Delta identity:** at every shared distance, `delta_seconds = elapsed_B −
elapsed_A`. A positive value means B required more elapsed time to reach that
estimated distance. It does not establish equal fuel, tyres, traffic or weather.

**Catalog versus quality certificate:** an explicit source pair gives stable,
reproducible selection. It does not prove both laps are clean; missing Monaco
pit coverage leaves pit-in status uncertain despite available non-pit-out flags.


### 2026-10-16 — telemetry UI review correction

Published P3 source: `5bce32930dfaa802c6ec1c7a54e1a0f7ffce0cf9`. A subsequent
UI/source review found a discrete trace ended at the previous known point
instead of extending its held value to the first missing observation. The path
now draws that final horizontal step to the missing grid point, then breaks;
it does not bridge the unknown interval. A gear regression checks this behavior.
The review also found delta-axis tick text could crowd the zero label. Nearby
text within 14 SVG pixels is suppressed while its grid line remains visible.
These are display corrections; source comparison artifacts and hashes are
unchanged.

Current corrective checks: `cd apps/web && npm run test:unit` — 13 passed;
`npm run build` and `npm run lint` passed. Latest JS is 452.63 KB (148.05 KB
gzip), CSS unchanged at 79.61 KB (15.71 KB gzip). Full
`cd apps/web && npm run test:e2e` passed 14/14 in 36.5 s with both UI fixes.
After cleanup, `npx playwright test --grep='six telemetry channels'` passed
3/3 in 14.4 s. The full suite covers the fixes before cleanup; the targeted
three-race run verifies the subsequent cleanup. Corrective source commit/push
remains pending. Prior 14-scenario/39.2-second evidence applies to the original
published P3 source.

A held discrete value applies until the next observation boundary. When that
next value is missing, drawing the horizontal segment to its boundary expresses
known prior coverage; stopping there and breaking the path expresses unknown
future coverage. Suppressing overlapping tick text improves legibility without
removing the numerical grid scale.

### P3 publication proof

Implementation commit `5bce32930dfaa802c6ec1c7a54e1a0f7ffce0cf9` expanded the catalog and channel UI. Review
correction commit `9a13f6eef679c417fc3bc6a8beddd320504dbc06` fixed held-value traces at missing discrete samples
and crowded mobile delta labels. Both are on `origin/feat/foundation`;
`git ls-remote origin refs/heads/feat/foundation` returned `9a13f6eef679c417fc3bc6a8beddd320504dbc06`. Git
used Aymen Jedidi's repository identity, with no assistant coauthor. The two
unrelated user helpers under `ml/features/` remain untracked and untouched.

- **Walk-forward validation**: score each event with a model trained only on earlier events.
- **LambdaRank**: gradient boosting that optimises a ranking metric within groups (events).
- **Brier score**: mean squared error of probabilities; lower is better; compare to a uniform baseline.
- **Reliability diagram**: forecast probability vs observed frequency; points on the diagonal are calibrated.
- **Interval coverage**: share of actual outcomes inside the forecast interval; should match nominal (80%).

## 2026-10-31 — operations and reliability concepts in this implementation

- **Liveness vs readiness vs integrity:** `/healthz` says the process answers;
  readiness lists file presence; pace health actually checks model bytes/schema/
  dependency versions. A living app can honestly lack a research artifact.
- **Container image vs mounted artifact:** code/dependencies are built once;
  `/app/data/processed` mounts local research data read-only. Rebuilding UI does
  not copy confidential caches into an image. Profiles enable optional services.
- **Training run vs artifact import:** refitting changes training execution;
  importing an existing card/weights only registers old evidence. An import SHA
  belongs to importing code, not the original unknown training source.
- **PSI:** sum `(current_fraction-reference_fraction)*log(current/reference)`
  over fixed reference bins plus missingness, with 0.5-count smoothing. High
  temperature PSI can reflect a different calendar/circuit/weather mix. It does
  not prove model failure or regulation causality.
- **Paired race bootstrap:** align candidate and baseline forecasts by race,
  driver and lap; resample entire races so dependent laps are not falsely treated
  as independent. A difference interval crossing zero does not establish a gain.
- **Bounded labels:** aggregate metric keys use registered route templates,
  not arbitrary URLs/driver IDs. Otherwise metrics grow without bound.
- **Bounded fetch vs full materialization:** fetch 51 rows to return at most 50
  and detect truncation; do not convert a billion rows to pandas then call head.
  A truncated result's reported count is a lower bound, not the full SQL total.
- **Citation existence vs support:** a real `t2` observation can still contradict
  a diagnosis. The LLM scored 25% on eight planted faults despite citing real IDs
  in every case; the scripted reference's success does not measure LLM skill.
- **Lazy code import:** the Three.js module is fetched when opened; the replay
  still has one clock. A smaller initial bundle is not measured faster loading.

### Driver DNA normalization availability

**Transductive:** preprocessing may use an unlabeled held-out cohort's
statistics. It can remove that circuit's shape, but assumes that cohort is
available. Unlabeled does not mean training-only. **Inductive normalization:**
fit preprocessing on explicit training rows, freeze it, transform future/test
examples without refitting. Test-value poisoning must leave fitted moments
unchanged. In this repository logistic cross-circuit accuracy falls 38.4% to
19.8% when that target-cohort access is removed; this changes the task rather
than proving neural models better. The unchanged teammate logistic result
reflects cancellation of affine within-circuit scaling by its training scaler.
A fully online protocol additionally needs causal quality filters and feature
availability; this small normalization audit does not establish those.
