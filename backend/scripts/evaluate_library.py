"""Run the held-out evaluation of the measured library and write evaluation.json + thresholds.json.

Usage (from backend/):  .venv\\Scripts\\python scripts/evaluate_library.py [--no-perturb] [--no-thresholds]
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.services import evaluation_real  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "data" / "references_real"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-perturb", action="store_true", help="clean queries only (faster)")
    ap.add_argument("--no-thresholds", action="store_true", help="do not write thresholds.json")
    a = ap.parse_args()
    ev = evaluation_real.run(perturb=not a.no_perturb,
                             progress=lambda k, n: print(f"  {k}/{n}", end="\r", flush=True) if k % 25 == 0 or k == n else None)
    print()
    (OUT / "evaluation.json").write_text(json.dumps(ev, indent=1), encoding="utf-8")
    if not a.no_thresholds:
        (OUT / "thresholds.json").write_text(json.dumps({**ev["thresholds"], "date": ev["date"]}, indent=1), encoding="utf-8")
    print(json.dumps({k: ev[k] for k in ("n_reference_spectra", "n_materials", "thresholds", "summary", "negative_control",
                                         "classification_ungated")}, indent=1))
    print(evaluation_real.headline(ev))


if __name__ == "__main__":
    main()
