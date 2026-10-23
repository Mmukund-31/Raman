"""Build the curated measured reference library (data/references_real/) from downloaded RRUFF and ROD files.

Every spectrum is read with the app's own parser (formats.parse_any) and must pass all curation checks:
  * identity confirmed by the source (RRUFF 'excellent' archives: XRD and/or chemistry; ROD: experimental entries)
  * provisional SNR >= MIN_SNR after the app's baseline correction
  * covers at least COVER_LO..COVER_HI cm-1 (the mineral fingerprint region) with >= MIN_POINTS points
  * no flat-topped (saturated) maximum
  * one spectrum per independent specimen (RRUFF id / ROD entry): 532 nm preferred, then the highest SNR
  * the material has >= 2 independent specimens, so evaluation can always hold one out

Usage (from backend/):  .venv\\Scripts\\python scripts/curate_library.py [--max-materials 60] [--per-material 3]
Run scripts/fetch_rruff.py and scripts/fetch_rod.py first. Writes CSVs + manifest.json + curation_report.json.
"""
import argparse
import collections
import json
import pathlib
import re
import sys
from datetime import date

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.services import preprocessing, quality  # noqa: E402
from app.services.formats import parse_any  # noqa: E402
from app.services.validation import ValidationError  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "references_real"
MIN_SNR, COVER_LO, COVER_HI, MIN_POINTS, GRID = 20.0, 300.0, 1100.0, 300, 2.0
# Common, well-characterised materials chosen first when available; the rest of the slots go to the best-sampled others.
PRIORITY = ["calcite", "aragonite", "dolomite", "magnesite", "siderite", "rhodochrosite", "quartz", "cristobalite",
            "gypsum", "anhydrite", "barite", "celestine", "rutile", "anatase", "brookite", "hematite", "magnetite",
            "goethite", "corundum", "spinel", "diamond", "graphite", "forsterite", "fayalite", "albite", "orthoclase",
            "microcline", "anorthite", "muscovite", "talc", "kaolinite", "apatite", "fluorapatite", "pyrite", "sulfur",
            "zircon", "almandine", "pyrope", "grossular", "diopside", "enstatite", "tremolite", "beryl", "topaz",
            "elbaite", "cassiterite", "fluorite", "malachite", "azurite", "cerussite", "smithsonite"]
# Mineral synonyms and systematic names used by the sources -> one material key
ALIASES = {"baryte": "barite", "celestite": "celestine", "triberyllium_dialuminium_catena_silicate": "beryl",
           "calcium_carbonate": "calcite", "silicon_dioxide": "quartz", "alpha_quartz": "quartz", "titanium_dioxide": "rutile"}
# Group names that cover several species already in the library (RRUFF's unspecified 'Tourmaline' overlaps 'Elbaite')
EXCLUDE = {"tourmaline"}
CITES = {
    "RRUFF": ("Lafuente B, Downs R T, Yang H, Stone N (2015) The power of databases: the RRUFF project. In: Highlights in "
              "Mineralogical Crystallography, T Armbruster and R M Danisi, eds. De Gruyter, pp 1-30.",
              "RRUFF data: free for research use with citation (https://www.rruff.net/about/download-data/)."),
    "ROD": ("El Mendili Y. et al. (2019) Raman Open Database. J. Appl. Cryst. 52, 618-625. doi:10.1107/S1600576719004229",
            "Public domain (stated in every ROD file)."),
}


def slug(name: str) -> str:
    k = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return ALIASES.get(k, k)


def records():
    """Yields (record, reject_reason) for every candidate file."""
    for f in sorted((RAW / "rruff").glob("*/*.txt")):
        if "Raman_Data_Processed" not in f.name:
            continue  # RAW files are kept for test-file generation, not as references
        yield from _one(f, "RRUFF", "rruff/" + f.parent.name)
    for f in sorted((RAW / "rod").glob("*.rod")):
        yield from _one(f, "ROD", "rod")


def _one(f, source, archive):
    try:
        s = parse_any(f.read_bytes(), f.name)
    except ValidationError as e:
        yield None, f"unreadable: {e}"
        return
    m = s.meta
    if source == "ROD" and m.get("determination_method", "experimental").lower() != "experimental":
        yield None, "not experimental"
        return
    if source == "RRUFF" and "confirmed" not in m.get("status", "confirmed").lower():
        yield None, "identity not confirmed"
        return
    name = m.get("name")
    if not name:
        yield None, "no material name"
        return
    base = preprocessing.als_baseline(s.y)
    snr = quality.estimate_snr(s.y - base)
    rec = {"file": f, "source": source, "archive": archive, "name": name, "material": slug(name), "x": s.x, "y": s.y,
           "snr": snr, "excitation_nm": m.get("excitation_nm"), "formula": m.get("formula"),
           # independence unit: an RRUFF specimen id; for ROD the publication, since one paper often deposits several
           # spectra of the same sample (temperature or pressure series)
           "specimen": (f"RRUFF:{m.get('source_id') or f.stem}" if source == "RRUFF"
                        else f"ROD-pub:{slug(m.get('publication') or m.get('source_id') or f.stem)[:80]}:{slug(name)}"),
           "source_id": m.get("source_id") or f.stem,
           "url": m.get("url") or (f"https://solsa.crystallography.net/rod/{m.get('source_id')}.html" if source == "ROD" else None),
           "instrument": m.get("instrument"), "locality": m.get("locality")}
    if s.x.size < MIN_POINTS:
        yield None, "too few points"
    elif s.x[0] > COVER_LO or s.x[-1] < COVER_HI:
        yield None, f"range does not cover {COVER_LO:g}-{COVER_HI:g} cm-1"
    elif snr is None or snr < MIN_SNR:
        yield None, f"SNR below {MIN_SNR:g}"
    elif quality.saturation(s.y):
        yield None, "saturated"
    else:
        yield rec, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-materials", type=int, default=60)
    ap.add_argument("--per-material", type=int, default=3)
    a = ap.parse_args()
    rejects, by_specimen = collections.Counter(), {}
    n_seen = 0
    for rec, why in records():
        n_seen += 1
        if why:
            rejects[why.split(":")[0]] += 1
            continue
        key = rec["specimen"]
        cur = by_specimen.get(key)
        pref = lambda r: (r["excitation_nm"] == 532, r["snr"])
        if cur is None or pref(rec) > pref(cur):
            by_specimen[key] = rec
    by_material = collections.defaultdict(list)
    for r in by_specimen.values():
        by_material[r["material"]].append(r)
    eligible = {k: sorted(v, key=lambda r: (-(r["excitation_nm"] == 532), -r["snr"])) for k, v in by_material.items()
                if len(v) >= 2 and k not in EXCLUDE}
    chosen = [k for k in PRIORITY if k in eligible]
    chosen += [k for k in sorted(eligible, key=lambda k: -len(eligible[k])) if k not in chosen]
    chosen = chosen[: a.max_materials]

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.csv"):
        old.unlink()
    manifest = []
    for mat in sorted(chosen):
        for r in eligible[mat][: a.per_material]:
            rid = slug(f"{mat}_{r['source']}_{r['source_id']}")
            lo, hi = np.ceil(max(r["x"][0], 50)), np.floor(min(r["x"][-1], 4000))
            grid = np.arange(lo, hi + 1e-9, GRID)
            yi = np.interp(grid, r["x"], r["y"])
            yi = (yi - yi.min()) / (np.ptp(yi) or 1)
            with open(OUT / f"{rid}.csv", "w", newline="") as fh:
                fh.write("raman_shift_cm1,intensity\n")
                fh.writelines(f"{gx:.1f},{gy:.5f}\n" for gx, gy in zip(grid, yi))
            cite, lic = CITES[r["source"]]
            manifest.append({
                "reference_id": rid, "name": r["name"], "material": mat, "formula": r["formula"], "category": "measured",
                "file": f"{rid}.csv", "units": "raman_shift_cm1", "excitation_nm": r["excitation_nm"],
                "source": f"{r['source']} ({r['archive']})", "source_id": r["source_id"], "source_url": r["url"],
                "source_file": r["file"].name, "instrument": r["instrument"], "locality": r["locality"],
                "license": lic, "citation": cite, "range_cm1": [float(lo), float(hi)], "snr": round(float(r["snr"]), 1),
                "curation_checks": {"identity_confirmed_by_source": True, f"snr_ge_{MIN_SNR:g}": True,
                                    f"covers_{COVER_LO:g}_{COVER_HI:g}": True, "not_saturated": True,
                                    "independent_specimens_of_material": len(eligible[mat])},
                "processing": f"source intensities resampled to a {GRID:g} cm-1 grid and min-max scaled; no other changes",
                "limitations": "One specimen and instrument per spectrum; orientation, grain size and instrument response "
                               "change relative intensities.",
            })
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    report = {"built": date.today().isoformat(), "files_seen": n_seen, "rejected": dict(rejects),
              "specimens_passing": len(by_specimen), "materials_passing": len(by_material),
              "materials_with_2plus_specimens": len(eligible), "materials_chosen": len(chosen),
              "reference_spectra": len(manifest),
              "criteria": {"min_snr": MIN_SNR, "must_cover_cm1": [COVER_LO, COVER_HI], "min_points": MIN_POINTS,
                           "min_independent_specimens": 2, "per_material": a.per_material}}
    (OUT / "curation_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
