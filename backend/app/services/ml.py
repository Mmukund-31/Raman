"""Machine-learning primitives with a documented fallback.

scikit-learn is the preferred backend. If it cannot be imported (on one development machine a Windows Application Control
policy blocks scikit-learn's compiled libsvm module), equivalent NumPy/SciPy implementations are used instead. Callers use
only the names exported here, and results record `BACKEND`.

Known differences of the fallback:
- `SVC` is a least-squares SVM (Suykens): same RBF kernel family, but squared-error loss, so not identical to libsvm's SVC.
  Its "probabilities" are a softmax of one-vs-rest decision values, NOT Platt-calibrated.
- `LogisticRegression` is multinomial L2 with L-BFGS (matches sklearn's default objective up to optimiser tolerance).
- `PCA` uses a full SVD with the same sign convention as scikit-learn.
"""
import numpy as np

try:  # pragma: no cover - depends on the machine
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import silhouette_score
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    import sklearn
    BACKEND = f"scikit-learn {sklearn.__version__}"
    FALLBACK = False
except Exception:  # ImportError, or DLL load blocked by OS policy
    from scipy.optimize import minimize
    from scipy.spatial.distance import cdist
    BACKEND = "numpy-fallback"
    FALLBACK = True

    class _Base:
        def get_params(self):
            return dict(self.__dict__)

        def fit_transform(self, X, y=None):
            return self.fit(X, y).transform(X)

    class StandardScaler(_Base):
        def __init__(self, with_std=True):
            self.with_std = with_std

        def fit(self, X, y=None):
            self.mean_ = X.mean(axis=0)
            if self.with_std:
                s = X.std(axis=0)
                self.scale_ = np.where(s > 0, s, 1.0)
            return self

        def transform(self, X):
            Z = X - self.mean_
            return Z / self.scale_ if self.with_std else Z

    class PCA(_Base):
        def __init__(self, n_components=2, svd_solver="full", random_state=0):
            self.n_components = n_components

        def fit(self, X, y=None):
            self.mean_ = X.mean(axis=0)
            U, S, Vt = np.linalg.svd(X - self.mean_, full_matrices=False)
            sign = np.sign(U[np.argmax(np.abs(U), axis=0), range(U.shape[1])])
            sign[sign == 0] = 1
            Vt = Vt * sign[:, None]
            k = self.n_components
            var = S ** 2 / (X.shape[0] - 1)
            self.components_ = Vt[:k]
            self.explained_variance_ = var[:k]
            self.explained_variance_ratio_ = var[:k] / var.sum()
            return self

        def transform(self, X):
            return (X - self.mean_) @ self.components_.T

        def inverse_transform(self, Z):
            return Z @ self.components_ + self.mean_

    class Pipeline(_Base):
        def __init__(self, steps):
            self.steps = steps

        @property
        def named_steps(self):
            return dict(self.steps)

        def fit(self, X, y=None):
            for _, s in self.steps[:-1]:
                X = s.fit(X, y).transform(X)
            last = self.steps[-1][1]
            last.fit(X, y)
            return self

        def _t(self, X, upto=None):
            for _, s in self.steps[:upto]:
                X = s.transform(X)
            return X

        def transform(self, X):
            return self._t(X)

        def predict(self, X):
            return self.steps[-1][1].predict(self._t(X, -1))

        def predict_proba(self, X):
            return self.steps[-1][1].predict_proba(self._t(X, -1))

    def _softmax(z):
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    class LogisticRegression(_Base):
        def __init__(self, C=1.0, max_iter=1000):
            self.C, self.max_iter = C, max_iter

        def fit(self, X, y):
            self.classes_ = np.unique(y)
            Y = (np.asarray(y)[:, None] == self.classes_[None, :]).astype(float)
            n, d = X.shape
            k = len(self.classes_)

            def f(w):
                W, b = w[:d * k].reshape(d, k), w[d * k:]
                P = _softmax(X @ W + b)
                loss = -np.log(np.clip((P * Y).sum(axis=1), 1e-12, None)).sum() + 0.5 / self.C * (W ** 2).sum()
                G = P - Y
                return loss, np.concatenate([(X.T @ G + W / self.C).ravel(), G.sum(axis=0)])
            r = minimize(f, np.zeros(d * k + k), jac=True, method="L-BFGS-B", options={"maxiter": self.max_iter})
            self.W_, self.b_ = r.x[:d * k].reshape(d, k), r.x[d * k:]
            return self

        def predict_proba(self, X):
            return _softmax(X @ self.W_ + self.b_)

        def predict(self, X):
            return self.classes_[self.predict_proba(X).argmax(axis=1)]

    class SVC(_Base):
        """Least-squares SVM, one-vs-rest, RBF kernel with gamma='scale'. See module docstring."""

        def __init__(self, C=1.0, kernel="rbf", probability=True, random_state=0):
            self.C = C

        def _k(self, A, B):
            return np.exp(-self.gamma_ * cdist(A, B, "sqeuclidean"))

        def fit(self, X, y):
            self.classes_ = np.unique(y)
            self.X_ = np.asarray(X, float)
            v = self.X_.var()
            self.gamma_ = 1.0 / (self.X_.shape[1] * v) if v > 0 else 1.0
            n = len(self.X_)
            K = self._k(self.X_, self.X_)
            A = np.zeros((n + 1, n + 1))
            A[0, 1:] = A[1:, 0] = 1.0
            A[1:, 1:] = K + np.eye(n) / self.C
            T = np.where(np.asarray(y)[:, None] == self.classes_[None, :], 1.0, -1.0)
            sol = np.linalg.solve(A, np.vstack([np.zeros((1, len(self.classes_))), T]))
            self.b_, self.alpha_ = sol[0], sol[1:]
            return self

        def decision_function(self, X):
            return self._k(np.asarray(X, float), self.X_) @ self.alpha_ + self.b_

        def predict_proba(self, X):
            return _softmax(self.decision_function(X) * 3.0)  # fixed temperature; uncalibrated

        def predict(self, X):
            return self.classes_[self.decision_function(X).argmax(axis=1)]

    class GroupKFold:
        def __init__(self, n_splits=3):
            self.n_splits = n_splits

        def split(self, X, y, groups):
            groups = np.asarray(groups)
            names, counts = np.unique(groups, return_counts=True)
            order = np.argsort(-counts, kind="stable")
            fold_of, load = {}, np.zeros(self.n_splits)
            for i in order:
                f = int(np.argmin(load))
                fold_of[names[i]] = f
                load[f] += counts[i]
            fid = np.array([fold_of[g] for g in groups])
            for f in range(self.n_splits):
                yield np.where(fid != f)[0], np.where(fid == f)[0]

    def silhouette_score(X, labels, max_n=1500):
        X, labels = np.asarray(X, float), np.asarray(labels)
        if len(X) > max_n:
            idx = np.random.default_rng(0).choice(len(X), max_n, replace=False)
            X, labels = X[idx], labels[idx]
        u = np.unique(labels)
        if len(u) < 2 or len(u) >= len(X):
            raise ValueError("silhouette needs 2..n-1 labels")
        D = cdist(X, X)
        s = np.zeros(len(X))
        for i in range(len(X)):
            same = labels == labels[i]
            same[i] = False
            if not same.any():
                continue
            a = D[i, same].mean()
            b = min(D[i, labels == l].mean() for l in u if l != labels[i])
            s[i] = (b - a) / max(a, b) if max(a, b) > 0 else 0.0
        return float(s.mean())
