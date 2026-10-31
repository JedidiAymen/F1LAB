"""CPU inductive residual regressors; original identity classifiers stay unchanged."""
from __future__ import annotations

import copy

import numpy as np
import torch
from torch import nn

from f1_racelab.ml.driver_dna.nets import Encoder, seed_all


class RemainingLapNet(nn.Module):
    def __init__(self, context: bool = True):
        super().__init__()
        self.use_context = context
        self.encoder = Encoder(channels=5, width=16, dim=32)
        self.head = nn.Sequential(nn.Linear(64 + (3 if context else 0), 32), nn.GELU(),
                                  nn.Dropout(0.1), nn.Linear(32, 1))

    def forward(self, x, context):
        z = self.encoder(x)
        if self.use_context:
            z = torch.cat([z, context], dim=1)
        return self.head(z).squeeze(1)


def fit(x: np.ndarray, context: np.ndarray, residual: np.ndarray, train: np.ndarray, validation: np.ndarray,
        *, seed: int, use_context: bool = True, masked: bool = False) -> tuple[RemainingLapNet, list[dict]]:
    """All arrays are preprocessed with training-only statistics by the caller."""
    torch.set_num_threads(2)
    seed_all(seed)
    model = RemainingLapNet(use_context)
    xt, ct, yt = (torch.as_tensor(a, dtype=torch.float32) for a in (x, context, residual))
    ti, vi = torch.as_tensor(train), torch.as_tensor(validation)
    curves = []
    if masked:
        decoder = nn.Linear(64, 5)
        optimizer = torch.optim.AdamW([*model.encoder.parameters(), *decoder.parameters()], lr=0.001,
                                      weight_decay=0.001)
        for epoch in range(10):
            model.train()
            losses = []
            for batch in ti[torch.randperm(len(ti))].split(64):
                if len(batch) < 2:
                    continue
                mask = torch.rand_like(xt[batch]) < 0.5
                corrupted = xt[batch].masked_fill(mask, 0)
                # Prefix channel means form a small self-supervised reconstruction
                # target; no future target or held-out prefix enters pretraining.
                loss = nn.functional.mse_loss(decoder(model.encoder(corrupted)), xt[batch].mean(-1))
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
                losses.append(float(loss.detach()))
            curves.append({"stage": "masked_prefix", "epoch": epoch + 1, "loss": float(np.mean(losses))})
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.001)
    best, best_state, patience = float("inf"), copy.deepcopy(model.state_dict()), 0
    for epoch in range(25):
        model.train()
        losses = []
        for batch in ti[torch.randperm(len(ti))].split(64):
            if len(batch) < 2:
                continue
            loss = nn.functional.smooth_l1_loss(model(xt[batch], ct[batch]), yt[batch])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            score = float((model(xt[vi], ct[vi]) - yt[vi]).abs().mean())
        curves.append({"stage": "supervised", "epoch": epoch + 1, "train_loss": float(np.mean(losses)),
                       "validation_scaled_mae": score})
        if score < best:
            best, best_state, patience = score, copy.deepcopy(model.state_dict()), 0
        else:
            patience += 1
        if patience >= 5:
            break
    model.load_state_dict(best_state)
    return model.eval(), curves


@torch.no_grad()
def predict(model: RemainingLapNet, x: np.ndarray, context: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    predictions, embeddings = [], []
    for start in range(0, len(x), 256):
        batch = torch.as_tensor(x[start:start + 256], dtype=torch.float32)
        ctx = torch.as_tensor(context[start:start + 256], dtype=torch.float32)
        predictions.append(model(batch, ctx).numpy())
        embeddings.append(model.encoder(batch).numpy())
    return np.concatenate(predictions), np.concatenate(embeddings)
