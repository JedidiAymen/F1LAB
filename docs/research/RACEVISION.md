# RaceVision: status BLOCKED (no training or results)

**Not implemented. No detector, tracker or accuracy figure exists.** The mandate requires a legally usable camera dataset before any training. None is available:

* The repository and `data/` contain no images or video (checked: no .mp4/.mkv/.jpg files).
* Formula 1 broadcast footage and onboard streams are protected; they must not be downloaded, stored or redistributed (project rule in `AGENTS.md`).
* No third-party dataset with a verified licence permitting this use has been selected. Candidates must be checked individually (licence text, attribution, non-commercial limits, whether F1 imagery is included) before download.

## Unblock criteria
1. A named dataset or owner-supplied footage with a written licence that allows model training and evaluation; record the licence URL and SHA-256 of every archive in `DATA_CONTRACTS.md`.
2. Per-race (or per-video) train/validation/test split; no frame-level random split.
3. Baseline first (pretrained detector with no fine-tuning), then fine-tune; report mAP@0.5 and mAP@0.5:0.95 by split, tracking metrics (IDF1, ID switches) and failure cases.
4. UI shows "detections are image-derived estimates" and never fuses them with timing state without a flag.

Hardware note: an RTX 3050 6 GB is enough for a small YOLO-class fine-tune; torch is already available via `uv sync --extra dl`.
