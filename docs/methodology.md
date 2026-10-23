# Methodology (as implemented, v0.3.0)

RamanReach is an experimental, non-diagnostic workflow for inspecting and comparing Raman spectra. The matching gate is calibrated on curated measured spectra (below); everything else remains a documented heuristic.

## Pipeline
1. **Import** (`services/formats.py`, `parse_any`): the format is detected from the content (RRUFF `##` header, ROD CIF loop, JCAMP-DX, JSON, otherwise delimited text). For text the delimiter and decimal separator are chosen as the split under which most candidate rows have the same number (≥ 2) of numeric fields; preamble lines are read for an excitation wavelength (numbers carrying another unit, e.g. laser power in mW, are ignored); header words decide which column is the x-axis (Raman shift, wavelength, absolute wavenumber) and which is intensity; extra intensity columns, or rows under an axis row, become additional spectra. Binary vendor formats are rejected with an export instruction.
2. **Validation** (`services/validation.py`, `finalise`): ≥ 50 finite points, 5 MB limit, non-constant intensity. In the upload path small defects are repaired with a warning: up to 5 % unusable rows are dropped, duplicate coordinates are averaged, an unsorted axis is sorted. The original strict CSV parser (`parse_csv`) is unchanged.
3. **Coordinates, excitation and calibration are three separate things.**
   - *Coordinate conversion*: wavelength (nm) → shift = 1e7/λ0 − 1e7/λ; absolute wavenumber → shift = 1e7/λ0 − ν̃. Both need the excitation wavelength, taken from the user or, if absent, from the file. The sign is kept (anti-Stokes is negative).
   - *Excitation metadata*: optional for Raman-shift input.
   - *Calibration status*: always `not_verified`.
4. **Cosmic-ray removal** (`preprocessing.despike`, on by default): a point is a spike when it exceeds a 5-point running median by > 6 robust noise sigmas **and** that excess is ≥ 75 % of its height above the local floor. Bands spanning ≥ 3 points fail the second test because the 5-point median still sits high on them; a 1–2 point spike leaves the median at the floor. Spikes are replaced by linear interpolation; the raw spectrum is always kept and the count is reported.
5. **Saturation check** (`quality.saturation`): ≥ 3 consecutive points at exactly the maximum value → reliability warning.
6. **Baseline**: asymmetric least squares (λ = 1e5, p = 0.01, 10 iterations).
7. **Smoothing** (optional): Savitzky–Golay; window forced odd and clamped; order < window.
8. **Normalisation** (optional): vector (L2), max, or none.
9. **Peaks**: `scipy.signal.find_peaks`, prominence ≥ 5 % of the processed range by default.
10. **Reference comparison** (`services/matching.py`): sample and reference (preprocessed identically, references cached per setting) are resampled to a 2 cm⁻¹ grid over their overlap, mean-centred and compared by cosine similarity. Each match also reports reference coverage (overlap ÷ reference range), **sample coverage** (share of the sample's squared band intensity inside the overlap: a narrow reference can otherwise score highly while ignoring most bands) and peak agreement (reference peaks in the overlap with a sample peak within ±10 cm⁻¹). Candidates are ranked by cosine discounted for low coverage, and several spectra of one material count as one candidate (its best spectrum), so the margin compares different materials.
11. **Mixture check** (`matching.mixture_check`): for every pair of the top 5 candidates, non-negative least squares fits sample ≈ a·r₁ + b·r₂ + c. If the best pair's cosine beats the best single reference by ≥ 0.05 and each component carries ≥ 20 % of the fitted intensity, a single-material answer is blocked ("looks like a mixture of X and Y"). On the held-out evaluation it did not change any result on pure specimens; it does not prove the sample is that mixture.
12. **Quality gate** → `ok` or `inconclusive` (below).

## Similarity is not identification
A cosine similarity measures agreement of band shape under the chosen preprocessing. It is **not** a probability that the material is the reference. Every API response, the UI and the report say so.

## SNR estimate
Computed from the baseline-corrected data only (independent of smoothing/normalisation): noise = robust sigma of first differences (1.4826·MAD/√2), signal = strongest feature above the median of a fixed-window smoothed copy; *undefined* when the noise estimate is numerically zero, which makes the result inconclusive. Conservative on smooth, densely sampled data.

## Quality gate
| Check | Value | Basis |
|---|---|---|
| Best similarity | ≥ 0.50 | **calibrated** (`data/references_real/thresholds.json`) |
| Margin to the next material | ≥ 0.11 | **calibrated** |
| Reference bands present in the sample | ≥ 65 % | **calibrated** |
| SNR | ≥ 5 | provisional heuristic |
| Reference coverage | ≥ 70 % | provisional heuristic |
| Sample intensity inside the compared range | ≥ 60 % | provisional heuristic |
| Two-material fit better than one | blocks | heuristic (see mixture check) |
| Peak-agreement tolerance | ±10 cm⁻¹ | readability, not instrument resolution |

Without `thresholds.json` the original provisional values are used (similarity ≥ 0.6, margin ≥ 0.05, no band check). Every response publishes the thresholds in use and their status.

## Evaluation and calibration (`services/evaluation_real.py`, `scripts/evaluate_library.py`)
- **Library**: 164 measured spectra of 60 minerals, each material with ≥ 2 independent specimens (see `DATA_SOURCES.md`).
- **Protocol: leave-one-specimen-out.** Each spectrum is a query against the library without that spectrum, so it can only match *other* specimens of its material. Every query runs through `pipeline.analyze`, the code path used for uploads.
- **Negative control**: the query's whole material is removed; any answer is a false match. This is the hard case: an absent garnet still looks like the garnets that remain.
- **Perturbations**: Gaussian noise (σ = 5 % of peak-to-peak), a fluorescence-like background (2× peak-to-peak), a 5 cm⁻¹ axis offset.
- **Calibration**: a grid search over (similarity, margin, band fraction) picks the loosest thresholds that keep the false-match rate among all answered queries (wrong positives + answered negatives) ≤ 5 % while maximising correct answers.
- **Honest estimate**: 5-fold cross-validation grouped by material: thresholds are chosen on four fifths of the materials and scored on the held-out fifth.

| Result (2026-10-23) | Value |
|---|---|
| Correct material ranked first, no gate | 86 % (top 5: 96 %) |
| Answered (cross-validated) | 59 % of queries |
| Right when answered (cross-validated) | 96 % |
| Wrong answer when the material is absent (cross-validated) | 4 % |
| Wrong answers among all answers incl. negative controls (cross-validated) | 11 %, above the 5 % target the thresholds were fitted for |
| Answered / right, in-sample: clean · noise · fluorescence · 5 cm⁻¹ offset | 62 %/100 % · 60 %/99 % · 60 %/100 % · 48 %/94 % |

Variants tried and rejected on these numbers: a ±6 cm⁻¹ shift-tolerant cosine and square-root intensity compression raised top-1 accuracy slightly (to 90 %) but, once gated, answered fewer queries or had a higher cross-validated false-match rate.

## Plain-language explanation (`services/explanation.py`, `agent/`)
- `evidence(report)` turns the computed sections into numbered facts (E1, E2, …): verdict and its reasons, peaks, closest and runner-up reference with scores, coverage, SNR, library, robustness, the evaluation track record, the file's own label (marked "not verified, not used"), calibration status and suggested next steps.
- **Standard summary** (`rule_based`): fixed templates over those facts; used when no LLM is configured, and as the fallback.
- **LLM summary** (`agent/llm.py`): Claude receives only the facts (no file, no spectrum, no user metadata) and returns JSON constrained by a schema (headline, findings with cited fact ids, how sure, what it does not mean, next steps). No sampling parameters are sent; effort is `low`; refusals and API errors fall back.
- **Fact check** (`explanation.verify`), deterministic: every cited id exists; every number is present in the facts at the precision it is written with (99.9 is not supported by 1.00; 100 is); no library material outside the facts is named; no medical/safety/authenticity wording; if the result is inconclusive the headline must say so and no sentence may present an identification. A failed draft is retried once with the problems listed, then replaced by the standard summary. The report states which version is shown.
- **Orchestration** (`agent/graph.py`): a LangGraph state graph whose nodes call the same stage functions as the linear runner; it adds stop-on-fatal-error routing and the draft → verify → retry/fallback loop. Stage events are streamed through LangGraph's custom stream in the existing NDJSON format.

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
