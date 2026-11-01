"""Optional dependencies: tests use synthetic boxes and never download model weights."""
import importlib.util
from pathlib import Path

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torchvision')
pytest.importorskip('pycocotools')

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
