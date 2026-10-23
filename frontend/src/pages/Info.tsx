export function About() {
  return (
    <div className="space-y-3 text-sm">
      <h2 className="text-2xl font-bold">Methodology & limitations</h2>
      <p><b>Pipeline:</b> validation → asymmetric least squares (ALS) baseline → optional Savitzky–Golay smoothing → optional normalization → SciPy peak detection → cosine similarity against references resampled onto a common 2 cm⁻¹ grid over the overlapping range.</p>
      <p><b>Inconclusive rules:</b> SNR undefined or below 5, reference coverage below 70%, best similarity below 0.6, or top-two scores within 0.05. These thresholds are provisional heuristics, not validated on measured data.</p>
      <p><b>Inspiration:</b> the open-source <a className="text-blue-700 underline" href="https://github.com/jacobbusshart/CubeRaman">CubeRaman</a> hardware project. The repository states no license, so no CubeRaman code or data is reused; RamanReach is an independent implementation of standard methods.</p>
      <p><b>Data:</b> all bundled spectra are <b>synthetic</b> (Lorentzian bands at approximate literature positions). They demonstrate the workflow and are not measurements. Matching real spectra needs a validated reference library and instrument calibration.</p>
      <p><b>Not validated:</b> any diagnostic, clinical, medicine-authenticity or glucose-sensing use. A similarity score is not an identification probability. The CubeRaman laser is Class 3B; never aim it at people.</p>
    </div>
  )
}
