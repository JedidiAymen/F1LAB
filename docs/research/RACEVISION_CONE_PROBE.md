# RaceVision: exploratory FSOCO cone detector probe

Status: **implemented and evaluated, unsuccessful under this protocol; not a completed RaceVision system**. [Preregistered protocol and pre-download split correction](FSOCO_CONE_PROTOCOL.md); frozen training source `3c9a948f110879b7914daad61cc0a79eb4ed39a0`. Formula Student Driverless cone images are not Formula 1 broadcasts and do not establish race-car detection, video tracking or on-track deployment quality.

## Data and rights

The official [FSOCO download](https://fsoco.github.io/fsoco-dataset/download) explicitly offers its training dataset for cone detection; the [overview](https://fsoco.github.io/fsoco-dataset/overview/) describes human-labeled cone boxes. Redistribution permission and original contributor image licenses were not established. The archive is fetched over unauthenticated HTTP; SHA-256 and ZIP CRC detect later changes, not origin impersonation. No source imagery, annotations, image-containing screenshots or model weights are distributed in this PR. The local user must respect source rights and independently assess any redistribution or deployment.

From the official ZIP, range-fetch 140 paired frames under the frozen filename-prefix protocol: 100 train (25 each from `amz`, `BME`, `mms`, `ff`), 20 validation (`ka`), 20 test (`gfr`). The 20 test images contain 255 labeled boxes; 20 validation images contain 464. Folder names can contain different prefixes, and prefix is not a verified sequence/circuit identity. Exact duplicate image hashes across splits are rejected, but near-duplicate frames and shared venues remain possible. All cone classes are collapsed to one; no truncation or difficult label is intentionally excluded. The selected manifest SHA-256 is `646c9a4961bfeeaed19b35fdfdaad95db988b94a501fc6347284d25cddeefe42`; 227,489,891 bytes were transferred and source files remain under `data/processed/racevision/fsoco_cone_20261101`.

## Models and held-out results

Torchvision SSDLite320 MobileNet V3 Large starts from the official COCO detector weights (SHA-256 `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`); its classification head was replaced with background + cone and fine-tuned for three fixed epochs. The COCO baseline's predicted categories are collapsed to one class; COCO has no cone label and no extra class-agnostic suppression is performed. It is a transfer reference rather than an ideal specialized baseline. Evaluation uses COCO bounding-box metrics on the same 20 test frames, once per model after the frozen protocol. The saved candidate state was reloaded with `weights_only=True` before test scoring.

| Model | mAP@50 | mAP@50:95 | Precision at confidence .5 / IoU .5 | Recall at confidence .5 / IoU .5 |
| --- | ---: | ---: | ---: | ---: |
| COCO transfer reference | 0.021294 | 0.005272 | 0 / 5 = 0.000 | 0 / 255 = 0.000 |
| Fine-tuned detector | 0.021453 | 0.005628 | 0 / 1 = 0.000 | 0 / 255 = 0.000 |

Both are poor. The tiny AP difference does not establish improvement; neither model should be promoted. For each model the 1,000-resample conditional frame bootstrap for threshold recall was [0, 0], which only reflects the observed zero true positives in these potentially correlated frames and is **not** an interval for new tracks or teams. Test AP was independently recomputed from saved prediction boxes and original annotation JSON with `recompute_fsoco_metrics.py` and matched saved values to 1e-12. There is no AP confidence interval or independent sequence-level validation.

Training losses over epochs were 9.6212, 7.1177 and 6.1252; validation mAP@50 was 0.000026, 0.000750 and 0.002694. Lower training loss did not yield a useful held-out detector. On test frame 1 the candidate's only confidence ≥0.5 box scored 0.500055, overlapped no ground-truth box (best IoU 0), and all 14 labeled cones were missed at the registered operating point. The 320×320 input, small/distant cones, limited data and domain shift are plausible contributors, not established causes. Low-score predictions and the baseline contain numerous false positives; inspect the local UI rather than infer reliability from AP alone.

The actual run used Python 3.12.13, PyTorch 2.15.0+cu132, torchvision 0.29.2+cu132, pycocotools 2.0.11, seed 42 and an NVIDIA RTX 3050 6 GB Laptop GPU. Full run after initialization took 25.23 s including training and evaluation; peak allocated GPU memory was 568,065,024 bytes. Mean model call after the first test frame was 11.10 ms candidate and 32.76 ms baseline, excluding image decoding and host-to-device transfer; this is not end-to-end video latency. The local model `data/processed/racevision/fsoco_cone_probe_20261101/detector.pth` is 8.8 MiB with SHA-256 `a055b56f58c3769553315bef6b3dadfcf59adb44e79f367462bbc5abac4585f8`. Predictions SHA-256 `cbcd9fa412389ff7f287bc35f9781a70110dd741d8d06dac1ac934cfe3585482`; [saved metrics](evidence/fsoco_cone_20261101/metrics.json) SHA-256 `4e1667252bdf742ddccc95b01e5bf08ba406c6fe592f00f3335a3176a18ac73f`. Model weights are local, not a bundled or promoted serving artifact.

## Local investigation interface

`GET /api/v1/research/racevision/cones` returns saved metrics; `/cones/{frame_id}` returns original labeled and saved prediction boxes; `/cones/{frame_id}/image` serves the local source image after SHA-256 and path-boundary checks. The Research & reliability workspace includes frame/model/threshold selection, overlays, confidences and provenance. With artifacts absent, it reports an unavailable state while the basic app remains usable. The interface reads saved outputs; it does not perform live inference, process video, track IDs or authenticate users. Run locally; do not expose it publicly. Desktop/mobile screenshots were rendered and reviewed locally but are not included because image redistribution rights remain unresolved.

## Reproduction

Use the original source revision for training, because the script verifies its checkout. With the main project `.venv` containing the stated GPU PyTorch build, the exact local optional environment used was created without changing project dependencies:

```bash
git worktree add --detach /tmp/f1lab-cone-training 3c9a948f110879b7914daad61cc0a79eb4ed39a0
uv venv --python /path/to/F1LAB/.venv/bin/python /tmp/f1lab-cv-env
UV_CACHE_DIR=/tmp/f1lab-cv-cache uv pip install --python /tmp/f1lab-cv-env/bin/python --no-deps torchvision==0.29.2 pycocotools==2.0.11
export PYTHONPATH=/path/to/F1LAB/.venv/lib/python3.12/site-packages
export TORCH_HOME=/tmp/f1lab-torch-cache
export CUBLAS_WORKSPACE_CONFIG=:4096:8
cd /tmp/f1lab-cone-training
/tmp/f1lab-cv-env/bin/python scripts/racevision/fetch_fsoco_subset.py --out /path/to/local/fsoco_cone_20261101
/tmp/f1lab-cv-env/bin/python -c 'from torchvision.models.detection import ssdlite320_mobilenet_v3_large, SSDLite320_MobileNet_V3_Large_Weights as W; ssdlite320_mobilenet_v3_large(weights=W.DEFAULT)'
/tmp/f1lab-cv-env/bin/python scripts/racevision/train_fsoco_probe.py --source /path/to/local/fsoco_cone_20261101 --out /path/to/new/run --source-revision 3c9a948f110879b7914daad61cc0a79eb4ed39a0 --pretrained-weights /tmp/f1lab-torch-cache/hub/checkpoints/ssdlite320_mobilenet_v3_large_coco-a79551df.pth
```

The independent recomputation script was added after that frozen revision; run it from the current review branch with `--source /path/to/local/fsoco_cone_20261101 --run /path/to/new/run`. Matching exact bytes on different GPU, CUDA or package versions is not guaranteed. `torchvision`'s code is BSD-licensed and pycocotools is FreeBSD-licensed; check PyTorch's package notices and the upstream pretrained-weight terms separately. This optional stack is not a new dependency for basic F1LAB.

Next: establish independent sequence/venue grouping and source permissions, register a fresh validation/test split, investigate resolution and calibration without tuning on this inspected test set, compare a meaningful specialized baseline, and only then consider video or tracking with suitable ground truth. No IDF1/HOTA, trajectory accuracy, video FPS or race-car mAP has been measured.

Provenance limitation: the original fetch did not record per-request retrieval timestamps. A later [audit record](evidence/fsoco_cone_20261101/retrieval_audit.json) marks retrieval time unknown instead of deriving it from file modification times. The [dataset manifest](evidence/fsoco_cone_20261101/dataset_manifest.json) records source paths, per-file SHA-256 and ZIP CRC, but does not authenticate the HTTP source or establish underlying image rights.
