# Limitations and implementation status

## Status (v0.2.0)
Implemented and tested (20 pytest tests): CSV validation, ALS baseline, Savitzky–Golay smoothing, normalization, peak detection, cosine-similarity comparison with peak-agreement explanations, provisional quality gate with inconclusive outcome, HTML report, processed-CSV export, React UI.
Not done: real reference spectra, measured data, instrument integration, public deployment, community interviews, a browser-based UI test pass.

## Scientific limitations
- **All bundled spectra are synthetic.** References and examples come from one generator (`data/generate_synthetic.py`: Lorentzian bands at approximate literature positions). Because examples and references share that model, near-1.0 scores on the demos are expected and are **not evidence of real-world performance**.
- Real spectra differ in relative intensities, band widths, fluorescence, detector response and calibration. The software has never been run on a measured spectrum in this repository.
- Quality thresholds are provisional heuristics (see `methodology.md`). No accuracy, sensitivity or specificity is claimed, and none can be estimated from the available data.
- Calibration of the x-axis is never verified; excitation wavelength is user-declared metadata.
- Similarity ≠ identification probability. A high score against an unrepresentative library can be wrong, and the library covers only five materials.
- ALS and Savitzky–Golay settings can distort peaks; settings are recorded so results can be reproduced and reviewed.
- No machine-learning model is used: there is no labelled dataset that could support one.

## Scope limits
- Not a diagnostic or clinical tool; no disease detection, glucose sensing, or reliable medicine-authenticity claims.
- Class 3B lasers (as in CubeRaman) must only be operated by trained people with appropriate safety controls.

## Research-lab limits (added with the labs)
- All lab results use **simulated** spectra derived from the **synthetic** reference library. They show how the analysis pipeline behaves, not how an instrument or material behaves, and give no real-world accuracy, tolerance or generalisation estimate.
- The synthetic classes are easy to separate, so clean-data benchmark scores sit at a ceiling and cannot rank models.
- No measured temperature, excitation-wavelength, laser-power or geometry dataset is bundled; those comparisons work only on user-uploaded CSVs with user-declared metadata. Temperature coefficients are user assumptions.
- Spectral translation is evaluated only as a controlled-perturbation benchmark; broadening/baseline are not inverted and no neural translator exists.
- Deep models were tried only on tiny simulated sets; they are not tuned and are off by default. RamanNet is not implemented.
- Quality thresholds that decide "inconclusive" remain provisional.
- On the development machine scikit-learn could not load (Windows Application Control), so tests ran on the NumPy fallback in `ml.py`; scikit-learn paths are therefore untested here.
