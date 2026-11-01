"""Independently recompute saved COCO test AP from source labels and predictions."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    metrics = json.loads((args.run / 'metrics.json').read_text())
    manifest_path, pred_path = args.source / 'manifest.json', args.run / 'test_predictions.json'
    if sha(manifest_path) != metrics['dataset_manifest_sha256'] or sha(pred_path) != metrics['test_predictions_sha256']:
        raise ValueError('Input checksum mismatch')
    manifest = json.loads(manifest_path.read_text())
    entries = [row for row in manifest['records'] if row['split'] == 'test']
    images, annotations = [], []
    for image_id, row in enumerate(entries, 1):
        path = args.source / row['annotation']['path']
        if sha(path) != row['annotation']['sha256']:
            raise ValueError('Annotation checksum mismatch')
        source = json.loads(path.read_text())
        images.append({'id': image_id, **source['size']})
        for obj in source['objects']:
            (x1, y1), (x2, y2) = obj['points']['exterior']
            w, h = x2 - x1, y2 - y1
            annotations.append({'id': len(annotations) + 1, 'image_id': image_id, 'category_id': 1,
                                'bbox': [x1, y1, w, h], 'area': w * h, 'iscrowd': 0})
    reference = COCO()
    reference.dataset = {'info': {}, 'images': images, 'annotations': annotations,
                         'categories': [{'id': 1, 'name': 'cone'}]}
    reference.createIndex()
    saved = json.loads(pred_path.read_text())
    for name in ('baseline', 'fine_tuned'):
        evaluator = COCOeval(reference, reference.loadRes(saved[name]), 'bbox')
        evaluator.evaluate()
        evaluator.accumulate()
        evaluator.summarize()
        for index, key in ((0, 'map_50_95'), (1, 'map_50')):
            if not math.isclose(float(evaluator.stats[index]), metrics[name][key], abs_tol=1e-12):
                raise ValueError(f'{name} {key} does not match saved metric')
        print(f'{name}: independent AP50={evaluator.stats[1]:.9f}, AP50:95={evaluator.stats[0]:.9f}')


if __name__ == '__main__':
    main()
