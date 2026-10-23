# Limitations and implementation status

## Status (v0.3.0)
Implemented and tested (150 backend, 51 frontend tests): format-tolerant import (delimited text, RRUFF, ROD, JCAMP-DX, JSON, multi-spectrum files), cosmic-ray removal, saturation warning, ALS baseline, smoothing, normalisation, peak detection, matching against a curated measured library (RRUFF + ROD) and the synthetic demo set, mixture check, a quality gate calibrated by held-out evaluation, robustness tests, a LangGraph workflow, a fact-checked plain-language explanation (Claude when configured, templates otherwise), HTML/PDF report, 36 downloadable test files with expected outcomes.
Not done: instrument integration, public deployment, user testing with non-specialists, a manual browser test pass of every page, a live run of the Claude explanation (no API key was available during development; the request shape and every fallback path are tested with a stub client).

## Scientific limitations
- **The library holds 60 minerals.** A spectrum of anything else (organics, polymers, pharmaceuticals, biological samples) can only be inconclusive or, in about 4 % of cases on the evaluation, wrongly named after the nearest mineral. The five synthetic organics cannot identify a real material and are flagged as synthetic wherever they appear.
- **The evaluation is optimistic for real uploads.** Queries are curated database spectra (good signal, mostly 532 nm, mineral specimens measured by expert labs). Spectra from other instruments, sample types or quality will usually do worse. The cross-validated share of wrong answers among all answers (including absent materials) is 11 %, above the 5 % target used for calibration.
- **Raw spectra are harder than processed ones.** An unmodified RRUFF RAW file can be inconclusive where the processed spectrum of the same measurement is a match.
- **Laboratory offsets.** Band positions differing by more than ~10 cm⁻¹ between laboratories (e.g. the ROD magnetite test file) make the band check fail, so the answer is inconclusive.
- Calibration of the x-axis is never verified; a 5 cm⁻¹ offset roughly halves how often the gate answers (48 % vs 62 % in-sample).
- Mixtures are detected only as "two references fit better than one" among the top candidates; three-component mixtures, minor phases and coatings are not handled.
- SNR, coverage and mixture thresholds remain provisional heuristics; only the similarity, margin and band-fraction thresholds are calibrated.
- Similarity ≠ identification probability.
- ALS and Savitzky–Golay settings can distort peaks; settings are recorded so results can be reproduced.
- The AI-written explanation can only restate the computed facts; the fact check verifies numbers, names and claims, not whether the wording is the clearest possible.

## Scope limits
- Not a diagnostic or clinical tool; no disease detection, glucose sensing, or reliable medicine-authenticity claims.
- Class 3B lasers (as in CubeRaman) must only be operated by trained people with appropriate safety controls.

## Research-lab limits (added with the labs)
- All lab results use **simulated** spectra derived from the **synthetic** reference library. They show how the analysis pipeline behaves, not how an instrument or material behaves, and give no real-world accuracy, tolerance or generalisation estimate.
- The synthetic classes are easy to separate, so clean-data benchmark scores sit at a ceiling and cannot rank models.
- No measured temperature, excitation-wavelength, laser-power or geometry dataset is bundled; those comparisons work only on user-uploaded CSVs with user-declared metadata. Temperature coefficients are user assumptions.
- Spectral translation is evaluated only as a controlled-perturbation benchmark; broadening/baseline are not inverted and no neural translator exists.
- Deep models were tried only on tiny simulated sets; they are not tuned and are off by default. RamanNet is not implemented.
- The quality gate is calibrated on measured mineral spectra only; the simulated labs still use the synthetic library.
- scikit-learn (1.9.1) now loads in `backend/.venv`, so the tests exercise it; the NumPy fallback in `ml.py` is kept for machines where it cannot load.
