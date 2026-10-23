# RamanReach

Open-source web tool for inspecting, processing and comparing Raman spectra. **Experimental, non-diagnostic research prototype.**

Pipeline: CSV upload → validation → ALS baseline → Savitzky–Golay smoothing → normalization → peak detection → cosine-similarity reference comparison → quality checks (can return **inconclusive**) → HTML report / processed CSV.

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
Tests: `cd backend; .venv\Scripts\python -m pytest`.
For a separately hosted API set `VITE_API_URL` at frontend build time.

## Input format
`raman_shift_cm1,intensity` (≥50 rows, ≤5 MB). `wavelength_nm,intensity` is accepted only with an excitation wavelength (nm).

## Status and data
v0.2.0 - working local prototype, 20 backend tests. See `docs/methodology.md` (method, provisional thresholds), `docs/limitations.md` (status and limits) and `DATA_SOURCES.md` (provenance).
All bundled spectra are **synthetic** (`data/generate_synthetic.py`). They demonstrate the workflow; they are not measurements, and near-perfect demo scores are circular because examples and references share one generator.
Quality thresholds are provisional, unvalidated heuristics. Excitation wavelength is optional metadata; calibration is never verified.

## API
`GET /health`, `GET /api/examples`, `GET /api/references`, `POST /api/validate`, `POST /api/analyze`, `POST /api/analyze/example/{id}`, `POST /api/report`.

## What this is not
Not a diagnostic. A similarity score is not a probability of identification. Never aim a Class 3B Raman laser at people.

## Research labs (v0.3.0 work in progress)
Tabs: Analyze Spectrum, Experimental Conditions Lab, Wavenumber Sensitivity Lab, PCA Explorer, Model Benchmark, Spectral Translation, Reports & Methodology.
Everything the labs compute from the bundled data is **simulated** (controlled perturbations of a synthetic library) and labelled as such; uploaded CSVs with metadata are labelled *user-declared measured*. Excitation wavelength and incidence/collection angle are never simulated.

Extra endpoints: `GET /api/perturbations`, `GET /api/conditions/excitation-info`, `POST /api/conditions/compare`, `POST /api/sensitivity/sweep`, `POST /api/sensitivity/matrix`, `POST /api/pca/run`, `POST /api/benchmark/run`, `POST /api/translation/evaluate`, `POST /api/report/research`.

Backend modules (`backend/app/services/`): `perturbations`, `dataset_builder`, `experiment_conditions`, `wavenumber_sensitivity`, `pca_analysis`, `model_benchmark`, `deep_models` (optional, PyTorch), `spectral_translation`, `evaluation_metrics`, `insight_generation`, `ml` (scikit-learn with NumPy fallback). Routes: `backend/app/research_routes.py`.

Run tests: `cd backend && .venv/Scripts/python -m pytest -q`. Frontend: `cd frontend && npm run build`.
Optional deep models: `pip install torch --index-url https://download.pytorch.org/whl/cpu`, then tick "Include deep models" in Model Benchmark.
