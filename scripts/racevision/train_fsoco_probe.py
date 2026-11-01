"""Run the frozen, exploratory prefix-held-out FSOCO cone detector protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import time
from functools import partial
from pathlib import Path

import numpy as np
import torch
import torchvision
from PIL import Image
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision.models.detection import (
    SSDLite320_MobileNet_V3_Large_Weights,
    ssdlite320_mobilenet_v3_large,
)
from torchvision.models.detection.ssdlite import SSDLiteClassificationHead
from torchvision.ops import box_iou
from torchvision.transforms.functional import pil_to_tensor


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConeDataset(Dataset):
    def __init__(self, root: Path, manifest: dict, split: str):
        self.root = root
        self.rows = [r for r in manifest['records'] if r['split'] == split]
        if not self.rows:
            raise ValueError('Empty split')
        self.targets = []
        for row in self.rows:
            for key in ('image', 'annotation'):
                relative = Path(row[key]['path'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Invalid source path')
                if digest(root / relative) != row[key]['sha256']:
                    raise ValueError('Source checksum mismatch')
            annotation = json.loads((root / row['annotation']['path']).read_text())
            width, height = annotation['size']['width'], annotation['size']['height']
            boxes = []
            for obj in annotation['objects']:
                if obj['geometryType'] != 'rectangle' or not obj['classTitle'].lower().endswith('_cone'):
                    raise ValueError(f'Unrecognized annotation: {obj["classTitle"]}, {obj["geometryType"]}')
                (x1, y1), (x2, y2) = obj['points']['exterior']
                if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                    raise ValueError(f'Invalid box in {row["annotation"]["path"]}')
                boxes.append([x1, y1, x2, y2])
            self.targets.append({'boxes': boxes, 'width': width, 'height': height})

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        row, target = self.rows[index], self.targets[index]
        with Image.open(self.root / row['image']['path']) as source:
            image = source.convert('RGB')
            if image.size != (target['width'], target['height']):
                raise ValueError('Image dimensions disagree with annotation')
            tensor = pil_to_tensor(image).float() / 255
        boxes = torch.tensor(target['boxes'], dtype=torch.float32).reshape(-1, 4)
        return tensor, {'boxes': boxes, 'labels': torch.ones(len(boxes), dtype=torch.int64)}


def score_at_threshold(boxes: torch.Tensor, scores: torch.Tensor, truth: torch.Tensor) -> tuple[int, int, int]:
    """Score-threshold 0.5, greedy IoU 0.5; unmatched detections/truth remain errors."""
    keep = torch.where(scores >= 0.5)[0]
    keep = keep[torch.argsort(scores[keep], descending=True)]
    overlaps = box_iou(boxes[keep], truth) if len(keep) and len(truth) else torch.zeros((len(keep), len(truth)))
    used: set[int] = set()
    tp = 0
    for row in overlaps:
        candidates = sorted(((float(v), i) for i, v in enumerate(row) if i not in used), reverse=True)
        if candidates and candidates[0][0] >= 0.5:
            used.add(candidates[0][1])
            tp += 1
    return tp, len(keep) - tp, len(truth) - tp


def evaluate(model, dataset: ConeDataset, device: torch.device) -> tuple[dict, list]:
    model.eval()
    images, annotations, detections = [], [], []
    latency, totals = [], np.zeros(3, dtype=int)
    ann_id = 1
    with torch.inference_mode():
        for index in range(len(dataset)):
            image, target = dataset[index]
            info = dataset.targets[index]
            image_id = index + 1
            images.append({'id': image_id, 'width': info['width'], 'height': info['height']})
            for x1, y1, x2, y2 in info['boxes']:
                annotations.append({'id': ann_id, 'image_id': image_id, 'category_id': 1,
                                    'bbox': [x1, y1, x2 - x1, y2 - y1], 'area': (x2 - x1) * (y2 - y1), 'iscrowd': 0})
                ann_id += 1
            image = image.to(device)
            if device.type == 'cuda':
                torch.cuda.synchronize()
            start = time.perf_counter()
            output = model([image])[0]
            if device.type == 'cuda':
                torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            if index:  # first invocation includes initialization
                latency.append(elapsed)
            boxes, scores = output['boxes'].cpu(), output['scores'].cpu()
            totals += score_at_threshold(boxes, scores, target['boxes'])
            for box, score in zip(boxes.tolist(), scores.tolist()):
                x1, y1, x2, y2 = box
                detections.append({'image_id': image_id, 'category_id': 1, 'bbox': [x1, y1, x2 - x1, y2 - y1], 'score': score})
    coco = COCO()
    coco.dataset = {'info': {}, 'images': images, 'annotations': annotations, 'categories': [{'id': 1, 'name': 'cone'}]}
    coco.createIndex()
    if not detections:
        raise ValueError('No predictions for COCO evaluation')
    result = coco.loadRes(detections)
    evaluator = COCOeval(coco, result, 'bbox')
    evaluator.evaluate()
    evaluator.accumulate()
    evaluator.summarize()
    tp, fp, fn = map(int, totals)
    return {'images': len(dataset), 'ground_truth_boxes': len(annotations), 'predicted_boxes': len(detections),
            'map_50_95': float(evaluator.stats[0]), 'map_50': float(evaluator.stats[1]),
            'mean_recall_100': float(evaluator.stats[8]), 'threshold': 0.5,
            'precision_at_50_iou': tp / (tp + fp) if tp + fp else None,
            'recall_at_50_iou': tp / (tp + fn) if tp + fn else None,
            'true_positive': tp, 'false_positive': fp, 'false_negative': fn,
            'mean_model_seconds_excluding_decode_first': float(np.mean(latency)) if latency else None}, detections


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source-revision', required=True, help='Frozen source commit for this run')
    parser.add_argument('--pretrained-weights', type=Path, required=True, help='Torchvision cached COCO checkpoint')
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    actual_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repository, text=True).strip()
    if actual_revision != args.source_revision:
        raise ValueError('Source revision does not match checkout')
    if subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', 'scripts/racevision',
                       'docs/research/FSOCO_CONE_PROTOCOL.md'], cwd=repository, check=False).returncode != 0:
        raise ValueError('Research code or protocol has uncommitted changes')
    if os.environ.get('CUBLAS_WORKSPACE_CONFIG') not in {':4096:8', ':16:8'}:
        raise ValueError('Set CUBLAS_WORKSPACE_CONFIG=:4096:8 before starting Python')
    if args.out.exists():
        raise FileExistsError('Output directory already exists; choose a new immutable run path')
    manifest_path = args.source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    expected_prefixes = {'train': {'amz', 'BME', 'mms', 'ff'}, 'val': {'ka'}, 'test': {'gfr'}}
    for split, expected in expected_prefixes.items():
        rows = [row for row in manifest['records'] if row['split'] == split]
        prefixes = {row['filename_prefix'] for row in rows}
        if prefixes != expected:
            raise ValueError(f'Unexpected filename-prefix assignment in {split}')
        for prefix in expected:
            if sum(row['filename_prefix'] == prefix for row in rows) != (25 if split == 'train' else 20):
                raise ValueError(f'Unexpected sample count for {prefix}')
        if any(not Path(row['image']['path']).name.lower().startswith(row['filename_prefix'].lower() + '_') for row in rows):
            raise ValueError('Filename does not match assigned prefix')
    paths = [row['image']['path'] for row in manifest['records']]
    if len(paths) != len(set(paths)):
        raise ValueError('Duplicate source image')
    hash_splits: dict[str, str] = {}
    for row in manifest['records']:
        source_hash = row['image']['sha256']
        if source_hash in hash_splits and hash_splits[source_hash] != row['split']:
            raise ValueError('Identical source images occur in multiple splits')
        hash_splits[source_hash] = row['split']
    datasets = {split: ConeDataset(args.source, manifest, split) for split in ('train', 'val', 'test')}
    if [len(datasets[s]) for s in ('train', 'val', 'test')] != [100, 20, 20]:
        raise ValueError('Split sizes disagree with frozen protocol')
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    torch.use_deterministic_algorithms(True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    expected_cache = Path(torch.hub.get_dir()) / 'checkpoints/ssdlite320_mobilenet_v3_large_coco-a79551df.pth'
    if args.pretrained_weights.resolve() != expected_cache.resolve() or digest(expected_cache) != 'a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2':
        raise ValueError('Unexpected pretrained checkpoint checksum')
    weights = SSDLite320_MobileNet_V3_Large_Weights.DEFAULT
    model = ssdlite320_mobilenet_v3_large(weights=weights).to(device)
    anchors = model.anchor_generator.num_anchors_per_location()
    channels = [layer[0][0].in_channels for layer in model.head.classification_head.module_list]
    model.head.classification_head = SSDLiteClassificationHead(channels, anchors, 2,
        partial(nn.BatchNorm2d, eps=0.001, momentum=0.03)).to(device)
    optimizer = torch.optim.SGD([p for p in model.parameters() if p.requires_grad], lr=0.001, momentum=0.9)
    loader = DataLoader(datasets['train'], batch_size=4, shuffle=True, num_workers=0, collate_fn=lambda x: tuple(zip(*x)),
                        generator=torch.Generator().manual_seed(42))
    args.out.mkdir(parents=True)
    started = time.perf_counter()
    if device.type == 'cuda':
        torch.cuda.reset_peak_memory_stats()
    history = []
    for epoch in range(3):
        model.train()
        losses = []
        for images, targets in loader:
            images = [image.to(device) for image in images]
            targets = [{k: v.to(device) for k, v in target.items()} for target in targets]
            loss = sum(model(images, targets).values())
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        validation, _ = evaluate(model, datasets['val'], device)
        history.append({'epoch': epoch + 1, 'mean_training_loss': float(np.mean(losses)), 'validation': validation})
        print(json.dumps(history[-1]), flush=True)
    torch.save(model.state_dict(), args.out / 'detector.pth')
    candidate, candidate_predictions = evaluate(model, datasets['test'], device)
    baseline = ssdlite320_mobilenet_v3_large(weights=weights).to(device)
    baseline_metrics, baseline_predictions = evaluate(baseline, datasets['test'], device)
    output = {'protocol': 'docs/research/FSOCO_CONE_PROTOCOL.md', 'dataset_manifest_sha256': digest(manifest_path),
              'source_revision': args.source_revision, 'model_sha256': digest(args.out / 'detector.pth'),
              'pretrained_sha256': digest(args.pretrained_weights), 'seed': 42, 'epochs': 3, 'batch_size': 4,
              'device': str(device), 'gpu': torch.cuda.get_device_name(0) if device.type == 'cuda' else None,
              'python': platform.python_version(), 'torch': torch.__version__, 'torchvision': torchvision.__version__,
              'total_seconds': time.perf_counter() - started,
              'peak_gpu_bytes': torch.cuda.max_memory_allocated() if device.type == 'cuda' else None,
              'training_history': history, 'baseline': baseline_metrics, 'fine_tuned': candidate}
    (args.out / 'metrics.json').write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    (args.out / 'test_predictions.json').write_text(json.dumps({'baseline': baseline_predictions, 'fine_tuned': candidate_predictions}))
    print(json.dumps(output, indent=2), flush=True)


if __name__ == '__main__':
    main()
