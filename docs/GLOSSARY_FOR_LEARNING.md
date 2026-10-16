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
    location/interval samples. The first local UI now draws 2D, timing and
    race control from that same API state at one playback time. 3D and
    telemetry remain unconnected. Drawing frames must not invent extra race
    time.
12. **Distance alignment.** Two lap telemetry streams should be interpolated
    to matching track distances before speed or braking comparisons. Equal
    timestamps can represent different physical places. This is a planned P3
    feature and has no current measured comparison result.
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
