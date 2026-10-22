from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .services import pipeline, reporting
from .services.validation import MAX_BYTES, ValidationError, parse_csv

app = FastAPI(title="RamanReach API", version=pipeline.VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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


def _run(raw, sample_id, source, excitation_nm, options: Options):
    try:
        spec = parse_csv(raw, excitation_nm)
        return pipeline.analyze(spec, sample_id, source, excitation_nm, options.model_dump())
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
    return _run(raw, sample_id, f"bundled example ({m['category']})", m["excitation_nm"], options)


@app.post("/api/report", response_class=HTMLResponse)
def report(result: dict):
    try:
        return reporting.build_report(result)
    except (KeyError, TypeError, IndexError):
        raise HTTPException(422, "Body must be an /api/analyze result.")
