"""PyTorch models for Driver DNA: dilated TCN classifier and SimCLR-style contrastive encoder.

Inputs are [N, 6, GRID] tensors z-scored per circuit and grid point (`protocol.normalise_per_circuit`). Everything is seeded; training
uses only the train indices handed in by the protocol. Optional dependency: ``uv sync --extra dl``.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def seed_all(seed: int) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


class Block(nn.Module):
    def __init__(self, cin: int, cout: int, dilation: int):
        super().__init__()
        self.conv1 = nn.Conv1d(cin, cout, 5, padding=2 * dilation, dilation=dilation)
        self.conv2 = nn.Conv1d(cout, cout, 5, padding=2 * dilation, dilation=dilation)
        self.norm1, self.norm2 = nn.BatchNorm1d(cout), nn.BatchNorm1d(cout)
        self.skip = nn.Conv1d(cin, cout, 1) if cin != cout else nn.Identity()

    def forward(self, x):
        y = F.gelu(self.norm1(self.conv1(x)))
        y = self.norm2(self.conv2(y))
        return F.gelu(y + self.skip(x))


class Encoder(nn.Module):
    """Dilated residual TCN -> [mean ‖ max] pooled embedding."""

    def __init__(self, channels: int = 6, width: int = 32, dim: int = 64):
        super().__init__()
        self.blocks = nn.Sequential(Block(channels, width, 1), Block(width, width, 2), Block(width, dim, 4),
                                    Block(dim, dim, 8))
        self.dim = dim * 2

    def forward(self, x):
        h = self.blocks(x)
        return torch.cat([h.mean(-1), h.amax(-1)], dim=-1)


class Classifier(nn.Module):
    def __init__(self, classes: int, dropout: float = 0.3):
        super().__init__()
        self.encoder = Encoder()
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(self.encoder.dim, classes))

    def forward(self, x):
        return self.head(self.encoder(x))


def augment(x: torch.Tensor, strength: float = 1.0) -> torch.Tensor:
    """Gaussian noise, a small circular shift and a random channel drop (all label-preserving)."""
    n = x.shape[0]
    x = x + 0.1 * strength * torch.randn_like(x)
    shift = int(torch.randint(-3, 4, (1,)))
    x = torch.roll(x, shift, dims=-1)
    drop = (torch.rand(n, x.shape[1], 1, device=x.device) < 0.1 * strength).float()
    return x * (1 - drop)


def _tensor(x: np.ndarray) -> torch.Tensor:
    return torch.as_tensor(x, dtype=torch.float32, device=DEVICE)


def fit_classifier(x: np.ndarray, y: np.ndarray, classes: int, *, seed: int, epochs: int = 60) -> Classifier:
    seed_all(seed)
    model = Classifier(classes).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-2)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=epochs * ((len(x) + 63) // 64))
    xt, yt = _tensor(x), torch.as_tensor(y, dtype=torch.long, device=DEVICE)
    for _ in range(epochs):
        model.train()
        for idx in torch.randperm(len(xt), device=DEVICE).split(64):
            if len(idx) < 2:
                continue
            loss = F.cross_entropy(model(augment(xt[idx])), yt[idx], label_smoothing=0.1)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
    return model.eval()


@torch.no_grad()
def predict_logits(model: nn.Module, x: np.ndarray) -> np.ndarray:
    model.eval()
    return torch.cat([model(_tensor(x[i:i + 256])).cpu() for i in range(0, len(x), 256)]).numpy()


def nt_xent(z1: torch.Tensor, z2: torch.Tensor, temperature: float = 0.2) -> torch.Tensor:
    z = F.normalize(torch.cat([z1, z2]), dim=-1)
    sim = z @ z.T / temperature
    n = z1.shape[0]
    sim.fill_diagonal_(float("-inf"))
    target = torch.cat([torch.arange(n, 2 * n), torch.arange(0, n)]).to(z.device)
    return F.cross_entropy(sim, target)


def fit_contrastive(x: np.ndarray, *, seed: int, epochs: int = 80) -> Encoder:
    """Self-supervised SimCLR pre-training: two augmentations of one lap are positives. No labels are used."""
    seed_all(seed)
    encoder = Encoder().to(DEVICE)
    projector = nn.Sequential(nn.Linear(encoder.dim, 128), nn.GELU(), nn.Linear(128, 64)).to(DEVICE)
    opt = torch.optim.AdamW([*encoder.parameters(), *projector.parameters()], lr=2e-3, weight_decay=1e-2)
    xt = _tensor(x)
    for _ in range(epochs):
        encoder.train()
        for idx in torch.randperm(len(xt), device=DEVICE).split(128):
            if len(idx) < 4:
                continue
            batch = xt[idx]
            loss = nt_xent(projector(encoder(augment(batch, 1.5))), projector(encoder(augment(batch, 1.5))))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
    return encoder.eval()


@torch.no_grad()
def embed(encoder: nn.Module, x: np.ndarray) -> np.ndarray:
    encoder.eval()
    return torch.cat([encoder(_tensor(x[i:i + 256])).cpu() for i in range(0, len(x), 256)]).numpy()
