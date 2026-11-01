# Source integrity and historical impact — 2026-11-01

Status: **partial implementation; screened evidence, not proof of completeness**. Base revision `5cdac66677e6abb513f84e3ede5f74dd74d00bb6`. No models were trained or replaced in this audit.

`f1_racelab.data.source_integrity` audits exact OpenF1 JSON bytes. It records content SHA-256, source/provider/parameters, known retrieval time (or null), audit time, session identity, key/schema violations, duplicate laps, timestamps, durations, driver lap ranges and gaps. An optional cross-endpoint completed-laps reference and declared time window are comparisons, not independent proof of expected coverage. The telemetry screen reports time gaps, missing/nonfinite channels, observed ranges and units; negative speed/RPM are review flags, not silently corrected. Different tyres, retirements, safety cars, provider limits and missing rows prevent a universal expected count. The late-start (>3) and internal-gap (>20%) screens are heuristics; false positives and false negatives are possible. Null lap timestamps and durations are counted; the caller must decide whether the recorded uncertainty is acceptable for its feature contract.

`archive` copies bytes into content-addressed read-only snapshots or quarantine, writes separate immutable audit records, and checks collisions; this is local file integrity, not cryptographic signing or backup. `gated_lap_snapshot` blocks broken/review sources and requires a scoped rationale when completeness is unknown. `OpenF1Client.get_verified_laps` offers this gate explicitly, leaving existing callers unchanged. `dataset_manifest`, `publish_dataset_manifest`, and `verify_dataset_manifest` bind and verify source checksums, a transformation checksum, feature contract, cutoff and output checksum. They currently gate OpenF1 laps only; they do not rerun transformations or establish rights. No existing research producer is automatically migrated: **new studies must opt into this API until integrated**. Malformed legacy cached JSON is archived without changing the original; a malformed newly fetched response can fail in the existing client before archival. Audit records and datasets are local and not distributed in this PR. Research must verify applicable data permissions before redistribution; [OpenF1 API documentation](https://openf1.org/docs/) and [upstream license](https://github.com/br-g/openf1/blob/main/LICENSE) do not by themselves establish rights in every underlying timing source.

## Real cached-source comparison

Both responses are session 11234, Australia 2026 race. Actual retrieval times are unknown, not inferred from filesystem timestamps. The source files and prior artifacts were not overwritten.

| Snapshot | SHA-256 | Rows | Drivers | Late-start drivers | Finite durations | Outcome |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `data/raw/openf1/laps/4d508b0d238a5632e3d0.json` | `a6e52b3e34c806dfd507340086ef89c43ade9dfb832aad8654af24d0ba45d8b8` | 45 | 22 | 20 | 20 | review; quarantined copy |
| `data/processed/driver_dna_future/fresh_australia_audit/laps/4d508b0d238a5632e3d0.json` | `2a3fd6867dac686c4324573d65ca9c39b22ea822aaa1c724111490d1e4c536dd` | 1,008 | 22 | 0 | 1,003 | no screening anomaly; completeness unknown |

The newer response has two missing timestamps and five missing durations. The old response has zero duplicate keys and spans all 22 drivers and laps 1–58 globally: roster and global range alone would have missed its sparsity. Local audit records and immutable copies are under `data/processed/source_integrity/20261101/{records,quarantine,snapshots}`. Reproduce locally, substituting an available authorized archive root:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_source_integrity.py data/raw/openf1/laps/4d508b0d238a5632e3d0.json 11234 data/processed/source_integrity/20261101
PYTHONPATH=src .venv/bin/python scripts/audit_source_integrity.py data/processed/driver_dna_future/fresh_australia_audit/laps/4d508b0d238a5632e3d0.json 11234 data/processed/source_integrity/20261101
```

## Historical-impact review

- Race Pace's fetch manifest references the old response, but its coverage file records session 11234 as EMPTY. The saved pace frame (83,523 rows; SHA-256 `993cfaeb810883509bd9348e98a3b8a700813f4f509eeddcec22bd2c2e190ece`) and predictions (323,035 rows; SHA-256 `825ebe14d452c0322368f03deccface6d316ca18fc5eb711323d6db59a2139b5`) contain zero rows for that session. Published results remain reproducible **on that saved cohort**; broader coverage is provisional. A new dataset and chronological evaluation including Australia may change results in either direction. Other EMPTY entries need separate investigation and are not automatically evidence of truncation.
- Original Driver DNA metadata (1,749 rows; SHA-256 `df74abadef5adeb3a9c920a902aeb171240631227d909df3c8e26048de8c5b12`) contains no session 11234: no direct dependency found. PR #4's earlier 4,899-prefix failed attempt also lacked Australia and is not a valid six-session benchmark; preserve its failed artifacts. Its corrected 5,676-prefix study uses the newer snapshot and contains 777 Australia and 820 Japan prefixes. Its persistence-beats-trained-model conclusion remains tied to those corrected saved artifacts, not an assertion of universally complete data.
- The qualifying workflow uses practice/qualifying session results and drivers rather than these race laps; no direct dependency on session 11234 was found. For session 11230, 19 result rows versus 22 driver rows warrants separate review, not an assertion of three missing entrants: DNS/DNQ/entry evidence is needed. A manifest's 2023–2025 description despite containing 2026 is a separate provenance-description defect; old artifacts remain unchanged.

Further work: integrate gated snapshots and manifests into each new data producer; independently audit qualifying result coverage; establish provider-specific missing-channel and timestamp policies; measure source lineage across all historical snapshots. This is not a complete provider-ingestion solution.

### Reference coverage follow-up

When a cross-endpoint completed-lap reference is supplied, observed key shortfalls or a positive-lap reference driver with no source rows now require review. Zero-lap reference entries are not by themselves evidence of missing race data. Dataset creation checks the original archived audit as well as re-screening the bytes, so dropping a supplied reference cannot silently release a quarantined source. References remain fallible cross-endpoint evidence rather than an independent proof of completeness; preserve their provenance and investigate discrepancies.
