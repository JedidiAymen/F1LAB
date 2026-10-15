# Engineering decisions

## D-001 — historical qualifying provider fallback, 2026-10-15

FastF1 3.8.3 could reuse 2022 cached timing, but an uncached 2023 Bahrain
timing request to `livetiming.formula1.com` returned HTTP 401. OpenF1's public
historical API documents 2023 onward and returned session results for a 2023
qualifying and FP3. We keep the original FastF1 dataset and create a separate
mixed-source dataset. Each row records provider, version, source identifiers,
hash and prediction cutoff. The raw OpenF1 responses are cached under ignored
`data/raw/openf1/`. See `ML_EVALUATION.md` for comparability limits.

Primary sources: [OpenF1 API](https://openf1.org/docs/) and the local FastF1
3.8.3 source in `.venv/lib/python3.12/site-packages/fastf1/req.py`. No
third-party repository code was copied. The inspected OpenF1 repository HEAD
was `87540e3f495bbd9bedb37b10456dd848c8f193d6`; its
[LICENSE](https://github.com/br-g/openf1/blob/87540e3f495bbd9bedb37b10456dd848c8f193d6/LICENSE)
is CC BY-NC-SA 4.0. The exact licensing of upstream F1 timing facts and a
future commercial product needs separate review. F1LAB keeps raw API data out
of Git and attributes the provider in data rows and documentation.

## D-002 — common practice feature set, 2026-10-15

OpenF1 `session_result` reports official best practice times, ranks, and Q1–Q3
times, but not the per-lap tyre, sector, and representative-lap features in the
FastF1 extractor. Models on the mixed dataset therefore use an explicit eight
field intersection: FP1/FP2/FP3 gaps and ranks plus FP1→FP3 and FP2→FP3 gap
changes. This avoids training on source-specific missingness as a proxy for
season. The original richer feature list remains available for a homogeneous
FastF1 experiment when access returns.

## D-003 — event-level uncertainty, 2026-10-15

The unit of evaluation and bootstrap resampling is the Grand Prix, because all
drivers in one event share weather, track evolution and conditions. A paired
bootstrap resamples candidate-minus-FP3 event errors with a fixed seed. Its
interval describes variability among these historical events; it is not a
calibrated probability that a model will win a future race.
