# RamanReach reasearch tool

Open-source web tool for analysing Raman spectra: upload one file, every applicable analysis runs automatically, and the result is a single report that opens with a plain-language answer. **Experimental, non-diagnostic research prototype.**

Pipeline: file import (any common export) → validation → cosmic-ray removal → ALS baseline → Savitzky–Golay smoothing → normalisation → peak detection → comparison with measured (RRUFF, ROD) and synthetic references → calibrated quality gate (can return **inconclusive**) → robustness tests → plain-language explanation → HTML/PDF report and processed CSV.

Inspired by the open-source [CubeRaman](https://github.com/jacobbusshart/CubeRaman) project. That repository states no license, so none of its code or data is reused.

## Run locally (Windows)
```
cd backend
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000

cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
```
Tests: `cd backend; .venv\Scripts\python -m pytest -q` (150 tests) and `cd frontend; npm test` (51 tests).
For a separately hosted API set `VITE_API_URL` at frontend build time.

### Optional: AI-written explanations
Set `ANTHROPIC_API_KEY` before starting the backend. The report's "In plain words" card is then written by Claude (`RAMAN_LLM_MODEL`, default `claude-opus-5-5`) and fact-checked before it is shown; without a key, or if the check fails twice, a standard template summary is used. `RAMAN_LLM=off` disables the call. Only the numbered evidence facts are sent, never the uploaded file or the spectrum.

## Input formats
One spectrum file, ≤ 5 MB, ≥ 50 points:
- delimited text (`.csv .tsv .txt .dat`): comma, semicolon, tab, pipe or whitespace; decimal commas; any header wording (`Raman Shift (cm-1)`, `Wavenumber`, `#Wave`, `Counts`, …) or no header; metadata preambles and footers; UTF-8, Windows-1252 or UTF-16;
- RRUFF `.txt` (`##KEY=value` header), Raman Open Database `.rod`/`.cif`, JCAMP-DX `.jdx`/`.dx` (XYPOINTS or uncompressed AFFN), JSON (`{"raman_shift": [...], "intensity": [...]}`, pairs or records);
- several spectra in one file (extra intensity columns, or one spectrum per row under an axis row) are analysed together;
- x-axis as Raman shift, wavelength (nm) or absolute wavenumber; the excitation wavelength is read from the file when it states one, otherwise the UI asks for it.
Binary vendor files (`.spc`, `.wdf`, `.spe`, Excel) are rejected with an instruction to export as text. Small defects (a few empty cells, duplicate x values, unsorted axis) are repaired with a warning.

## Test files
`data/test_files/` holds 36 downloadable files (also on the Analyze page and at `GET /api/test-files/all.zip`), each with an expected outcome in `manifest.json`: real RRUFF/ROD spectra in every supported layout, acquisition problems (fluorescence, cosmic rays, noise, saturation, calibration offset, narrow range, mixture, material not in the library), synthetic organics, and invalid files with the error they should produce. Regenerate with `backend/scripts/make_test_files.py`.

## Reference data and evaluation
| Library | Contents | Built by |
|---|---|---|
| `measured` (`data/references_real/`) | 164 curated spectra of 60 minerals, ≥ 2 independent specimens each (RRUFF, ROD) | `scripts/fetch_rruff.py --select`, `scripts/fetch_rod.py`, `scripts/curate_library.py` |
| `synthetic_demo` (`data/references/`) | 5 idealised organics | `data/generate_synthetic.py` |

Uploads are compared with both (`library=auto`); bundled synthetic examples only with the synthetic set. `scripts/evaluate_library.py` runs a leave-one-specimen-out evaluation with negative controls and perturbations, calibrates the gate and writes `evaluation.json` + `thresholds.json`. Current cross-validated result: the gate answers for 59 % of held-out real spectra, is right 96 % of the time when it answers, and names a wrong material for 4 % of spectra whose material is absent from the library (`GET /api/evaluation`). Details: `docs/methodology.md`; sources and licences: `DATA_SOURCES.md`.

## Workflow orchestration
`backend/app/agent/graph.py` runs the analysis as a LangGraph state graph (validate → process → conditions → sensitivity → PCA → models → report → explain ⇄ fact-check → fallback). Each node calls the same stage function as the plain runner in `services/orchestrator.py`, so results are identical with or without LangGraph; the graph adds fatal-error routing and the draft → verify → retry/fallback loop for the explanation.

## API
`GET /health`, `GET /api/examples`, `GET /api/examples/{id}/download`, `GET /api/references?library=`, `GET /api/evaluation`, `GET /api/test-files`, `GET /api/test-files/{id}`, `GET /api/test-files/all.zip`, `POST /api/validate`, `POST /api/analyze`, `POST /api/analyze/example/{id}`, `POST /api/report`, `POST /api/full-report` (streams NDJSON stage events), `POST /api/full-report/example/{id}`, `POST /api/full-report/html`.

## What this is not
Not a diagnostic. A similarity score is not a probability of identification; a library can only recognise materials it contains. Never aim a Class 3B Raman laser at people.

## Research labs (v0.3.0 work in progress)
Tabs: Analyze Spectrum, Experimental Conditions Lab, Wavenumber Sensitivity Lab, PCA Explorer, Model Benchmark, Spectral Translation, Reports & Methodology.
Everything the labs compute from the bundled data is **simulated** (controlled perturbations of a synthetic library) and labelled as such; uploaded CSVs with metadata are labelled *user-declared measured*. Excitation wavelength and incidence/collection angle are never simulated.

Extra endpoints: `GET /api/perturbations`, `GET /api/conditions/excitation-info`, `POST /api/conditions/compare`, `POST /api/sensitivity/sweep`, `POST /api/sensitivity/matrix`, `POST /api/pca/run`, `POST /api/benchmark/run`, `POST /api/translation/evaluate`, `POST /api/report/research`.

Backend modules (`backend/app/services/`): `perturbations`, `dataset_builder`, `experiment_conditions`, `wavenumber_sensitivity`, `pca_analysis`, `model_benchmark`, `deep_models` (optional, PyTorch), `spectral_translation`, `evaluation_metrics`, `insight_generation`, `ml` (scikit-learn with NumPy fallback). Routes: `backend/app/research_routes.py`.

Run tests: `cd backend && .venv/Scripts/python -m pytest -q`. Frontend: `cd frontend && npm run build`.
Optional deep models: `pip install torch --index-url https://download.pytorch.org/whl/cpu`, then tick "Include deep models" in Model Benchmark.

## Diabetes urine study
The **Diabetes study** page (`#/diabetes`) applies Raman urinalysis to diabetes screening and to monitoring treatment response. It uses two datasets (see `DATA_SOURCES.md`): measured patient urine from Zenodo 7343559 (CC BY 1.0) and a **simulated** 12-week monitoring trial. For each dataset the page shows cohort mean spectra, glucose/ketone/urea band indices (normalised to creatinine at 680 cm⁻¹), PCA, a cross-validated screening classifier (ROC, sensitivity, specificity) and, for the trial, glucose-index trajectories. You can also place an uploaded urine spectrum within the cohort. Every result is drawn both as a 2D and an interactive 3D figure; the general analysis report likewise pairs 2D figures with 3D views. Raman spectroscopy monitors urine chemistry; it does not diagnose, treat or cure diabetes.

Regenerate data: `py data/urine/generate_urine_trial.py`; `backend/.venv/Scripts/python backend/scripts/fetch_urine_zenodo.py` (downloads ~145 MB into `data/raw/`).
Endpoints: `GET /api/urine/datasets`, `GET /api/urine/study/{trial|zenodo}`, `GET /api/urine/examples`, `GET /api/urine/examples/{id}/download`, `POST /api/urine/analyze` (file or `example`, `dataset`).

### Personalised monitoring (Study 1 of the programme)
The diabetes study is the first step of a personalised-healthcare programme (roadmap on the study page: kidney and metabolic health, multi-biofluid profiling, personal health baselines). Its **Personal profile** view reads each trial participant against their own week-0 baseline. A change counts as meaningful only if it exceeds the reference change value RCV = 1.96·√2·√(SDw² + (CV·baseline)²). SDw is measured from the visit-to-visit spread of the control participants; the within-person CV (20% for glucose and ketones, `ASSUMED_CV` in `services/urine.py`) is an assumption until repeat samples from stable patients are available. Endpoint: `GET /api/urine/participant/{id}`.

## Deploy on Render
`render.yaml` is a Render Blueprint that creates two services from this repository:
- **ramanreach-api**: Python web service (FastAPI). It builds from the repository root because it reads `data/`, runs on Python 3.12.8, and exposes the health check `/health`.
- **ramanreach-web**: static site (Vite build of `frontend/`). Its `VITE_API_URL` is filled in automatically with the API's address.

Steps: push to GitHub → Render Dashboard → **New → Blueprint** → select this repository → **Apply**. `ANTHROPIC_API_KEY` is optional; leave it empty to use the template summaries. On the free plan the API sleeps after 15 minutes without traffic, so the first request after a pause takes about 30–60 s. The optional PyTorch deep-learning models are not installed on Render.
