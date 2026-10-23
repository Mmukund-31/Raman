"""Format-tolerant import (formats.parse_any) and the downloadable test files with their expected outcomes."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import pipeline
from app.services.formats import parse_any
from app.services.validation import ValidationError

client = TestClient(app)
X = np.arange(100, 1500, 2.0)
Y = 100 + 1000 * np.exp(-((X - 1086) / 6) ** 2) + np.random.default_rng(0).normal(0, 3, X.size)
rows = lambda f: "\n".join(f(a, b) for a, b in zip(X, Y))


def check(s, n=X.size):
    assert s.x.size == n and s.x[0] < s.x[-1]
    assert abs(s.x[np.argmax(s.y)] - 1086) < 2.5


LAYOUTS = [
    ("csv", "raman_shift_cm1,intensity\n" + rows(lambda a, b: f"{a},{b}")),
    ("tsv with units", "Raman Shift (cm-1)\tIntensity (a.u.)\n" + rows(lambda a, b: f"{a}\t{b}")),
    ("semicolon + decimal comma", "Raman shift;Intensität\n" + rows(lambda a, b: f"{a:.1f};{b:.3f}".replace(".", ","))),
    ("headerless whitespace", rows(lambda a, b: f"  {a:.2f}   {b:.2f}")),
    ("renishaw #Wave", "#Wave\t\t#Intensity\n" + rows(lambda a, b: f"{a}\t\t{b}")),
    ("pipe", "shift|counts\n" + rows(lambda a, b: f"{a}|{b}")),
    ("descending", "raman_shift_cm1,intensity\n" + "\n".join(f"{a},{b}" for a, b in zip(X[::-1], Y[::-1]))),
    ("json", json.dumps({"raman_shift": X.tolist(), "intensity": Y.tolist()})),
    ("json pairs", json.dumps([[a, b] for a, b in zip(X, Y)])),
    ("json records", json.dumps([{"wavenumber": a, "counts": b} for a, b in zip(X, Y)])),
    ("jcamp xypoints", "##TITLE=t\n##JCAMP-DX=4.24\n##XUNITS=1/CM\n##XYPOINTS=(XY..XY)\n" + rows(lambda a, b: f"{a}, {b}") + "\n##END="),
    ("rruff", "##NAMES=Calcite\n##RRUFFID=R040070\n##RAMAN WAVELENGTH=532\n" + rows(lambda a, b: f"{a}, {b}") + "\n##END=\n"),
]


@pytest.mark.parametrize("name,text", LAYOUTS, ids=[n for n, _ in LAYOUTS])
def test_layouts_parse_to_the_same_spectrum(name, text):
    check(parse_any(text.encode(), "f.txt"))


def test_metadata_preamble_footer_and_excitation_are_read():
    text = ("Instrument: X\nLaser Wavelength: 785 nm\nLaser power: 250 mW\n\nShift,Counts\n" + rows(lambda a, b: f"{a},{b}")
            + "\nEnd of file\n")
    s = parse_any(text.encode())
    check(s)
    assert s.meta["excitation_nm"] == 785.0
    assert any("after the data" in w for w in s.warnings)


def test_rruff_metadata_and_rod_loop():
    s = parse_any(("##NAMES=Calcite\n##RRUFFID=R040070\n##IDEAL CHEMISTRY=CaCO_3_\n##RAMAN WAVELENGTH=532\n"
                   + rows(lambda a, b: f"{a}, {b}")).encode())
    assert (s.meta["name"], s.meta["source_id"], s.meta["formula"], s.meta["excitation_nm"]) == ("Calcite", "R040070", "CaCO3", 532.0)
    rod = ("data_1\n_chemical_name_mineral 'Calcite'\n_raman_measurement_device.excitation_laser_wavelength 785\n"
           "_rod_database.code 1000001\nloop_\n_raman_spectrum.raman_shift\n_raman_spectrum.intensity\n"
           + rows(lambda a, b: f"{a} {b}") + "\n")
    s = parse_any(rod.encode(), "x.rod")
    check(s)
    assert s.meta["name"] == "Calcite" and s.meta["excitation_nm"] == 785.0 and s.meta["format"] == "ROD (CIF)"


def test_jcamp_affn_compressed_and_wavelength_axis():
    n = X.size
    affn = (f"##TITLE=t\n##JCAMP-DX=5.01\n##XUNITS=1/CM\n##FIRSTX=100\n##LASTX={X[-1]:g}\n##NPOINTS={n}\n##YFACTOR=0.01\n"
            "##XYDATA=(X++(Y..Y))\n" + "\n".join(f"{X[i]:g} " + " ".join(str(int(v * 100)) for v in Y[i:i + 10]) for i in range(0, n, 10))
            + "\n##END=")
    check(parse_any(affn.encode()))
    with pytest.raises(ValidationError, match="compressed"):
        parse_any(b"##TITLE=t\n##JCAMP-DX=5.01\n##XYDATA=(X++(Y..Y))\n100@A1B2C3\n##END=")
    wl = "##TITLE=t\n##JCAMP-DX=4.24\n##XUNITS=NANOMETERS\n##XYPOINTS=(XY..XY)\n" + "\n".join(
        f"{1e7 / (1e7 / 532 - a)}, {b}" for a, b in zip(X, Y)) + "\n##END="
    check(parse_any(wl.encode(), None, 532))


def test_multi_spectrum_files_become_additional_spectra():
    s = parse_any(("shift,a,b,c\n" + rows(lambda a, b: f"{a},{b},{b * 2},{b * 3}")).encode())
    check(s)
    assert [e["name"] for e in s.extra_y] == ["b", "c"]
    m = ",".join(map(str, X)) + "\n" + ",".join(map(str, Y)) + "\n" + ",".join(map(str, Y * 2))
    s = parse_any(m.encode())
    check(s)
    assert len(s.extra_y) == 1


def test_repairs_small_defects_and_rejects_large_ones():
    gaps = "raman_shift_cm1,intensity\n" + "\n".join(f"{a},{'' if i in (3, 9) else b}" for i, (a, b) in enumerate(zip(X, Y)))
    s = parse_any(gaps.encode())
    assert s.x.size == X.size - 2 and any("skipped" in w for w in s.warnings)
    many = "raman_shift_cm1,intensity\n" + "\n".join(f"{a},{'' if i % 5 == 0 else b}" for i, (a, b) in enumerate(zip(X, Y)))
    with pytest.raises(ValidationError, match="non-numeric"):
        parse_any(many.encode())
    dup = "raman_shift_cm1,intensity\n" + rows(lambda a, b: f"{a},{b}") + "\n" + rows(lambda a, b: f"{a},{b}")
    s = parse_any(dup.encode())
    assert s.x.size == X.size and any("averaged" in w for w in s.warnings)


def test_axis_conversions():
    abs_wn = "wavenumber,intensity\n" + rows(lambda a, b: f"{1e7 / 532 - a},{b}")
    with pytest.raises(ValidationError, match="absolute wavenumbers"):
        parse_any(abs_wn.encode())
    check(parse_any(abs_wn.encode(), None, 532))
    s = parse_any(("# excitation 532 nm\nwavelength_nm,intensity\n" + "\n".join(f"{1e7 / (1e7 / 532 - a)},{b}" for a, b in zip(X, Y))).encode())
    check(s)
    assert s.converted and any("read from the file" in w for w in s.warnings)


def test_encodings_and_binary_files():
    check(parse_any(("Raman shift\tIntensity\r\n" + rows(lambda a, b: f"{a}\t{b}").replace("\n", "\r\n")).encode("utf-16")))
    check(parse_any(("Shift (cm-1),Intensität\n" + rows(lambda a, b: f"{a},{b}")).encode("cp1252")))
    for raw, name, msg in [(b"PK\x03\x04" + bytes(50), "w.xlsx", "Excel"), (b"WDF1" + bytes(50), "m.wdf", "Renishaw"),
                           (b"\x4b\x4d\x00\x00" + bytes(300), "v.spc", "SPC"), (b"", "e.csv", "empty"),
                           (b"just words\nno data\n", "n.txt", "numeric")]:
        with pytest.raises(ValidationError, match=msg):
            parse_any(raw, name)


def test_validate_endpoint_reports_file_metadata():
    body = ("##NAMES=Calcite\n##RRUFFID=R1\n" + rows(lambda a, b: f"{a}, {b}")).encode()
    r = client.post("/api/validate", files={"file": ("c.txt", body)}).json()
    assert r["valid"] and r["file_metadata"]["format"] == "RRUFF text"


# ---------------------------------------------------------------- downloadable test files

TEST_DIR = pipeline.DATA_DIR / "test_files"
MANIFEST = json.loads((TEST_DIR / "manifest.json").read_text(encoding="utf-8")) if (TEST_DIR / "manifest.json").exists() else []


@pytest.mark.skipif(not MANIFEST, reason="data/test_files not generated")
@pytest.mark.parametrize("t", MANIFEST, ids=[t["id"] for t in MANIFEST])
def test_test_file_gives_its_expected_outcome(t):
    data = {"stream": "false", "sample_id": t["id"]}
    if t.get("excitation_nm"):
        data["excitation_nm"] = str(t["excitation_nm"])
    r = client.post("/api/full-report", files={"file": (t["file"], (TEST_DIR / t["file"]).read_bytes())}, data=data)
    e = t["expected"]
    if e["expect"] == "error":
        assert r.status_code == 422, r.text[:200]
        assert e["message_contains"].lower() in r.json()["detail"].lower()
        return
    assert r.status_code == 200, r.text[:300]
    a = r.json()["analysis"]
    top = a["matches"][0]["material"]
    outcome = top if a["status"] == "ok" else "inconclusive"
    if e["expect"] == "match":
        assert outcome == e["material"], (outcome, a["quality_warnings"][:2], [(m["material"], round(m["score"], 3)) for m in a["matches"][:3]])
    elif e["expect"] == "inconclusive":
        assert outcome == "inconclusive", (top, a["matches"][0]["score"])
    else:
        assert outcome in e["allowed"], outcome
    if e.get("warning_contains"):
        assert any(e["warning_contains"] in w for w in a["quality_warnings"])


@pytest.mark.skipif(not MANIFEST, reason="data/test_files not generated")
def test_test_files_download_individually_and_as_zip():
    import io
    import zipfile
    assert client.get("/api/test-files").json() == MANIFEST
    one = MANIFEST[0]
    assert client.get(f"/api/test-files/{one['id']}").content == (TEST_DIR / one["file"]).read_bytes()
    assert client.get("/api/test-files/..%2Fmanifest").status_code == 404
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/test-files/all.zip").content))
    assert set(z.namelist()) == {t["file"] for t in MANIFEST} | {"manifest.json", "README.txt"}
    assert client.get("/api/examples/demo_paracetamol_synthetic/download").status_code == 200
