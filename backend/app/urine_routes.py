"""HTTP layer for the Diabetes Urine Study. Computation lives in services/urine.py."""
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .services import urine
from .services.formats import parse_any
from .services.validation import MAX_BYTES, ValidationError

router = APIRouter(prefix="/api/urine")


def _dataset(d: str) -> str:
    if d not in urine.DATASETS:
        raise HTTPException(422, f"Unknown dataset. Choose one of: {', '.join(urine.DATASETS)}.")
    return d


@router.get("/datasets")
def datasets():
    return urine.available()


@router.get("/study/{dataset}")
def study(dataset: str):
    try:
        return urine.study(_dataset(dataset))
    except urine.DatasetUnavailable as e:
        raise HTTPException(404, str(e))


@router.get("/participant/{pid}")
def participant(pid: str, dataset: str = "trial"):
    try:
        return urine.participant(pid, _dataset(dataset))
    except KeyError:
        raise HTTPException(404, "Unknown participant.")
    except urine.DatasetUnavailable as e:
        raise HTTPException(404, str(e))


@router.get("/examples")
def examples():
    return urine.examples()


@router.get("/examples/{sample_id}/download")
def example_download(sample_id: str):
    m = next((e for e in urine.examples() if e["sample_id"] == sample_id), None)
    path = (urine.URINE_DIR / "examples" / m["file"]).resolve() if m else None
    if not path or path.parent != (urine.URINE_DIR / "examples").resolve() or not path.is_file():
        raise HTTPException(404, "Unknown example.")
    return FileResponse(path, filename=path.name, media_type="text/csv")


@router.post("/analyze")
async def analyze(file: UploadFile | None = File(None), example: str = Form(""), dataset: str = Form("trial"),
                  excitation_nm: float | None = Form(None)):
    d = _dataset(dataset)
    if example:
        m = next((e for e in urine.examples() if e["sample_id"] == example), None)
        if not m:
            raise HTTPException(404, "Unknown example.")
        raw, name = (urine.URINE_DIR / "examples" / m["file"]).read_bytes(), m["file"]
    elif file is not None:
        raw, name = await file.read(MAX_BYTES + 1), file.filename
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "File exceeds the 5 MB limit.")
    else:
        raise HTTPException(422, "Upload a urine spectrum or choose an example.")
    try:
        s = parse_any(raw, name, excitation_nm)
        out = urine.analyze(s.x, s.y, d)
    except urine.DatasetUnavailable as e:
        raise HTTPException(404, str(e))
    except (ValidationError, ValueError) as e:
        raise HTTPException(422, str(e))
    out["sample_name"] = (name or "uploaded").rsplit(".", 1)[0][:80]
    out["warnings"] = s.warnings
    return json.loads(json.dumps(out, allow_nan=False, default=float))
