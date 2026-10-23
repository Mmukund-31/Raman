"""Download the Raman Open Database (ROD) into data/raw/rod/.

ROD (https://solsa.crystallography.net/rod/) states: "All data on this site have been placed in the public domain by
the contributors." Cite: El Mendili Y. et al. (2019), Raman Open Database: first interconnected Raman-X-ray
diffraction open-access resource for material identification, J. Appl. Cryst. 52, 618-625.

Usage (from backend/):  .venv\\Scripts\\python scripts/fetch_rod.py [--limit N] [--workers 6]
Existing files are skipped, so the script can be re-run to resume.
"""
import argparse
import concurrent.futures as cf
import json
import pathlib
import re
import time
import urllib.request
from datetime import date

BASE = "https://solsa.crystallography.net/rod"
LIST_URL = f"{BASE}/result.php?mineral="  # an empty mineral filter lists every entry
OUT = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "rod"
UA = {"User-Agent": "RamanReach-research-prototype/0.3 (reference-library curation)"}


def get(url, timeout=60, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def list_ids():
    """The result list is paginated per search session (CODSESSION); walk it 100 entries at a time."""
    first = get(LIST_URL, 120).decode("utf-8", "replace")
    sess = re.search(r'name="CODSESSION" value="([^"]+)"', first)
    total = re.search(r"(\d+) entries", first)
    ids = set(re.findall(r"(\d{7})\.rod", first))
    if sess and total:
        n = int(total.group(1))
        for page in range((n + 99) // 100):
            html = get(f"{BASE}/result.php?CODSESSION={sess.group(1)}&count=100&page={page}&order_by=file&order=asc", 120)
            ids |= set(re.findall(r"(\d{7})\.rod", html.decode("utf-8", "replace")))
        print(f"listing reports {n} entries; collected {len(ids)} ids")
    return sorted(ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ids = list_ids()[: a.limit or None]
    print(f"{len(ids)} ROD entries listed")

    def one(i):
        p = OUT / f"{i}.rod"
        if p.exists() and p.stat().st_size > 0:
            return "skip"
        p.write_bytes(get(f"{BASE}/{i}.rod"))
        return "ok"

    done = {"ok": 0, "skip": 0, "fail": 0}
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, f in zip(ids, ex.map(lambda i: _safe(one, i), ids)):
            done[f] += 1
    (OUT / "_fetch.json").write_text(json.dumps({
        "source": "Raman Open Database (ROD)", "url": BASE, "fetched": date.today().isoformat(), "entries": len(ids),
        "license": "Public domain (stated on every ROD file)",
        "citation": "El Mendili Y. et al. (2019) J. Appl. Cryst. 52, 618-625. doi:10.1107/S1600576719004229", **done}, indent=2))
    print(done)


def _safe(fn, i):
    try:
        return fn(i)
    except Exception as e:
        print("failed", i, e)
        return "fail"


if __name__ == "__main__":
    main()
