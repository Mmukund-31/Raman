"""Download RRUFF Raman archives into data/raw/rruff/ and extract them.

RRUFF (https://www.rruff.net): spectra of mineral specimens whose identity is confirmed by X-ray diffraction and/or
chemical analysis. RRUFF asks that users cite: Lafuente B, Downs R T, Yang H, Stone N (2015) The power of databases:
the RRUFF project. In: Highlights in Mineralogical Crystallography, T Armbruster and R M Danisi, eds. Berlin, Germany,
W. De Gruyter, pp 1-30. Check https://www.rruff.net/about/download-data/ for current terms before redistributing.

Usage (from backend/):
  .venv\\Scripts\\python scripts/fetch_rruff.py --select            # only the materials the curated library uses (fast)
  .venv\\Scripts\\python scripts/fetch_rruff.py --archives excellent_unoriented fair_oriented   # whole archives
--select reads the ZIP's central directory with HTTP Range requests and fetches just the matching members, so a few MB
are transferred instead of 230 MB. Whole-archive downloads resume after an interruption (the RRUFF server can be slow).
"""
import argparse
import io
import json
import pathlib
import sys
import time
import urllib.request
import zipfile
from datetime import date

BASE = "https://www.rruff.net/zipped_data_files/raman"
ARCHIVES = ["excellent_unoriented", "excellent_oriented", "fair_unoriented", "fair_oriented", "poor_unoriented",
            "unrated_unoriented", "unrated_oriented", "LR-Raman"]
OUT = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "rruff"
UA = {"User-Agent": "RamanReach-research-prototype/0.3 (reference-library curation)"}
CITATION = ("Lafuente B, Downs R T, Yang H, Stone N (2015) The power of databases: the RRUFF project. In: Highlights in "
            "Mineralogical Crystallography, T Armbruster and R M Danisi, eds. De Gruyter, pp 1-30.")


def download(url, dest: pathlib.Path, chunk=1 << 16, tries=40):
    """Resumable download using HTTP Range requests."""
    for attempt in range(tries):
        have = dest.stat().st_size if dest.exists() else 0
        req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={have}-"} if have else UA)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status == 416:  # nothing left to fetch
                    return
                total = have + int(r.headers.get("Content-Length", 0))
                mode = "ab" if r.status == 206 else "wb"
                with open(dest, mode) as f:
                    while b := r.read(chunk):
                        f.write(b)
                if dest.stat().st_size >= total:
                    return
        except urllib.error.HTTPError as e:
            if e.code == 416:
                return
            print(f"  HTTP {e.code}; retrying")
        except Exception as e:
            print(f"  interrupted at {dest.stat().st_size if dest.exists() else 0} bytes ({e}); resuming")
        time.sleep(min(30, 2 + attempt))
    raise RuntimeError(f"Could not download {url}")


class HttpRangeFile(io.RawIOBase):
    """Read-only, seekable view of a remote file via HTTP Range requests (with a read-ahead buffer), so zipfile can
    list and extract single members without downloading the archive."""

    def __init__(self, url, block=1 << 18):
        self.url, self.block, self.pos, self.buf_start, self.buf = url, block, 0, 0, b""
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=120) as r:
            self.size = int(r.headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def _fetch(self, start, end):
        for attempt in range(8):
            try:
                req = urllib.request.Request(self.url, headers={**UA, "Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    return r.read()
            except Exception as e:
                print(f"  range {start}-{end} failed ({e}); retrying")
                time.sleep(2 + 2 * attempt)
        raise RuntimeError("range request kept failing")

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.size, self.pos + n)
        if not (self.buf_start <= self.pos and end <= self.buf_start + len(self.buf)):
            self.buf_start = self.pos
            self.buf = self._fetch(self.pos, min(self.size, self.pos + max(n, self.block)) - 1)
        out = self.buf[self.pos - self.buf_start: end - self.buf_start]
        self.pos += len(out)
        return out


def fetch_selected(archive, materials, kinds=("Processed", "RAW")):
    """Extract only the spectra of the named materials (file names start with 'Mineral__R0xxxxx')."""
    target = OUT / archive
    target.mkdir(parents=True, exist_ok=True)
    rf = HttpRangeFile(f"{BASE}/{archive}.zip")
    with zipfile.ZipFile(rf) as zf:
        want = {m.lower() for m in materials}
        names = [i for i in zf.infolist() if not i.is_dir() and i.filename.lower().endswith(".txt")
                 and i.filename.split("/")[-1].split("__")[0].lower() in want
                 and any(f"Raman_Data_{k}" in i.filename for k in kinds)]
        print(f"{archive}: {len(zf.infolist())} members, {len(names)} selected")
        for k, info in enumerate(sorted(names, key=lambda i: i.header_offset)):
            p = pathlib.PurePosixPath(info.filename)
            dest = target / p.name
            if ".." in p.parts or (dest.exists() and dest.stat().st_size == info.file_size):
                continue
            dest.write_bytes(zf.read(info))
            if k % 50 == 0:
                print(f"  {k}/{len(names)}")
    return target


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archives", nargs="+", default=["excellent_unoriented"], choices=ARCHIVES)
    ap.add_argument("--select", action="store_true", help="fetch only the curated library's materials")
    ap.add_argument("--materials", nargs="*", help="material names for --select (default: the curation priority list)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.select:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from curate_library import PRIORITY
        mats = [m.capitalize() for m in (a.materials or PRIORITY)]
        for name in a.archives:
            target = fetch_selected(name, mats)
            _record(target, name, "selected members: " + ", ".join(mats))
        return
    for name in a.archives:
        z = OUT / f"{name}.zip"
        print(f"{name}: downloading to {z}")
        download(f"{BASE}/{name}.zip", z)
        target = OUT / name
        target.mkdir(exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            for m in zf.infolist():
                p = pathlib.PurePosixPath(m.filename)
                if m.is_dir() or p.is_absolute() or ".." in p.parts or p.suffix.lower() != ".txt":
                    continue  # only plain spectrum files, never paths outside the target folder
                (target / p.name).write_bytes(zf.read(m))
        _record(target, name, "whole archive")


def _record(target, name, scope):
    n = len(list(target.glob("*.txt")))
    (target / "_fetch.json").write_text(json.dumps({
        "source": "RRUFF", "archive": f"{BASE}/{name}.zip", "scope": scope, "fetched": date.today().isoformat(),
        "files": n, "license": "Free for research use with citation; see https://www.rruff.net/about/download-data/",
        "citation": CITATION}, indent=2))
    print(f"{name}: {n} spectrum files")


if __name__ == "__main__":
    main()
