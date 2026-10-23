import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .research_routes import router as research_router
from .services import orchestrator, pipeline, report_html, reporting
from .services.validation import MAX_BYTES, ValidationError, parse_csv

app = FastAPI(title="RamanReach API", version=pipeline.VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(research_router)


class Options(BaseModel):
    baseline: bool = True
    als_lambda: float = Field(1e5, gt=0)
    als_p: float = Field(0.01, gt=0, lt=1)
    smooth: bool = True
    window: int = Field(11, ge=3, le=101)
    poly: int = Field(3, ge=1, le=7)
    normalize: str = Field("vector", pattern="^(none|vector|max)$")
    prominence: float = Field(0.05, gt=0, lt=1)


async def _read(file: UploadFile) -> bytes:
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "File exceeds the 5 MB limit.")
    return raw


def _run(raw, sample_id, source, excitation_nm, options: Options, provenance=None):
    try:
        spec = parse_csv(raw, excitation_nm)
        return pipeline.analyze(spec, sample_id, source, excitation_nm, options.model_dump(), provenance)
    except ValidationError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


def _opts(baseline, smooth, window, poly, normalize, prominence, als_lambda, als_p):
    try:
        return Options(baseline=baseline, smooth=smooth, window=window, poly=poly, normalize=normalize,
                       prominence=prominence, als_lambda=als_lambda, als_p=als_p)
    except Exception as e:
        raise HTTPException(422, f"Invalid options: {e}")


@app.get("/health")
def health():
    return {"status": "ok", "version": pipeline.VERSION}


@app.get("/api/examples")
def examples():
    return pipeline.load_manifest("examples")


@app.get("/api/references")
def references():
    return pipeline.load_manifest("references")


@app.post("/api/validate")
async def validate(file: UploadFile = File(...), excitation_nm: float | None = Form(None)):
    try:
        s = parse_csv(await _read(file), excitation_nm)
    except ValidationError as e:
        raise HTTPException(422, str(e))
    return {"valid": True, "points": int(s.x.size), "range": [float(s.x[0]), float(s.x[-1])], "warnings": s.warnings}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), sample_id: str = Form("uploaded"),
                  excitation_nm: float | None = Form(None), baseline: bool = Form(True), smooth: bool = Form(True),
                  window: int = Form(11), poly: int = Form(3), normalize: str = Form("vector"),
                  prominence: float = Form(0.05), als_lambda: float = Form(1e5), als_p: float = Form(0.01)):
    o = _opts(baseline, smooth, window, poly, normalize, prominence, als_lambda, als_p)
    return _run(await _read(file), sample_id[:80], "uploaded file", excitation_nm, o)


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
                      als_lambda: float = Form(1e5), als_p: float = Form(0.01)):
    o = _opts(_flag(baseline), _flag(smooth), window, poly, normalize, prominence, als_lambda, als_p)
    meta = _json_form(metadata, dict, "metadata")
    labels = _json_form(extra_labels, list, "extra_labels")
    if len(extra_files) > orchestrator.MAX_EXTRAS:
        raise HTTPException(422, f"At most {orchestrator.MAX_EXTRAS} additional spectra.")
    raw = await _read(file)
    extras = [{"name": (f.filename or f"spectrum-{i + 2}").removesuffix(".csv")[:80], "raw": await _read(f),
               "label": (str(labels[i])[:40] if i < len(labels) and labels[i] else None)} for i, f in enumerate(extra_files)]
    events = orchestrator.run(raw, sample_id[:80], "uploaded file", excitation_nm, o.model_dump(), meta, extras, origin,
                              primary_label=primary_label[:40] or None)
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
