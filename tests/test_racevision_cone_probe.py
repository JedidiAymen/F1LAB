"""Optional dependencies: tests use synthetic boxes and never download model weights."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torchvision')
pytest.importorskip('pycocotools')
from PIL import Image

spec = importlib.util.spec_from_file_location('cone_probe', Path(__file__).parents[1] / 'scripts/racevision/train_fsoco_probe.py')
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_greedy_detection_matching_penalizes_duplicate_boxes():
    boxes = torch.tensor([[0., 0., 10., 10.], [0., 0., 10., 10.], [20., 20., 30., 30.]])
    scores = torch.tensor([0.9, 0.8, 0.2])
    truth = torch.tensor([[0., 0., 10., 10.]])
    assert probe.score_at_threshold(boxes, scores, truth) == (1, 1, 0)


def test_empty_predictions_and_truth_are_counted_correctly():
    boxes = torch.empty((0, 4))
    assert probe.score_at_threshold(boxes, torch.empty(0), torch.tensor([[0., 0., 1., 1.]])) == (0, 0, 1)
    assert probe.score_at_threshold(torch.tensor([[0., 0., 1., 1.]]), torch.tensor([0.8]), boxes) == (0, 1, 0)


def test_conditional_frame_bootstrap_recall_handles_empty_and_perfect_cases():
    assert probe.frame_bootstrap_recall([]) is None
    assert probe.frame_bootstrap_recall([(0, 0, 0)]) is None
    assert probe.frame_bootstrap_recall([(2, 1, 0), (1, 0, 0)]) == [1.0, 1.0]


def test_dataset_checks_source_hashes_and_annotation_geometry(tmp_path):
    image = tmp_path / 'image.png'
    annotation = tmp_path / 'image.json'
    Image.new('RGB', (20, 10)).save(image)
    annotation.write_text(json.dumps({'size': {'width': 20, 'height': 10}, 'objects': [{
        'classTitle': 'blue_cone', 'geometryType': 'rectangle', 'points': {'exterior': [[1, 2], [5, 8]]},
    }]}))
    entry = lambda path: {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {'records': [{'split': 'train', 'image': entry(image), 'annotation': entry(annotation)}]}
    dataset = probe.ConeDataset(tmp_path, manifest, 'train')
    tensor, target = dataset[0]
    assert tuple(tensor.shape) == (3, 10, 20) and target['boxes'].tolist() == [[1, 2, 5, 8]]
    annotation.write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        probe.ConeDataset(tmp_path, manifest, 'train')
