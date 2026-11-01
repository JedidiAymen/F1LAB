"""Read a local, checksum-verified FSOCO detector study; never load model code."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _bounded_file(root: Path, relative: str, expected_sha: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Invalid source path')
    full = (root / path).resolve()
    if not full.is_relative_to(root.resolve()) or not full.is_file():
        raise ValueError('Source path is missing or outside the dataset')
    if _digest(full) != expected_sha:
        raise ValueError('Source checksum mismatch')
    return full


def load_study(dataset: Path, run: Path) -> dict:
    manifest_path, metrics_path, predictions_path = dataset / 'manifest.json', run / 'metrics.json', run / 'test_predictions.json'
    metrics = json.loads(metrics_path.read_text())
    if _digest(manifest_path) != metrics['dataset_manifest_sha256'] or _digest(predictions_path) != metrics['test_predictions_sha256']:
        raise ValueError('Study manifest or prediction checksum mismatch')
    if _digest(run / 'detector.pth') != metrics['model_sha256']:
        raise ValueError('Detector checksum mismatch')
    manifest = json.loads(manifest_path.read_text())
    rows = [row for row in manifest['records'] if row['split'] == 'test']
    if len(rows) != metrics['fine_tuned']['images'] or not rows:
        raise ValueError('Test-frame count disagrees with metrics')
    predictions = json.loads(predictions_path.read_text())
    if set(predictions) != {'baseline', 'fine_tuned'}:
        raise ValueError('Unexpected prediction sets')
    return {'metrics': metrics, 'rows': rows, 'predictions': predictions}


def frame(dataset: Path, study: dict, frame_id: int) -> dict:
    rows = study['rows']
    if frame_id < 1 or frame_id > len(rows):
        raise IndexError('Unknown frame')
    row = rows[frame_id - 1]
    _bounded_file(dataset, row['image']['path'], row['image']['sha256'])
    annotation_path = _bounded_file(dataset, row['annotation']['path'], row['annotation']['sha256'])
    annotation = json.loads(annotation_path.read_text())
    width, height = annotation['size']['width'], annotation['size']['height']
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ValueError('Invalid image dimensions')
    truth = []
    for obj in annotation['objects']:
        if obj['geometryType'] != 'rectangle' or not obj['classTitle'].lower().endswith('_cone'):
            raise ValueError('Unexpected annotation type')
        (x1, y1), (x2, y2) = obj['points']['exterior']
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError('Invalid ground-truth box')
        truth.append({'bbox': [x1, y1, x2 - x1, y2 - y1], 'class_name': obj['classTitle']})
    output = {}
    for arm, entries in study['predictions'].items():
        matches = []
        for item in entries:
            if item['image_id'] != frame_id:
                continue
            x, y, w, h = item['bbox']
            score = item['score']
            if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in (x, y, w, h, score)) or w <= 0 or h <= 0 or not 0 <= score <= 1:
                raise ValueError('Invalid prediction box')
            if x < -0.001 or y < -0.001 or x + w > width + 0.001 or y + h > height + 0.001:
                raise ValueError('Prediction lies outside the frame')
            matches.append({'bbox': [x, y, w, h], 'score': score})
        output[arm] = matches
    return {'frame_id': frame_id, 'frame_count': len(rows), 'width': width, 'height': height,
            'filename_prefix': row['filename_prefix'], 'image_sha256': row['image']['sha256'],
            'ground_truth': truth, 'predictions': output}


def frame_image(dataset: Path, study: dict, frame_id: int) -> Path:
    if frame_id < 1 or frame_id > len(study['rows']):
        raise IndexError('Unknown frame')
    row = study['rows'][frame_id - 1]
    path = _bounded_file(dataset, row['image']['path'], row['image']['sha256'])
    if path.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
        raise ValueError('Unsupported image type')
    return path
