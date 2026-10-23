import io
import json
import pathlib
import zipfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .research_routes import router as research_router
from .services import evaluation_real, orchestrator, pipeline, report_html, reporting
from .services.formats import parse_any
from .services.validation import MAX_BYTES, ValidationError
from .urine_routes import router as urine_router

app = FastAPI(title="RamanReach API", version=pipeline.VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(research_router)
app.include_router(urine_router)


class Options(BaseModel):
    baseline: bool = True
    als_lambda: float = Field(1e5, gt=0)
    als_p: float = Field(0.01, gt=0, lt=1)
    smooth: bool = True
    window: int = Field(11, ge=3, le=101)
    poly: int = Field(3, ge=1, le=7)
    normalize: str = Field("vector", pattern="^(none|vector|max)$")
    prominence: float = Field(0.05, gt=0, lt=1)
    despike: bool = True
    library: str = Field("auto", pattern="^(auto|synthetic_demo|measured|all)$")


async def _read(file: UploadFile) -> bytes:
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "File exceeds the 5 MB limit.")
    return raw


def _run(raw, sample_id, source, excitation_nm, options: Options, provenance=None, filename=None):
    try:
        spec = parse_any(raw, filename, excitation_nm)
        excitation_nm = excitation_nm or spec.meta.get("excitation_nm")
        return pipeline.analyze(spec, sample_id, source, excitation_nm, options.model_dump(), provenance)
    except ValidationError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


def _opts(baseline, smooth, window, poly, normalize, prominence, als_lambda, als_p, despike=True, library="auto"):
    try:
        return Options(baseline=baseline, smooth=smooth, window=window, poly=poly, normalize=normalize,
                       prominence=prominence, als_lambda=als_lambda, als_p=als_p, despike=despike,
                       library=library)
    except Exception as e:
        raise HTTPException(422, f"Invalid options: {e}")


@app.get("/health")
def health():
    return {"status": "ok", "version": pipeline.VERSION}


@app.get("/api/examples")
def examples():
    return pipeline.load_manifest("examples")


@app.get("/api/references")
def references(library: str = "synthetic_demo"):
    if library not in pipeline.LIBRARIES:
        raise HTTPException(422, f"Unknown library. Choose one of: {', '.join(pipeline.LIBRARIES)}.")
    out = []
    for folder in pipeline.LIBRARIES[library]:
        if (pipeline.DATA_DIR / folder / "manifest.json").exists():
            out += pipeline.load_manifest(folder)
    return out


@app.get("/api/evaluation")
def evaluation():
    """Held-out evaluation of the measured reference library (without the per-query rows)."""
    ev = evaluation_real.load()
    if not ev:
        raise HTTPException(404, "No evaluation has been run yet (scripts/evaluate_library.py).")
    return ev


# ---------------------------------------------------------------- downloadable test and example files

TEST_DIR = pipeline.DATA_DIR / "test_files"


def _manifest_file(folder: pathlib.Path, key: str, value: str) -> pathlib.Path:
    """Resolves a file named in a manifest; ids come from the manifest, never from the request path, so no traversal."""
    if not (folder / "manifest.json").exists():
        raise HTTPException(404, "No files available.")
    m = next((e for e in json.loads((folder / "manifest.json").read_text(encoding="utf-8")) if e[key] == value), None)
    if not m:
        raise HTTPException(404, "Unknown file.")
    path = (folder / m["file"]).resolve()
    if path.parent != folder.resolve() or not path.is_file():
        raise HTTPException(404, "Unknown file.")
    return path


@app.get("/api/test-files")
def test_files():
    if not (TEST_DIR / "manifest.json").exists():
        return []
    return json.loads((TEST_DIR / "manifest.json").read_text(encoding="utf-8"))


@app.get("/api/test-files/all.zip")
def test_files_zip():
    files = test_files()
    if not files:
        raise HTTPException(404, "No test files available.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(TEST_DIR / "manifest.json", "manifest.json")
        for f in files:
            z.write(_manifest_file(TEST_DIR, "id", f["id"]), f["file"])
        z.writestr("README.txt", TEST_README)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="ramanreach-test-files.zip"'})


@app.get("/api/test-files/{file_id}")
def test_file(file_id: str):
    path = _manifest_file(TEST_DIR, "id", file_id)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/api/examples/{sample_id}/download")
def example_download(sample_id: str):
    path = _manifest_file(pipeline.DATA_DIR / "examples", "sample_id", sample_id)
    return FileResponse(path, filename=path.name, media_type="text/csv")


TEST_README = """RamanReach test files
=====================
Each file exercises one input format or measurement problem. manifest.json lists, for every file, what it tests and the
outcome the app is expected to give (a material, 'inconclusive', or a specific error message).

Real-data files are derived from RRUFF (cite: Lafuente et al. 2015, The power of databases: the RRUFF project) and the
Raman Open Database (public domain; cite El Mendili et al. 2019, J. Appl. Cryst. 52, 618-625). They come from specimens
that are NOT in the app's reference library, so a correct match is a genuine held-out result. Files marked synthetic are
simulated and are not measurements.
"""


@app.post("/api/validate")
async def validate(file: UploadFile = File(...), excitation_nm: float | None = Form(None)):
    try:
        s = parse_any(await _read(file), file.filename, excitation_nm)
    except ValidationError as e:
        raise HTTPException(422, str(e))
    return {"valid": True, "points": int(s.x.size), "range": [float(s.x[0]), float(s.x[-1])], "warnings": s.warnings,
            "file_metadata": s.meta, "additional_spectra_in_file": len(s.extra_y)}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), sample_id: str = Form("uploaded"),
                  excitation_nm: float | None = Form(None), baseline: bool = Form(True), smooth: bool = Form(True),
                  window: int = Form(11), poly: int = Form(3), normalize: str = Form("vector"),
                  prominence: float = Form(0.05), als_lambda: float = Form(1e5), als_p: float = Form(0.01)):
    o = _opts(baseline, smooth, window, poly, normalize, prominence, als_lambda, als_p)
    return _run(await _read(file), sample_id[:80], "uploaded file", excitation_nm, o, filename=file.filename)


@app.post("/api/analyze/example/{sample_id}")
def analyze_example(sample_id: str, options: Options = Options()):
    m = next((e for e in pipeline.load_manifest("examples") if e["sample_id"] == sample_id), None)
    if not m:
        raise HTTPException(404, "Unknown example.")
    raw = (pipeline.DATA_DIR / "examples" / m["file"]).read_bytes()
    prov = {"category": m["category"], "description": m["description"], "source": m["source"], "license": m["license"]}
    return _run(raw, sample_id, f"bundled example ({m['category']})", m["excitation_nm"], options, prov)


@app.post("/api/report", response_class=HTMLResponse)
def report(result: dict):
    try:
        return reporting.build_report(result)
    except (KeyError, TypeError, IndexError):
        raise HTTPException(422, "Body must be an /api/analyze result.")


# ---------------------------------------------------------------- unified workflow: one upload -> one report

class FullReportExample(BaseModel):
    options: Options = Options()
    metadata: dict = {}


def _respond(events, stream: bool):
    """Streams NDJSON progress events (genuine stage completion), or returns the finished report as JSON."""
    if stream:
        return StreamingResponse((json.dumps(e) + "\n" for e in events), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    for e in events:
        if e["event"] == "error":
            raise HTTPException(422, e["message"])
        if e["event"] == "result":
            return JSONResponse(e["report"])
    raise HTTPException(500, "Analysis ended without a report.")


def _flag(v: str | None, default: bool = True) -> bool:
    """Form booleans with a real default: an omitted field keeps the default instead of reading as an unticked checkbox."""
    if v is None or v == "":
        return default
    if v.lower() in ("true", "1", "yes", "on"):
        return True
    if v.lower() in ("false", "0", "no", "off"):
        return False
    raise HTTPException(422, f"Invalid boolean value '{v}'.")


def _stem(filename: str | None) -> str:
    return (filename or "").rsplit(".", 1)[0][:80] if filename and "." in filename else (filename or "")[:80]


def _json_form(text: str, kind: type, name: str):
    try:
        v = json.loads(text or ("{}" if kind is dict else "[]"))
    except json.JSONDecodeError:
        raise HTTPException(422, f"'{name}' must be valid JSON.")
    if not isinstance(v, kind):
        raise HTTPException(422, f"'{name}' must be a JSON {'object' if kind is dict else 'array'}.")
    return v


@app.post("/api/full-report")
async def full_report(file: UploadFile = File(...), extra_files: list[UploadFile] = File(default=[]),
                      sample_id: str = Form("uploaded"), excitation_nm: float | None = Form(None),
                      origin: str = Form("unknown"), metadata: str = Form("{}"), primary_label: str = Form(""),
                      extra_labels: str = Form("[]"), stream: str | None = Form(None),
                      baseline: str | None = Form(None), smooth: str | None = Form(None), window: int = Form(11),
                      poly: int = Form(3), normalize: str = Form("vector"), prominence: float = Form(0.05),
                      als_lambda: float = Form(1e5), als_p: float = Form(0.01), despike: str | None = Form(None),
                      library: str = Form("auto")):
    o = _opts(_flag(baseline), _flag(smooth), window, poly, normalize, prominence, als_lambda, als_p, _flag(despike), library)
    meta = _json_form(metadata, dict, "metadata")
    labels = _json_form(extra_labels, list, "extra_labels")
    if len(extra_files) > orchestrator.MAX_EXTRAS:
        raise HTTPException(422, f"At most {orchestrator.MAX_EXTRAS} additional spectra.")
    raw = await _read(file)
    extras = [{"name": _stem(f.filename) or f"spectrum-{i + 2}", "filename": f.filename, "raw": await _read(f),
               "label": (str(labels[i])[:40] if i < len(labels) and labels[i] else None)} for i, f in enumerate(extra_files)]
    events = orchestrator.run(raw, sample_id[:80], "uploaded file", excitation_nm, o.model_dump(), meta, extras, origin,
                              primary_label=primary_label[:40] or None, filename=file.filename)
    return _respond(events, _flag(stream))


@app.post("/api/full-report/example/{sample_id}")
def full_report_example(sample_id: str, body: FullReportExample = FullReportExample(), stream: bool = True):
    m = next((e for e in pipeline.load_manifest("examples") if e["sample_id"] == sample_id), None)
    if not m:
        raise HTTPException(404, "Unknown example.")
    raw = (pipeline.DATA_DIR / "examples" / m["file"]).read_bytes()
    prov = {"category": m["category"], "description": m["description"], "source": m["source"], "license": m["license"]}
    events = orchestrator.run(raw, sample_id, f"bundled example ({m['category']})", m["excitation_nm"], body.options.model_dump(),
                              body.metadata, (), "synthetic", prov, orchestrator.example_truth(sample_id))
    return _respond(events, stream)


@app.post("/api/full-report/html", response_class=HTMLResponse)
def full_report_html(report: dict):
    try:
        return report_html.build(report)
    except (KeyError, TypeError, IndexError, ValueError):
        raise HTTPException(422, "Body must be a /api/full-report result.")
