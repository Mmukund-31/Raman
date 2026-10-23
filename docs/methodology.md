# Methodology (as implemented, v0.2.0)

RamanReach is an experimental, non-diagnostic workflow for inspecting and comparing Raman spectra. Nothing here has been validated on measured data.

## Pipeline
1. **Validation** (`services/validation.py`): required columns, numeric and finite values, >= 50 points, sorted unique coordinates (unsorted data is sorted with a warning), non-constant intensity, 5 MB limit.
2. **Coordinates, excitation and calibration are three separate things.**
   - *Coordinate conversion*: only for `wavelength_nm` input. Raman shift (cm⁻¹) = 1e7/λ0 − 1e7/λ with λ in nm (1 cm = 1e7 nm). Stokes (λ > λ0) gives a positive shift; anti-Stokes (λ < λ0) a negative one — the sign is kept, not folded to positive. Requires a user-declared excitation wavelength; otherwise the file is rejected.
   - *Excitation metadata*: optional for `raman_shift_cm1` input. It is recorded as `user-declared` or `not provided`, and its absence is a non-blocking note.
   - *Calibration status*: always `not_verified`. The software cannot check an instrument's x-axis calibration, and a declared excitation wavelength does not change that.
3. **Baseline**: asymmetric least squares (λ = 1e5, p = 0.01, 10 iterations); corrected = raw − baseline. The raw spectrum is always returned alongside.
4. **Smoothing** (optional): Savitzky–Golay; window forced odd and clamped to the data length; polynomial order must be < window.
5. **Normalization** (optional): vector (L2), max, or none.
6. **Peaks**: `scipy.signal.find_peaks`, prominence ≥ a user-set fraction (default 5 %) of the processed range; peaks within 2 % of the range edge are flagged.
7. **Reference comparison**: sample and reference are resampled to a 2 cm⁻¹ grid over their overlap, mean-centred, and compared by cosine similarity. Each match also reports coverage (overlap ÷ reference range) and a peak-agreement summary: how many reference peaks in the overlap have a detected sample peak within ±10 cm⁻¹.
8. **Quality gate** → `ok` or `inconclusive` (see below).

## Similarity is not identification
A cosine similarity measures agreement of band shape under the chosen preprocessing. It is **not** a probability that the material is the reference. Every API response, the UI and the report say so. The "highest score" label means exactly that.

## SNR estimate (fixed in v0.2.0)
Earlier versions took the noise as the residual between the baseline-corrected and smoothed spectra. With smoothing disabled that residual is zero, which produced an artificial SNR of 1e9. The estimate now:
- is computed from the baseline-corrected data only, so it does **not** depend on the user's smoothing or normalization choices;
- takes noise as the robust sigma of first differences (1.4826·MAD/√2) and signal as the strongest feature above the median of a fixed-window smoothed copy;
- returns *undefined* (`null`) when the noise estimate is zero or numerically negligible, and an undefined SNR makes the result `inconclusive` rather than passing silently.
The first-difference noise estimate is conservative (over-estimates noise) on smooth, densely sampled data.

## Provisional quality thresholds
| Check | Value | Basis |
|---|---|---|
| SNR | ≥ 5 | engineering heuristic |
| Reference coverage | ≥ 70 % | engineering heuristic |
| Best similarity | ≥ 0.6 | engineering heuristic |
| Margin to second candidate | ≥ 0.05 | engineering heuristic |
| Peak-agreement tolerance | ±10 cm⁻¹ | readability, not instrument resolution |

These were **not derived from or tested on measured data**, so no sensitivity, specificity or accuracy can be claimed. They are published in every response (`quality_thresholds`) with the status "provisional". Replacing them requires labelled measurements from a characterised instrument.

## Data provenance
See `DATA_SOURCES.md`. The API response carries `data_provenance` (sample and per-reference category/source), the UI shows a SYNTHETIC DATA banner, and the HTML report repeats both. Uploaded files are labelled `user_supplied` (origin not verified).

## Research labs (simulation-based)
- **Perturbations** (`perturbations.py`) are tagged `axis_calibration`, `physical`, `instrumental` or `processing`. A global axis-calibration shift moves x of an unchanged signal; a physical shift moves the signal on a fixed axis. In reported coordinates they can be indistinguishable; only metadata or a calibration standard separates them. Temperature uses *user-specified* coefficients; laser power is gain + shot noise (+ optional saturation); no incidence-angle or excitation-wavelength model exists on purpose.
- **Sweeps** re-run the unchanged pipeline per level. "Correct" means status ok *and* top match = truth. Self-check: detected peak displacement must equal the injected shift within one grid step.
- **Experiment conditions**: metadata are normalised (K, nm, mW, s, degrees); changed / equal / unrecorded parameters are listed and multi-parameter changes are flagged as confounded. Peak height ratios are baseline-corrected counts, comparable only when acquisition settings match.
- **PCA**: identical preprocessing, documented scaling (mean-centre / Pareto / unit variance), explained variance, loadings with top regions, and eta-squared + silhouette per factor (material, condition) to show whether structure follows material or acquisition. In predictive use the scaler and PCA are inside the estimator and fitted on training specimens only (tested).
- **Benchmark**: 60/20/20 split by *specimen* per material (repeats never straddle splits), tuning on training data only, same preprocessing for all models, shift scenarios perturb test spectra only. Metrics: accuracy, macro-F1, per-class precision/recall, confusion matrix, ECE (probabilistic models), training/inference time, size. Deep models: CNN-1D and ResNet-18 with every 2-D operation replaced by its 1-D counterpart (block layout [2,2,2,2], widths 64–512), input = the same preprocessed spectra (constant rescale by sqrt(L)); off by default. RamanNet is not implemented (licence/dependency review and real multi-source data needed). This does **not** reproduce arXiv:2601.16107.
- **Translation**: parameters (shift, gain) are estimated from a separate calibration-standard pair, then evaluated on held-out pairs with RMSE, MAE, cosine, SAM, DTW, peak-position error, peak-preservation rate, relative-height error and downstream PCA+SVM accuracy/macro-F1, each against resampling only. No neural translator is trained.
- **Insights** (`insight_generation.py`) are rule-generated from computed metrics and labelled observed / supported / hypothesis / inconclusive, each with evidence, data class, validation status and limits. Model confidence is never evidence.
- **ML backend**: scikit-learn when importable, otherwise NumPy/SciPy equivalents (`ml.py`); results record which. The fallback SVM is a least-squares SVM with uncalibrated softmax scores.
