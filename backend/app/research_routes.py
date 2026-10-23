"""HTTP layer for the research workflows. Computation lives in services/; this module validates and shapes requests."""
import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .services import (dataset_builder, experiment_conditions, insight_generation as ig, model_benchmark, pca_analysis,
                       perturbations, pipeline, reporting, spectral_translation, wavenumber_sensitivity)
from .services.formats import parse_any
from .services.validation import ValidationError

router = APIRouter(prefix="/api")


class SpectrumRef(BaseModel):
    example_id: str | None = None
    reference_id: str | None = None
    csv_text: str | None = Field(None, max_length=5_000_000)
    excitation_nm: float | None = None


class Step(BaseModel):
    kind: str
    params: dict = {}


class Opts(BaseModel):
    baseline: bool = True
    als_lambda: float = Field(1e5, gt=0)
    als_p: float = Field(0.01, gt=0, lt=1)
    smooth: bool = True
    window: int = Field(11, ge=3, le=101)
    poly: int = Field(3, ge=1, le=7)
    normalize: str = Field("vector", pattern="^(none|vector|max)$")
    prominence: float = Field(0.05, gt=0, lt=1)


class ExperimentIn(BaseModel):
    label: str = Field(..., max_length=60)
    data_class: str = "measured"
    metadata: dict = {}
    spectrum: SpectrumRef | None = None
    simulate: list[Step] | None = None  # derive from the baseline spectrum by controlled perturbations
    seed: int = 0


class ConditionsRequest(BaseModel):
    baseline: ExperimentIn
    experiments: list[ExperimentIn] = Field(..., min_length=1, max_length=8)
    options: Opts = Opts()
    truth: str | None = None
    peak_tolerance_cm1: float = Field(15.0, gt=0, le=100)


class SweepRequest(BaseModel):
    spectrum: SpectrumRef
    truth: str | None = None
    kind: str = "axis_shift"
    levels: list[float] | None = Field(None, max_length=25)
    fixed_params: dict = {}
    options: Opts = Opts()
    seed: int = 0
    with_model: bool = False


class MatrixRequest(BaseModel):
    spectrum: SpectrumRef
    truth: str | None = None
    kinds: list[str] | None = None
    options: Opts = Opts()
    seed: int = 0


class PcaRequest(BaseModel):
    materials: list[str] | None = None
    n_specimens: int = Field(8, ge=2, le=40)
    n_repeats: int = Field(2, ge=1, le=5)
    seed: int = 0
    conditions: list[dict] | None = None
    noise_frac: float = Field(0.02, ge=0, le=1)
    options: Opts = Opts()
    n_components: int = Field(5, ge=2, le=10)
    scaling: str = Field("none", pattern="^(none|standard|pareto)$")
    factors: list[str] = ["material", "condition"]


class BenchmarkRequest(BaseModel):
    materials: list[str] | None = None
    n_specimens: int = Field(24, ge=6, le=60)
    n_repeats: int = Field(2, ge=1, le=4)
    seed: int = 0
    scaling: str = Field("none", pattern="^(none|standard|pareto)$")
    include_deep: bool = False
    deep_epochs: int = Field(30, ge=2, le=100)
    scenarios: list[dict] | None = None


class TranslationRequest(BaseModel):
    n_specimens: int = Field(16, ge=6, le=40)
    seed: int = 0
    standard: str = "polypropylene"
    source_steps: list[Step] | None = None
    source_grid_step: float = Field(3.0, ge=0.5, le=10)


class StudyIn(BaseModel):
    kind: str
    title: str = Field("Study", max_length=120)
    result: dict


def _fail(e):
    raise HTTPException(422, str(e))


def _load(ref: SpectrumRef):
    """Returns (x, y, label, truth_guess, data_class)."""
    refs = {r["id"]: r for r in pipeline.load_references()}
    if ref.reference_id:
        if ref.reference_id not in refs:
            raise HTTPException(404, "Unknown reference.")
        r = refs[ref.reference_id]
        return r["x"], r["y"], r["id"], r["id"], "synthetic_example"
    if ref.example_id:
        m = next((e for e in pipeline.load_manifest("examples") if e["sample_id"] == ref.example_id), None)
        if not m:
            raise HTTPException(404, "Unknown example.")
        x, y = pipeline.read_xy(pipeline.DATA_DIR / "examples" / m["file"])
        guess = ref.example_id.replace("demo_", "").replace("_synthetic", "")
        return x, y, ref.example_id, guess if guess in refs else None, "synthetic_example"
    if ref.csv_text:
        try:
            s = parse_any(ref.csv_text.encode(), None, ref.excitation_nm)
        except ValidationError as e:
            _fail(e)
        return s.x, s.y, "uploaded", None, "measured"
    raise HTTPException(422, "Provide example_id, reference_id or csv_text.")


def _finish(kind, res, insights):
    res["insights"] = insights
    res["report"] = ig.report_sections(kind, res)
    return res


@router.get("/perturbations")
def list_perturbations():
    return [{"kind": k, **v, "level_unit": wavenumber_sensitivity.UNIT.get(k), "default_levels": wavenumber_sensitivity.DEFAULT_LEVELS.get(k)}
            for k, v in perturbations.KINDS.items()]


@router.get("/conditions/excitation-info")
def excitation_info(excitation_nm: float, shift_min: float = 200, shift_max: float = 3000):
    try:
        return experiment_conditions.excitation_info(excitation_nm, shift_min, shift_max)
    except ValueError as e:
        _fail(e)


@router.post("/conditions/compare")
def conditions_compare(req: ConditionsRequest):
    try:
        if req.baseline.spectrum is None:
            raise ValueError("The baseline needs a spectrum.")
        bx, by, blabel, guess, bclass = _load(req.baseline.spectrum)
        base = {"label": req.baseline.label, "data_class": req.baseline.data_class if req.baseline.spectrum.csv_text else bclass,
                "metadata": req.baseline.metadata, "x": bx, "y": by}
        bmeta = experiment_conditions.normalize_metadata(req.baseline.metadata)
        exps = []
        for e in req.experiments:
            if e.simulate:
                x, y, recs = perturbations.apply_chain(bx, by, [s.model_dump() for s in e.simulate], e.seed)
                meta = dict(req.baseline.metadata)
                for r in recs:  # keep metadata consistent with the simulated change; never invent other fields
                    if r["kind"] == "temperature" and bmeta["temperature_K"]:
                        meta.update(temperature=bmeta["temperature_K"] + r["params"]["delta_T_K"], temperature_unit="K")
                    if r["kind"] == "laser_power" and bmeta["laser_power_mW"]:
                        meta.update(laser_power=bmeta["laser_power_mW"] * r["params"]["factor"], laser_power_unit="mW")
                exps.append({"label": e.label, "data_class": "simulated", "metadata": meta, "x": x, "y": y, "perturbations": recs})
            elif e.spectrum:
                x, y, _, _, cls = _load(e.spectrum)
                exps.append({"label": e.label, "data_class": e.data_class if e.spectrum.csv_text else cls,
                             "metadata": e.metadata, "x": x, "y": y})
            else:
                raise ValueError(f"'{e.label}' needs either a spectrum or a simulate recipe.")
        res = experiment_conditions.compare(base, exps, req.options.model_dump(), req.truth or guess, req.peak_tolerance_cm1)
    except ValueError as e:
        _fail(e)
    res["data_class"] = "simulated" if any(x["data_class"] == "simulated" for x in res["experiments"]) else (
        "measured" if all(x["data_class"] == "measured" for x in res["experiments"]) and res["baseline"]["data_class"] == "measured"
        else "synthetic_example")
    return _finish("conditions", res, ig.from_conditions(res))


@router.post("/sensitivity/sweep")
def sensitivity_sweep(req: SweepRequest):
    try:
        x, y, label, guess, _ = _load(req.spectrum)
        res = wavenumber_sensitivity.sweep(x, y, req.truth or guess, req.kind, req.levels, req.options.model_dump(),
                                           req.fixed_params, req.seed, req.with_model, label)
    except ValueError as e:
        _fail(e)
    return _finish("sweep", res, ig.from_sweep(res))


@router.post("/sensitivity/matrix")
def sensitivity_matrix(req: MatrixRequest):
    try:
        x, y, label, guess, _ = _load(req.spectrum)
        res = wavenumber_sensitivity.experiment_matrix(x, y, req.truth or guess, req.kinds, req.options.model_dump(), req.seed)
    except ValueError as e:
        _fail(e)
    res["sample"] = label
    return res


@router.post("/pca/run")
def pca_run(req: PcaRequest):
    try:
        cfg = {"materials": req.materials, "n_specimens": req.n_specimens, "n_repeats": req.n_repeats, "seed": req.seed,
               "conditions": req.conditions, "noise_frac": req.noise_frac}
        res = pca_analysis.run_on_simulated(cfg, req.options.model_dump(), req.n_components, req.scaling, tuple(req.factors))
    except (ValueError, KeyError, TypeError) as e:
        _fail(e)
    return _finish("pca", res, ig.from_pca(res))


@router.post("/benchmark/run")
def benchmark_run(req: BenchmarkRequest):
    try:
        res = model_benchmark.run_benchmark(req.model_dump())
    except (ValueError, KeyError, TypeError) as e:
        _fail(e)
    res = dict(res)
    return _finish("benchmark", res, ig.from_benchmark(res))


@router.post("/translation/evaluate")
def translation_evaluate(req: TranslationRequest):
    cfg = {"n_specimens": req.n_specimens, "seed": req.seed, "standard": req.standard, "source_grid_step": req.source_grid_step}
    if req.source_steps:
        cfg["source_steps"] = [s.model_dump() for s in req.source_steps]
    try:
        res = spectral_translation.run_controlled_benchmark(cfg)
    except (ValueError, KeyError, TypeError) as e:
        _fail(e)
    return _finish("translation", res, ig.from_translation(res))


@router.post("/report/research", response_class=HTMLResponse)
def research_report(studies: list[StudyIn]):
    if not studies or len(studies) > 12:
        raise HTTPException(422, "Provide 1-12 studies.")
    try:
        return reporting.build_research_report([s.model_dump() for s in studies])
    except (KeyError, TypeError):
        raise HTTPException(422, "Each study needs kind, title and a result from a research endpoint.")
