"""Download the measured urine Raman dataset of Senger, Robertson, Kavuru & Choudhury (Zenodo 10.5281/zenodo.7343559,
CC BY 1.0) and convert it into the compact form the Diabetes Urine Study uses (data/urine/zenodo/).

Source: raw spectra of de-identified patient urine, Agiltron PeakSeeker PRO-785 (785 nm, 30 mW, 30 s, 8 cm-1
resolution), 10 replicate scans per sample. Paper: Kavuru V. et al. (2023) "Analysis of urine Raman spectra differences
from patients with diabetes mellitus and renal pathologies", PeerJ 11:e14879, doi:10.7717/peerj.14879.

Conversion: per sample, the MEDIAN of the replicate scans (robust to cosmic rays), cropped to 400-1800 cm-1 and linearly
resampled onto a 2 cm-1 grid. Intensities are otherwise unchanged (no baseline removal, no scaling).

Usage:  py scripts/fetch_urine_zenodo.py            (downloads ~145 MB into data/raw/urine_zenodo/)
        py scripts/fetch_urine_zenodo.py --tsv PATH --meta PATH   (use files downloaded already)
"""
import argparse
import csv
import json
import pathlib
import urllib.request

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "urine_zenodo"
OUT = ROOT / "data" / "urine" / "zenodo"
BASE = "https://zenodo.org/records/7343559/files/"
FILES = {"meta": "Glomerular Pathologies - De-identified Metadata.tsv", "tsv": "Glomerular Pathologies - Raw Spectral Data.tsv"}
GRID = np.arange(400, 1801, 2.0)

# Study class -> analysis group. The DM+/DM- patients all have chronic kidney disease (CKD), so "diabetic" vs
# "non-diabetic CKD" compares diabetes status within CKD; healthy volunteers are a separate reference group.
GROUPS = {
    "Diabetes Mellitus (no biopsy) (DM+)": "diabetic", "Diabetic Nephropathy (DN)": "diabetic",
    "Non-Diabetic (no biopsy) (DM-)": "non_diabetic_ckd", "Immune-Mediated Nephropathy (IMN)": "non_diabetic_ckd",
    "Membranous Nephropathy (MN)": "non_diabetic_ckd", "Renal Neoplasm": "non_diabetic_ckd", "Other": "non_diabetic_ckd",
    "Healthy Volunteers": "healthy",
}  # "Surine" (a synthetic urinalysis control product) is excluded


def fetch(name: str, dest: pathlib.Path):
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = BASE + urllib.request.quote(name) + "?download=1"
    print(f"downloading {url}")
    urllib.request.urlretrieve(url, dest)
    return dest


def read_spectra(path: pathlib.Path):
    """Yields (sample_id, x, replicate_matrix). The file has, per sample, an axis row '<id> Wavenumbers ...' followed by
    replicate rows '<id>_0001 Raw Data ...'."""
    sid, x, reps = None, None, []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = [p for p in line.rstrip("\r\n").split("\t") if p.strip()]
            if len(parts) < 3:
                continue
            if parts[1].strip().lower().startswith("wavenumber"):
                if sid and reps:
                    yield sid, x, np.array(reps)
                sid, x, reps = parts[0].strip(), np.array(parts[2:], float), []
            elif sid:
                reps.append(np.array(parts[2:], float))
    if sid and reps:
        yield sid, x, np.array(reps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv")
    ap.add_argument("--meta")
    a = ap.parse_args()
    meta_path = pathlib.Path(a.meta) if a.meta else fetch(FILES["meta"], RAW / "metadata.tsv")
    tsv_path = pathlib.Path(a.tsv) if a.tsv else fetch(FILES["tsv"], RAW / "spectra.tsv")

    with open(meta_path, encoding="utf-8") as f:
        classes = {r["Barcode"].strip(): r["Class"].strip() for r in csv.DictReader(f, delimiter="\t")}
    OUT.mkdir(parents=True, exist_ok=True)
    rows, skipped = [], {}
    for sid, x, reps in read_spectra(tsv_path):
        cls = classes.get(sid)
        group = GROUPS.get(cls or "")
        if not group:
            skipped[cls or "no metadata"] = skipped.get(cls or "no metadata", 0) + 1
            continue
        y = np.median(reps, axis=0)
        order = np.argsort(x)
        rows.append({"sample_id": sid, "class": cls, "group": group, "n_replicates": len(reps),
                     "y": np.interp(GRID, x[order], y[order])})
    header = "sample_id," + ",".join(f"{v:.0f}" for v in GRID)
    (OUT / "spectra.csv").write_text("\n".join([header] + [r["sample_id"] + "," + ",".join(f"{v:.1f}" for v in r["y"])
                                                           for r in rows]) + "\n")
    keys = ["sample_id", "class", "group", "n_replicates"]
    with open(OUT / "samples.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(keys)
        w.writerows([[r[k] for k in keys] for r in rows])
    counts = {}
    for r in rows:
        counts[r["group"]] = counts.get(r["group"], 0) + 1
    (OUT / "manifest.json").write_text(json.dumps({
        "dataset_id": "zenodo", "name": "Urine Raman spectra, diabetes mellitus and renal pathologies", "category": "measured",
        "doi": "10.5281/zenodo.7343559", "url": "https://zenodo.org/records/7343559", "license": "CC BY 1.0",
        "citation": "Senger R.S., Robertson J.L., Kavuru V., Choudhury D. (2022) Raman spectra of urine from patients with "
                    "diabetes mellitus and other pathologies. Zenodo. doi:10.5281/zenodo.7343559. Analysis: Kavuru V. et al. "
                    "(2023) PeerJ 11:e14879, doi:10.7717/peerj.14879.",
        "instrument": "Agiltron PeakSeeker PRO-785, bulk liquid, 30 mW, 30 s, 8 cm-1 resolution", "excitation_nm": 785,
        "range_cm1": [float(GRID[0]), float(GRID[-1])], "step_cm1": 2.0, "n_spectra": len(rows), "groups": counts,
        "excluded": skipped,
        "processing": "Median of replicate scans, cropped to 400-1800 cm-1, linearly resampled to 2 cm-1; no other change.",
        "caveat": "All DM+ and DM- patients have chronic kidney disease; group differences may reflect kidney disease, "
                  "medication, diet or collection conditions as well as diabetes.",
    }, indent=2))
    print(f"wrote {len(rows)} spectra {counts}; skipped {skipped}")


if __name__ == "__main__":
    main()
