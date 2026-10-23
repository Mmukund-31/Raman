"""Format-tolerant spectrum import: one entry point for the raw exports found in practice.

parse_any() detects the format from the content (the filename is only a hint) and hands the arrays to
validation.finalise(), so every format gets the same checks. Supported:
  RRUFF .txt (##KEY=value header, "x, y" rows)   ROD .rod/.cif (CIF loop of _raman_spectrum.*)
  JCAMP-DX .jdx/.dx (XYPOINTS, AFFN X++(Y..Y))  JSON ({x, y}, list of pairs, list of records)
  delimited text: comma, semicolon, tab, pipe or whitespace; decimal commas; comment/metadata preambles;
  headerless two-column files; several spectra as extra columns (or as rows sharing an axis row).
Binary vendor formats (.spc, .wdf, .spe, ...) are rejected with an export instruction instead of being misread.
"""
import json
import re

import numpy as np

from .validation import MAX_BYTES, MAX_DROP_FRAC, ValidationError, Spectrum, finalise

BINARY_EXT = {".spc": "Galactic/Thermo SPC", ".wdf": "Renishaw WiRE", ".spe": "Princeton Instruments SPE",
              ".sp": "PerkinElmer SP", ".ngs": "NGSLabSpec", ".l6s": "LabSpec 6", ".xlsx": "Excel workbook",
              ".xls": "Excel workbook", ".opj": "Origin project", ".mat": "MATLAB", ".h5": "HDF5", ".hdf5": "HDF5",
              ".npy": "NumPy array", ".zip": "ZIP archive"}
BINARY_MAGIC = [(b"PK\x03\x04", "ZIP container (e.g. an Excel .xlsx workbook)"), (b"\x89HDF", "HDF5"),
                (b"WDF1", "Renishaw WiRE (.wdf)"), (b"\xd0\xcf\x11\xe0", "legacy Microsoft Office file (e.g. .xls)"),
                (b"\x93NUMPY", "NumPy array")]
EXPORT_HINT = ("Export the spectrum from your instrument software as text (CSV, TXT or JCAMP-DX) with a Raman-shift "
               "(or wavelength) column and an intensity column, then upload that file.")
_NUMERIC_LIKE = re.compile(r"^[+-]?(\d|[.,]\d)")
_NAN_TOKENS = {"nan", "na", "n/a", "null", "none", "-", "", "inf", "-inf", "+inf", "infinity"}
_COMMENT = ("#", "%", "//", "!", "*")


def parse_any(raw: bytes, filename: str | None = None, excitation_nm: float | None = None) -> Spectrum:
    if len(raw) > MAX_BYTES:
        raise ValidationError("File exceeds the 5 MB limit.")
    if not raw.strip():
        raise ValidationError("File is empty.")
    _reject_binary(raw, filename)
    text, enc_warn = _decode(raw)
    head = text[:20000]
    if re.search(r"^\s*##\s*JCAMP", head, re.M | re.I):
        kind, (x, y, coord, meta, warns, extra) = "JCAMP-DX", _jcamp(text)
    elif "_raman_spectrum.raman_shift" in head or re.search(r"^_raman_spectrum\.raman_shift", text, re.M):
        kind, (x, y, coord, meta, warns, extra) = "ROD (CIF)", _rod(text)
    elif re.search(r"^##\s*(NAMES|RRUFFID|IDEAL CHEMISTRY)\s*=", head, re.M | re.I):
        kind, (x, y, coord, meta, warns, extra) = "RRUFF text", _rruff(text, filename)
    elif text.lstrip()[:1] in ("{", "["):
        kind, (x, y, coord, meta, warns, extra) = "JSON", _json(text)
    else:
        kind, (x, y, coord, meta, warns, extra) = "delimited text", _delimited(text)
    meta = {"format": kind, **meta}
    if filename:
        meta.setdefault("filename", filename[:120])
    file_exc = meta.get("excitation_nm")
    if excitation_nm and file_exc and abs(float(file_exc) - excitation_nm) > 1:
        warns.append(f"The file states an excitation of {file_exc:g} nm but {excitation_nm:g} nm was entered; the entered value is used.")
    exc = excitation_nm or file_exc
    if coord in ("wavelength", "absolute_wavenumber") and not excitation_nm and file_exc:
        warns.append(f"Excitation wavelength {file_exc:g} nm was read from the file.")
    if coord == "raman_shift" and np.nanmin(x) > 5000:
        coord = "absolute_wavenumber"
    return finalise(x, y, enc_warn + warns, coord, exc, strict=False, meta=meta, extra_y=extra)


# ---------------------------------------------------------------- detection helpers

def _reject_binary(raw, filename):
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if filename and "." in filename else ""
    for magic, name in BINARY_MAGIC:
        if raw.startswith(magic):
            raise ValidationError(f"This is a binary file ({name}), which cannot be read directly. {EXPORT_HINT}")
    utf16 = raw[:2] in (b"\xff\xfe", b"\xfe\xff")
    if not utf16 and b"\x00" in raw[:4096]:
        label = BINARY_EXT.get(ext, "binary")
        raise ValidationError(f"This looks like a {label} file, which cannot be read directly. {EXPORT_HINT}")
    if ext in BINARY_EXT and not utf16 and _printable_frac(raw[:4096]) < 0.9:
        raise ValidationError(f"{BINARY_EXT[ext]} files cannot be read directly. {EXPORT_HINT}")


def _printable_frac(b):
    if not b:
        return 1.0
    ok = sum(1 for c in b if c in (9, 10, 13) or 32 <= c < 127 or c >= 128)
    return ok / len(b)


def _decode(raw):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), []
    try:
        return raw.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), ["File was not UTF-8; it was read as Windows-1252 text."]


_FLOAT = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _clean(tok: str, decimal_comma=False) -> str:
    t = tok.strip().strip('"').strip("'")
    if decimal_comma:
        t = t.replace(".", "").replace(",", ".") if re.match(r"^[+-]?\d{1,3}(\.\d{3})+,\d+$", t) else t.replace(",", ".")
    return t


def _num(tok: str, decimal_comma=False):
    t = _clean(tok, decimal_comma)
    return np.nan if t.lower() in _NAN_TOKENS else float(t)


def _is_num(tok, decimal_comma=False):
    return bool(_FLOAT.match(_clean(tok, decimal_comma)))


def _excitation_from_text(s: str):
    """Laser/excitation wavelength mentioned in a metadata line, e.g. 'Laser Wavelength: 785 nm', '##LASER=532'.
    Numbers carrying another unit (laser power in mW, exposure in s) are not wavelengths."""
    for m in re.finditer(r"(laser|excitation|exc\.?|lambda_?ex)[^0-9\n]{0,30}?(\d{3,4}(\.\d+)?)\s*([a-zµ%]+)?", s, re.I):
        unit = (m.group(4) or "").lower()
        if unit in ("", "nm") and 200 <= float(m.group(2)) <= 1600:
            return float(m.group(2))
    return None


# ---------------------------------------------------------------- header semantics

def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", h.strip().strip('"').strip("'").lstrip("#").lower())


def _role(h: str) -> str | None:
    """'x' (Raman shift), 'wl' (wavelength nm), 'abs' (absolute wavenumber), 'y' (intensity) or None."""
    s = _norm_header(h)
    compact = re.sub(r"[^a-z0-9]", "", s)
    if re.search(r"intens|count|cts|signal|\ba\.?u\.?\b|arb|absorb|spectrum|response|\by\b", s) and "shift" not in s:
        return "y"
    if re.search(r"wavelength|lambda|\bwl\b|\(nm\)|\[nm\]|\bnm\b", s):
        return "wl"
    if re.search(r"raman|shift|wavenumber|wave number|\bwave\b|cm-1|cm\^-1|cm⁻¹|1/cm|cm-¹|rcm|\bx\b|frequency", s) or compact in ("cm1",):
        if re.search(r"absolute", s):
            return "abs"
        return "x"
    return None


# ---------------------------------------------------------------- RRUFF

def _rruff(text, filename):
    meta, data_lines = {"source": "RRUFF"}, []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("##"):
            k, _, v = s[2:].partition("=")
            k, v = k.strip().upper(), v.strip()
            if k == "END":
                break
            if k == "NAMES":
                meta["name"] = v.split(",")[0].strip()
            elif k == "RRUFFID":
                meta["source_id"] = v
            elif k == "IDEAL CHEMISTRY":
                meta["formula"] = re.sub(r"_", "", v)
            elif k in ("LOCALITY", "STATUS", "URL", "OWNER", "SOURCE", "DESCRIPTION", "FILETYPE", "ORIENTATION"):
                meta[k.lower() if k != "SOURCE" else "specimen_source"] = v[:300]
            elif "LASER" in k or "WAVELENGTH" in k:
                exc = _excitation_from_text("laser " + v)
                if exc:
                    meta["excitation_nm"] = exc
        elif s:
            data_lines.append(s)
    if "excitation_nm" not in meta and filename:
        m = re.search(r"__(\d{3,4})__", filename)
        if m and 200 <= int(m.group(1)) <= 1600:
            meta["excitation_nm"] = float(m.group(1))
    x, y, coord, _, warns, extra = _delimited("\n".join(data_lines), allow_header=False, known_layout=True)
    return x, y, coord, meta, warns, extra


# ---------------------------------------------------------------- ROD (CIF)

def _cif_value(text, tag):
    m = re.search(rf"^{re.escape(tag)}[ \t]+(.+)$", text, re.M)
    if not m:
        return None
    return m.group(1).strip().strip("'").strip('"')


def _rod(text):
    lines = text.splitlines()
    meta = {"source": "ROD"}
    for tag, key in (("_chemical_name_mineral", "name"), ("_chemical_name_systematic", "systematic_name"),
                     ("_chemical_name_common", "common_name"), ("_chemical_formula_sum", "formula"),
                     ("_rod_database.code", "source_id"), ("_raman_measurement_device.model", "instrument"),
                     ("_raman_determination_method", "determination_method")):
        v = _cif_value(text, tag)
        if v and v != "?":
            meta[key] = v
    meta.setdefault("name", meta.get("common_name") or meta.get("systematic_name"))
    title = re.search(r"^_publ_section_title\s*\n;\s*\n?(.*?)\n;", text, re.M | re.S) or re.search(r"^_publ_section_title[ \t]+(.+)$", text, re.M)
    if title:
        meta["publication"] = re.sub(r"\s+", " ", title.group(1)).strip().strip("'")[:300]
    exc = _cif_value(text, "_raman_measurement_device.excitation_laser_wavelength")
    try:
        if exc:
            meta["excitation_nm"] = float(exc)
    except ValueError:
        pass
    i = next((k for k, l in enumerate(lines) if l.strip() == "_raman_spectrum.raman_shift"), None)
    if i is None:
        raise ValidationError("ROD file has no _raman_spectrum.raman_shift loop.")
    # walk forward over the loop's tag list, then read rows until the next loop_/tag/data block
    tags, j = [], i
    while j < len(lines) and lines[j].strip().startswith("_"):
        tags.append(lines[j].strip())
        j += 1
    xi = tags.index("_raman_spectrum.raman_shift")
    yi = next((k for k, t in enumerate(tags) if t == "_raman_spectrum.intensity"), None)
    if yi is None:
        raise ValidationError("ROD file has no _raman_spectrum.intensity column.")
    xs, ys = [], []
    for l in lines[j:]:
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith(("loop_", "_", "data_")):
            break
        parts = s.split()
        if len(parts) < len(tags):
            continue
        xs.append(_num(parts[xi]))
        ys.append(_num(parts[yi]))
    return np.array(xs), np.array(ys), "raman_shift", meta, [], []


# ---------------------------------------------------------------- JCAMP-DX

def _jcamp(text):
    ldr, data_kind, data_lines, warns = {}, None, [], []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("$$"):
            continue
        if s.startswith("##"):
            k, _, v = s[2:].partition("=")
            k = re.sub(r"[\s_\-/]", "", k).upper()
            v = v.split("$$")[0].strip()
            if k == "END":
                if data_lines:
                    break
                continue
            if k in ("XYDATA", "XYPOINTS", "PEAKTABLE"):
                data_kind = (k, v.replace(" ", "").upper())
                continue
            if data_kind and data_lines:  # a new LDR ends the data block
                break
            ldr[k] = v
        elif data_kind and s:
            data_lines.append(s.split("$$")[0].strip())
    if not data_kind:
        raise ValidationError("JCAMP-DX file has no ##XYDATA or ##XYPOINTS block.")
    if data_kind[0] == "PEAKTABLE":
        raise ValidationError("This JCAMP-DX file contains only a peak table, not a full spectrum.")
    f = lambda k, d=None: float(ldr[k]) if k in ldr and ldr[k] not in ("", "?") else d
    xfac, yfac = f("XFACTOR", 1.0), f("YFACTOR", 1.0)
    blob = " ".join(data_lines)
    if re.search(r"[@A-IJ-Ra-ij-rS-Zs%]", re.sub(r"[eE][+-]?\d", "", blob).replace("?", "")):
        raise ValidationError("This JCAMP-DX file uses compressed (ASDF) data, which is not supported. "
                              "Re-export it with uncompressed AFFN data, or as CSV/TXT.")
    if data_kind[0] == "XYPOINTS" or data_kind[1].startswith("(XY"):
        nums = [float(t) for t in re.split(r"[\s,;]+", blob) if t and t != "?"]
        x, y = np.array(nums[0::2]) * xfac, np.array(nums[1::2]) * yfac
        n = min(x.size, y.size)
        x, y = x[:n], y[:n]
    else:  # (X++(Y..Y)): each line = x then a run of y values at constant spacing
        firstx, lastx, npts = f("FIRSTX"), f("LASTX"), f("NPOINTS")
        ys, line_x = [], []
        for l in data_lines:
            toks = [t for t in re.split(r"[\s,;]+", l) if t]
            if len(toks) < 2:
                continue
            line_x.append(float(toks[0]) * xfac)
            ys.append([np.nan if t == "?" else float(t) for t in toks[1:]])
        flat = np.array([v for row in ys for v in row]) * yfac
        if firstx is not None and lastx is not None and flat.size > 1:
            n_decl = int(npts) if npts else flat.size
            if npts and n_decl != flat.size:
                warns.append(f"JCAMP-DX declares {n_decl} points but {flat.size} were read.")
            x = np.linspace(firstx, lastx, flat.size)
        else:
            dx = (line_x[1] - line_x[0]) / len(ys[0]) if len(line_x) > 1 else 1.0
            x = np.concatenate([lx + dx * np.arange(len(r)) for lx, r in zip(line_x, ys)])
        y = flat
    xunits = ldr.get("XUNITS", "").upper()
    dtype = ldr.get("DATATYPE", "").upper()
    coord = "wavelength" if ("NANOMETER" in xunits or xunits == "NM") else "raman_shift"
    if dtype and "RAMAN" not in dtype:
        warns.append(f"The file declares data type '{ldr['DATATYPE']}'; it is analysed as a Raman spectrum.")
    meta = {"name": ldr.get("TITLE") or None}
    exc = _excitation_from_text(" ".join(f"{k} {v}" for k, v in ldr.items() if re.search(r"LASER|EXCITATION|WAVELENGTH", k)))
    if exc:
        meta["excitation_nm"] = exc
    if ldr.get("ORIGIN"):
        meta["origin"] = ldr["ORIGIN"][:200]
    return x, y, coord, {k: v for k, v in meta.items() if v}, warns, []


# ---------------------------------------------------------------- JSON

_JX = ("raman_shift_cm1", "raman_shift", "ramanshift", "shift", "wavenumber", "wavenumbers", "x", "cm1")
_JW = ("wavelength_nm", "wavelength", "wl")
_JY = ("intensity", "intensities", "counts", "y", "signal", "spectrum")


def _json(text):
    try:
        d = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"File looks like JSON but could not be parsed: {e.msg} (line {e.lineno}).")
    meta = {}
    if isinstance(d, dict):
        low = {k.lower(): v for k, v in d.items()}
        for k in ("excitation_nm", "laser_wavelength", "laser_wavelength_nm", "excitation_wavelength"):
            if isinstance(low.get(k), (int, float)):
                meta["excitation_nm"] = float(low[k])
        for k in ("name", "sample", "sample_id", "title"):
            if isinstance(low.get(k), str):
                meta["name"] = low[k][:120]
                break
        if isinstance(low.get("data"), (list, dict)) and not any(k in low for k in _JX + _JW):
            x, y, coord, m2, w, e = _json(json.dumps(low["data"]))
            return x, y, coord, {**m2, **meta}, w, e
        xk = next((k for k in _JX if k in low), None)
        wk = next((k for k in _JW if k in low), None)
        yk = next((k for k in _JY if k in low), None)
        if yk is None or (xk is None and wk is None):
            raise ValidationError("JSON must contain an x array (e.g. 'raman_shift') and an intensity array "
                                  f"(e.g. 'intensity'); found keys: {', '.join(list(d)[:10])}.")
        xv, yv = low[xk or wk], low[yk]
        extra = []
        if yv and isinstance(yv[0], list):  # several spectra on one axis
            extra = [{"name": f"spectrum {i + 2}", "y": np.array(v, float)} for i, v in enumerate(yv[1:])]
            yv = yv[0]
        try:
            x, y = np.array(xv, float), np.array(yv, float)
        except (TypeError, ValueError):
            raise ValidationError("JSON arrays must contain only numbers.")
        if x.size != y.size:
            raise ValidationError(f"JSON x and intensity arrays differ in length ({x.size} vs {y.size}).")
        return x, y, "wavelength" if xk is None else "raman_shift", meta, [], extra
    if isinstance(d, list) and d:
        if all(isinstance(r, (list, tuple)) and len(r) >= 2 for r in d):
            a = np.array([[r[0], r[1]] for r in d], float)
            return a[:, 0], a[:, 1], "raman_shift", meta, [], []
        if all(isinstance(r, dict) for r in d):
            keys = {k.lower(): k for k in d[0]}
            xk = next((keys[k] for k in _JX if k in keys), None)
            wk = next((keys[k] for k in _JW if k in keys), None)
            yk = next((keys[k] for k in _JY if k in keys), None)
            if yk and (xk or wk):
                return (np.array([r.get(xk or wk, np.nan) for r in d], float), np.array([r.get(yk, np.nan) for r in d], float),
                        "wavelength" if xk is None else "raman_shift", meta, [], [])
    raise ValidationError("Unrecognised JSON layout. Use {\"raman_shift\": [...], \"intensity\": [...]}.")


# ---------------------------------------------------------------- delimited text

_DELIMS = [("\t", "tab"), (";", "semicolon"), (",", "comma"), ("|", "pipe"), (None, "whitespace")]


def _split(line, d):
    return [t for t in re.split(r"\s+", line.strip()) if t] if d is None else [t.strip() for t in line.strip().strip(d).split(d)]


def _numeric_row(toks, dc):
    return len(toks) >= 2 and all(_is_num(t, dc) or t.strip().lower() in _NAN_TOKENS for t in toks) and _is_num(toks[0], dc)


def _choose_delim(lines):
    """Pick the delimiter (and decimal-comma flag) under which the most candidate rows split into the same number (>=2)
    of numeric fields. Comma as decimal separator is only considered with a non-comma delimiter."""
    cand = [l for l in lines if _NUMERIC_LIKE.match(l.strip())][:400]
    if not cand:
        return None
    best = None
    for d, name in _DELIMS:
        for dc in ((False, True) if d != "," else (False,)):
            widths = [len(_split(l, d)) for l in cand if _numeric_row(_split(l, d), dc)]
            if not widths:
                continue
            w = max(set(widths), key=widths.count)
            score = widths.count(w)
            key = (score, -abs(w - 2) * 0.01, not dc)  # prefer more rows, then 2 columns, then '.' decimals
            if best is None or key > best[0]:
                best = (key, d, name, dc, w)
    return None if best is None else best[1:]


def _delimited(text, allow_header=True, known_layout=False):
    lines = text.splitlines()
    chosen = _choose_delim(lines)
    if chosen is None:
        n = sum(1 for l in lines if l.strip())
        if n and all(len(_split(l, None)) == 1 for l in lines if l.strip()):
            raise ValidationError("Only one column found. The file needs an x column (Raman shift or wavelength) and an "
                                  "intensity column.")
        raise ValidationError("No numeric data rows were found. Expected rows such as '1001.5, 2345' after an optional header.")
    d, dname, dc, width = chosen
    warns, meta = [], {}
    rows, first, last, bad = [], None, None, 0
    for i, l in enumerate(lines):
        s = l.strip()
        toks = _split(s, d) if s else []
        if s and len(toks) == width and _numeric_row(toks, dc):
            rows.append(toks)
            first = i if first is None else first
            last = i
        elif first is not None and s and not s.startswith(_COMMENT):
            bad += 1
    # rows after the last numeric row are a footer; rows inside the data block that failed are defects
    inner_bad = sum(1 for l in lines[first:last + 1] if l.strip() and not l.strip().startswith(_COMMENT)
                    and not (len(_split(l, d)) == width and _numeric_row(_split(l, d), dc)))
    footer = bad - inner_bad
    if inner_bad:
        if inner_bad > MAX_DROP_FRAC * (len(rows) + inner_bad):
            raise ValidationError(f"{inner_bad} row(s) contain missing or non-numeric values.")
        warns.append(f"{inner_bad} malformed row(s) inside the data were skipped.")
    if footer:
        warns.append(f"{footer} non-numeric line(s) after the data were ignored.")
    preamble = [l.strip() for l in lines[:first] if l.strip()]
    for p in preamble:
        exc = _excitation_from_text(p)
        if exc and "excitation_nm" not in meta:
            meta["excitation_nm"] = exc
    header = None
    if allow_header and preamble:
        cand = preamble[-1].lstrip("#%!/* ").strip()
        toks = _split(cand, d)
        if len(toks) >= 2 and not all(_is_num(t, dc) for t in toks) and len(toks) in (width, width + 1):
            header = toks[-width:] if len(toks) == width + 1 else toks
    if dc:
        warns.append(f"Read as {dname}-separated values with decimal commas.")
    a = np.array([[_num(t, dc) for t in r] for r in rows], float)
    # rows-as-spectra layout: a first numeric row holding the axis, then one spectrum per row
    if width >= 50 and a.shape[0] < width and a.shape[0] >= 2 and _monotonic(a[0]):
        x = a[0]
        ys = a[1:]
        extra = [{"name": f"row {i + 2}", "y": r} for i, r in enumerate(ys[1:])]
        warns.append(f"Read as one spectrum per row ({ys.shape[0]} spectra sharing the axis in the first row).")
        return x, ys[0], "raman_shift", meta, warns, extra
    roles = [_role(h) for h in header] if header else [None] * width
    xi = next((i for i, r in enumerate(roles) if r in ("x", "wl", "abs")), None)
    coord = {"x": "raman_shift", "wl": "wavelength", "abs": "absolute_wavenumber"}.get(roles[xi] if xi is not None else None)
    if xi is None:
        xi, coord = 0, "raman_shift"
        if header:
            warns.append(f"Column names ({', '.join(header[:4])}) were not recognised; the first column was used as Raman "
                         "shift (cm⁻¹) and the next as intensity.")
        elif not known_layout:
            warns.append("No header row: the first column was read as Raman shift (cm⁻¹) and the second as intensity.")
            if 180 < np.nanmin(a[:, 0]) and np.nanmax(a[:, 0]) < 1100 and np.ptp(a[:, 0]) < 300:
                warns.append("The first column could also be a wavelength in nm; if so, add a 'wavelength_nm' header.")
    ycols = [i for i in range(width) if i != xi]
    if not ycols:
        raise ValidationError("Only one column found. The file needs an x column and an intensity column.")
    named_y = [i for i in ycols if roles[i] == "y"]
    yi = named_y[0] if named_y else ycols[0]
    others = [i for i in ycols if i != yi]
    extra = [{"name": (header[i] if header else f"column {i + 1}")[:60], "y": a[:, i]} for i in others]
    if extra:
        warns.append(f"{len(extra) + 1} intensity columns found; column '{header[yi] if header else yi + 1}' is the main "
                     f"spectrum and the other {len(extra)} are analysed as additional spectra.")
    return a[:, xi], a[:, yi], coord, meta, warns, extra


def _monotonic(v):
    dv = np.diff(v[np.isfinite(v)])
    return dv.size > 0 and (np.all(dv > 0) or np.all(dv < 0))
