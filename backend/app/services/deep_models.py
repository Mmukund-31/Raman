"""OPTIONAL one-dimensional deep baselines (PyTorch imported lazily; the app works without it).

ResNet-18 adaptation: the standard image network uses 2-D convolutions on (3, H, W) tensors. For Raman spectra the input is
a single-channel 1-D signal (1, L) whose sample order IS the wavenumber axis, so every Conv2d/BatchNorm2d/MaxPool2d/AvgPool2d
becomes its 1-D counterpart; the block layout [2, 2, 2, 2] with widths 64-128-256-512 and the stem (7-wide stride-2
convolution + max-pool) are kept. No spectrogram or image rendering is used, so peak positions are not discarded.
Input: preprocessed (baseline-corrected, smoothed, L2-normalised) spectra on the common grid, i.e. exactly the arrays the
classical models receive, for a like-for-like comparison.
"""
import time

import numpy as np


def torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def _build():
    import torch
    from torch import nn

    class BasicBlock1D(nn.Module):
        def __init__(self, cin, cout, stride):
            super().__init__()
            self.c1 = nn.Conv1d(cin, cout, 3, stride, 1, bias=False)
            self.b1 = nn.BatchNorm1d(cout)
            self.c2 = nn.Conv1d(cout, cout, 3, 1, 1, bias=False)
            self.b2 = nn.BatchNorm1d(cout)
            self.down = None
            if stride != 1 or cin != cout:
                self.down = nn.Sequential(nn.Conv1d(cin, cout, 1, stride, bias=False), nn.BatchNorm1d(cout))

        def forward(self, x):
            h = torch.relu(self.b1(self.c1(x)))
            h = self.b2(self.c2(h))
            return torch.relu(h + (x if self.down is None else self.down(x)))

    class ResNet18_1D(nn.Module):
        def __init__(self, n_classes, width=64):
            super().__init__()
            w = [width, width * 2, width * 4, width * 8]
            self.stem = nn.Sequential(nn.Conv1d(1, w[0], 7, 2, 3, bias=False), nn.BatchNorm1d(w[0]), nn.ReLU(),
                                      nn.MaxPool1d(3, 2, 1))
            layers, cin = [], w[0]
            for i, c in enumerate(w):
                layers += [BasicBlock1D(cin, c, 1 if i == 0 else 2), BasicBlock1D(c, c, 1)]
                cin = c
            self.layers = nn.Sequential(*layers)
            self.head = nn.Linear(cin, n_classes)

        def forward(self, x):
            return self.head(self.layers(self.stem(x)).mean(dim=-1))

    class CNN1D(nn.Module):
        def __init__(self, n_classes):
            super().__init__()
            def blk(i, o): return nn.Sequential(nn.Conv1d(i, o, 7, padding=3), nn.BatchNorm1d(o), nn.ReLU(), nn.MaxPool1d(2))
            self.f = nn.Sequential(blk(1, 16), blk(16, 32), blk(32, 64))
            self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(64, n_classes))

        def forward(self, x):
            return self.head(self.f(x).mean(dim=-1))

    return {"cnn1d": CNN1D, "resnet18_1d": ResNet18_1D}


def build_model(name: str, n_classes: int):
    return _build()[name](n_classes)


def param_count(model) -> int:
    return int(sum(p.numel() for p in model.parameters()))


class TorchClassifier:
    """sklearn-like wrapper: fit(X, y_idx, X_val, y_val) with early stopping on a specimen-disjoint validation set."""

    def __init__(self, name, n_classes, seed=0, epochs=40, patience=6, lr=1e-3, batch=32, width=None):
        self.name, self.n_classes, self.seed = name, n_classes, seed
        self.epochs, self.patience, self.lr, self.batch = epochs, patience, lr, batch
        self.history, self.train_seconds = [], None

    @staticmethod
    def _prep(X):
        """Constant rescale by sqrt(length): L2-normalised spectra have ~1/sqrt(L) per-point values, which stalls training from
        default initialisation. A fixed constant, identical for every spectrum; no information is added or removed."""
        X = np.asarray(X, float)
        return X * np.sqrt(X.shape[1])

    def fit(self, X, y, Xv, yv):
        import torch
        torch.manual_seed(self.seed)
        torch.use_deterministic_algorithms(False)
        rng = np.random.default_rng(self.seed)
        self.model = build_model(self.name, self.n_classes)
        opt = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        lossf = torch.nn.CrossEntropyLoss()
        Xt, yt = torch.tensor(self._prep(X), dtype=torch.float32)[:, None], torch.tensor(y)
        Xvt, yvt = torch.tensor(self._prep(Xv), dtype=torch.float32)[:, None], torch.tensor(yv)
        best, bad, best_state = np.inf, 0, None
        t0 = time.perf_counter()
        for ep in range(self.epochs):
            self.model.train()
            perm = rng.permutation(len(Xt))
            for i in range(0, len(perm), self.batch):
                b = perm[i:i + self.batch]
                if len(b) < 2:
                    continue
                opt.zero_grad()
                lossf(self.model(Xt[b]), yt[b]).backward()
                opt.step()
            self.model.eval()
            with torch.no_grad():
                vl = float(lossf(self.model(Xvt), yvt))
            self.history.append(vl)
            if vl < best - 1e-4:
                best, bad = vl, 0
                best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
            else:
                bad += 1
                if bad >= self.patience:
                    break
        if best_state:
            self.model.load_state_dict(best_state)
        self.train_seconds = time.perf_counter() - t0
        self.epochs_run = len(self.history)
        return self

    def predict_proba(self, X):
        import torch
        self.model.eval()
        with torch.no_grad():
            return torch.softmax(self.model(torch.tensor(self._prep(X), dtype=torch.float32)[:, None]), dim=1).numpy()

    def n_params(self):
        return param_count(self.model)
