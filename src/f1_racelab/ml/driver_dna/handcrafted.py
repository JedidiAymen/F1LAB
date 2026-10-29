"""Interpretable lap descriptors from the [6, GRID] tensors (channels: speed, throttle, brake, gear, rpm, drs)."""
from __future__ import annotations

import numpy as np

NAMES = ["speed_mean", "speed_p10", "speed_p90", "speed_std", "full_throttle", "throttle_mean", "throttle_changes",
         "brake_fraction", "brake_events", "gear_changes", "gear_mean", "rpm_mean", "rpm_p90", "drs_fraction",
         "accel_p95", "decel_p05", "coast_fraction"]


def describe(x: np.ndarray, scales: np.ndarray) -> np.ndarray:
    """x: [N, 6, G] in raw units divided by nothing (raw), returns [N, len(NAMES)] (circuit-agnostic stats)."""
    speed, throttle, brake, gear, rpm, drs = (x[:, i] for i in range(6))
    d_speed = np.diff(speed, axis=1)
    on_brake = brake > 20
    feats = [speed.mean(1), np.percentile(speed, 10, 1), np.percentile(speed, 90, 1), speed.std(1),
             (throttle >= 98).mean(1), throttle.mean(1), (np.abs(np.diff(throttle, axis=1)) > 20).sum(1),
             on_brake.mean(1), (np.diff(on_brake.astype(int), axis=1) == 1).sum(1),
             (np.diff(gear, axis=1) != 0).sum(1), gear.mean(1), rpm.mean(1), np.percentile(rpm, 90, 1), drs.mean(1),
             np.percentile(d_speed, 95, 1), np.percentile(d_speed, 5, 1), ((throttle < 5) & ~on_brake).mean(1)]
    del scales
    return np.stack(feats, axis=1).astype(np.float32)
