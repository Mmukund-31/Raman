"""Export public Raman datasets via the BHT Berlin `raman-data` package (the data behind RamanBench) as app-ready files.

raman-data (https://foundationmodels.bht-berlin.de/data/raman-data/) lists, downloads and loads ~90 public Raman
datasets from Kaggle, Hugging Face, Zenodo and others. Each dataset keeps ITS OWN license, recorded in info.json;
check it before sharing anything exported here. Nothing from these datasets is committed to the repository.

Usage (from backend/, after `pip install raman-data`):
  .venv\\Scripts\\python scripts/fetch_bht.py --list
  .venv\\Scripts\\python scripts/fetch_bht.py --dataset bioprocess_substrates [--per-class 5]
Writes data/raw/bht/<dataset>/<class>.csv (one column per spectrum: upload one file to analyse those spectra together,
which enables the PCA section) plus info.json. These spectra are biological/chemical, so the mineral reference library
will usually (correctly) answer 'inconclusive'; they are useful for testing import, processing and PCA on real data.
"""
import argparse
import json
import pathlib
import re

import numpy as np

OUT = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "bht"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dataset")
    ap.add_argument("--per-class", type=int, default=5)
    a = ap.parse_args()
    try:
        from raman_data import TASK_TYPE, raman_data
    except ImportError:
        raise SystemExit("Install the optional package first:  pip install raman-data")
    if a.list or not a.dataset:
        for name in raman_data(task_type=TASK_TYPE.Classification, load_data=False):
            print(name)
        return
    ds = raman_data(a.dataset)
    x = np.asarray(ds.raman_shifts, float)
    X = np.asarray(ds.spectra, float)
    y = np.asarray(ds.targets)
    y = y[:, 0] if y.ndim > 1 else y
    names = ds.class_names or [str(c) for c in sorted(set(y.tolist()))]
    target = OUT / re.sub(r"[^A-Za-z0-9_.-]+", "_", a.dataset)
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for k, cls in enumerate(sorted(set(y.tolist()))):
        idx = np.flatnonzero(y == cls)[: a.per_class]
        label = names[int(cls)] if isinstance(cls, (int, np.integer)) and int(cls) < len(names) else str(cls)
        fn = target / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', label)[:60] or f'class_{k}'}.csv"
        with open(fn, "w", newline="") as f:
            f.write("raman_shift_cm1," + ",".join(f"{label}_{i + 1}" for i in range(idx.size)) + "\n")
            for j, xv in enumerate(x):
                f.write(f"{xv:.3f}," + ",".join(f"{X[i, j]:.6g}" for i in idx) + "\n")
        written.append(fn.name)
    info = ds.info
    (target / "info.json").write_text(json.dumps({
        "dataset": a.dataset, "source": "raman-data (BHT Berlin)", "license": getattr(info, "license", "unknown"),
        "metadata": getattr(info, "metadata", {}), "n_spectra": int(X.shape[0]), "n_points": int(x.size),
        "range_cm1": [float(x.min()), float(x.max())], "files": written,
        "note": "Each file holds up to --per-class spectra of one class as columns."}, indent=1, default=str), encoding="utf-8")
    print(f"{len(written)} files written to {target}")


if __name__ == "__main__":
    main()
