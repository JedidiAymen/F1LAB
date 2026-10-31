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

## Source and feasibility audit — 2026-10-31

The earlier statement that no licensed candidate exists is superseded by this
audit. **Training remains blocked**, for specific label/access/resource reasons:

| Candidate / primary source | Rights and annotations verified | Split / storage / decision |
| --- | --- | --- |
| [RACECAR, Link Lab UVA](https://github.com/linklab-uva/RACECAR_DATA) and [AWS registry](https://registry.opendata.aws/racecar-dataset/) | CC BY-NC 4.0 data; autonomous Indy racing, not F1. Camera/LiDAR/radar/odometry exist. Crucially, the README says annotation/taxonomy JSON files contain dummy entries because **annotations are absent**. | Eleven scenarios on two tracks; downloadable by scene. Archive sizes were not independently measured. Reject as an immediately scored detector benchmark without lawful manual labels; downloading imagery alone does not enable mAP. |
| [A2RL Vmax owner dataset card](https://huggingface.co/datasets/a2rl-vmax/a2rl-vmax) | CC BY-NC 4.0 data, gated account/terms acceptance. LiDAR/RADAR perception, 28,791 annotated keyframes; not an RGB F1 footage benchmark. Bundled code has separate notices/licenses that need review before reuse. | Native scene-aligned 247 train / 50 validation scenes; 24,168 / 4,623 keyframes. Published full repository is **67 GB**, exceeding this workstation's initial 6.5 GB free disk. CUDA/OpenPCDet toolchain and GT augmentation require a GPU; local NVIDIA driver unavailable. No account acceptance/download attempted. No untouched test split claimed. |
| [CARLA code license](https://github.com/carla-simulator/carla/blob/master/LICENSE), [owner repository](https://github.com/carla-simulator/carla) | Simulator code MIT; assets have separate Creative Commons attribution terms. Code licensing alone does not settle release/asset-specific rendering redistribution. Synthetic camera/ground-truth generation is possible in principle. | No selected release, permitted asset set, trained model or scene-split evaluation executed. Installation/storage and rendering feasibility were not measured. Do not present rendered imagery as real racing/F1 footage. |

RACECAR annotation finding is from the upstream README's **RACECAR nuScenes**
section, not a downloaded archive audit. A2RL figures are owner-published
metadata, not F1LAB training results. Links were checked through primary sources;
no large archives, protected videos, third-party model code or assets were copied.

Next workable gate: select a genuinely annotated permitted small RGB dataset
or secure an A2RL subset/access plus storage and functioning GPU; freeze
scene-level splits before training. Detector mAP, tracker IDF1/ID switches,
latency and qualitative failure analysis remain **not measured**. Existing
hardware model ownership does not imply a currently working CUDA device.
