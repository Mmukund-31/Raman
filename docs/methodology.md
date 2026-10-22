# Methodology
1. Validation: required columns, numeric/finite, >=50 points, sorted/unique coordinates, wavelength->shift only with excitation nm (shift = 1e7/λ0 - 1e7/λ).
2. Baseline: asymmetric least squares (lambda=1e5, p=0.01, 10 iterations); y_corrected = y_raw - b.
3. Smoothing: Savitzky–Golay (odd window clamped to data length, polynomial < window).
4. Normalization: vector (L2), max, or none; recorded in the report.
5. Peaks: scipy.signal.find_peaks, prominence >= 5% of the processed range; peaks within 2% of range edges are flagged.
6. Matching: both spectra resampled to a 2 cm-1 grid over their overlap, mean-centered, cosine similarity. Coverage = overlap / reference range.
7. Quality: SNR = peak-to-peak(smoothed) / std(baseline-removed - smoothed). Inconclusive if SNR<5, coverage<70%, best score<0.6, or top-2 margin<0.05.
