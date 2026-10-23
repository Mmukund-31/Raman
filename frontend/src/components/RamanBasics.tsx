/** Explanatory text and schematic diagrams. Nothing here is measured or computed from user data. */

function Arrow({ id, color }: { id: string; color: string }) {
  return (
    <marker id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill={color} />
    </marker>
  )
}

function EnergyLevels() {
  const cols = [
    { name: 'Rayleigh (elastic)', x: 110, end: 'v = 0', endY: 210, color: '#444', note: 'same energy out as in' },
    { name: 'Stokes', x: 320, end: 'v = 1', endY: 170, color: '#D55E00', note: 'molecule gains hν_vib; photon loses it' },
    { name: 'Anti-Stokes', x: 530, end: 'v = 0', endY: 210, color: '#0072B2', note: 'molecule loses hν_vib; photon gains it' },
  ]
  const start = [210, 210, 170]
  return (
    <svg viewBox="0 0 640 290" width="100%" role="img" aria-label="Energy-level diagram of Rayleigh, Stokes and anti-Stokes scattering">
      <defs><Arrow id="ar0" color="#444" /><Arrow id="ar1" color="#D55E00" /><Arrow id="ar2" color="#0072B2" /></defs>
      <text x="10" y="45" fontSize="11">virtual state</text>
      <text x="10" y="175" fontSize="11">v = 1</text>
      <text x="10" y="215" fontSize="11">v = 0</text>
      <text x="10" y="195" fontSize="9" fill="#555">spacing = hν_vib</text>
      {cols.map((c, i) => (
        <g key={c.name}>
          <line x1={c.x - 70} x2={c.x + 70} y1={40} y2={40} stroke="#888" strokeDasharray="5 4" />
          <line x1={c.x - 70} x2={c.x + 70} y1={210} y2={210} stroke="#000" strokeWidth="2" />
          <line x1={c.x - 70} x2={c.x + 70} y1={170} y2={170} stroke="#000" strokeWidth="2" />
          <line x1={c.x - 25} x2={c.x - 25} y1={start[i]} y2={44} stroke="#1a7f37" strokeWidth="2" markerEnd="url(#ar0)" />
          <line x1={c.x + 25} x2={c.x + 25} y1={40} y2={c.endY - 4} stroke={c.color} strokeWidth="2" markerEnd={`url(#ar${i})`} />
          <text x={c.x - 30} y={232} fontSize="10" fill="#1a7f37" textAnchor="end">laser in (hν₀)</text>
          <text x={c.x + 30} y={232} fontSize="10" fill={c.color}>scattered out</text>
          <text x={c.x} y={20} fontSize="13" fontWeight="600" textAnchor="middle">{c.name}</text>
          <text x={c.x} y={262} fontSize="10" textAnchor="middle" fill="#333">{c.note}</text>
        </g>
      ))}
      <text x="320" y="284" fontSize="9" textAnchor="middle" fill="#555">Schematic only — level spacing is exaggerated, not to scale, not data.</text>
    </svg>
  )
}

function SchematicSpectrum() {
  const X = (s: number) => 60 + ((s + 1500) / 3000) * 540
  const ticks = [-1500, -1000, -500, 0, 500, 1000, 1500]
  return (
    <svg viewBox="0 0 640 270" width="100%" role="img" aria-label="Schematic spectrum showing anti-Stokes, Rayleigh and Stokes bands against Raman shift">
      <line x1="60" x2="610" y1="200" y2="200" stroke="#000" />
      <line x1="60" x2="60" y1="20" y2="200" stroke="#000" />
      {ticks.map(t => (
        <g key={t}><line x1={X(t)} x2={X(t)} y1="200" y2="206" stroke="#000" /><text x={X(t)} y="220" fontSize="10" textAnchor="middle">{t}</text></g>
      ))}
      <text x="335" y="245" fontSize="12" textAnchor="middle">Raman shift (cm⁻¹) = 1/λ₀ − 1/λ_scattered   (negative: anti-Stokes · positive: Stokes)</text>
      <text transform="translate(16 110) rotate(-90)" fontSize="12" textAnchor="middle">Intensity (arbitrary, illustrative)</text>
      <line x1={X(0)} x2={X(0)} y1="200" y2="30" stroke="#444" strokeWidth="3" />
      <text x={X(0)} y="22" fontSize="11" textAnchor="middle">Rayleigh, 0 cm⁻¹ (off scale)</text>
      <line x1={X(1000)} x2={X(1000)} y1="200" y2="110" stroke="#D55E00" strokeWidth="3" />
      <text x={X(1000)} y="102" fontSize="11" textAnchor="middle" fill="#D55E00">Stokes band, +ν̃ₖ</text>
      <line x1={X(-1000)} x2={X(-1000)} y1="200" y2="186" stroke="#0072B2" strokeWidth="3" />
      <text x={X(-1000)} y="176" fontSize="11" textAnchor="middle" fill="#0072B2">anti-Stokes, −ν̃ₖ (weaker)</text>
      <text x="335" y="266" fontSize="9" textAnchor="middle" fill="#555">Schematic only — positions and heights are illustrative, not measured or computed.</text>
    </svg>
  )
}

export function RamanBasics() {
  const f = 'rounded bg-slate-100 px-2 py-1 font-mono text-xs'
  return (
    <section className="space-y-4 rounded bg-white p-4 text-sm shadow-sm" aria-label="Raman scattering basics">
      <h2 className="text-xl font-semibold">Raman scattering basics</h2>

      <h3 className="font-semibold">Rayleigh, Stokes and anti-Stokes</h3>
      <p>
        When laser photons hit a molecule, almost all are scattered <b>elastically</b> (Rayleigh scattering): the photon changes direction but not energy. A very small
        fraction is scattered <b>inelastically</b> (Raman scattering) and exchanges one vibrational quantum, hν_vib, with the molecule.
      </p>
      <ul className="list-disc pl-5">
        <li><b>Stokes (photon “downshift”):</b> the molecule starts in a low vibrational level and ends one level higher. The scattered photon has <i>less</i> energy, a <i>longer</i> wavelength, and a <b>positive</b> Raman shift.</li>
        <li><b>Anti-Stokes (photon “upshift”):</b> the molecule starts already vibrating (excited level) and ends one level lower. The scattered photon has <i>more</i> energy, a <i>shorter</i> wavelength, and a <b>negative</b> shift in the convention used here.</li>
        <li>Anti-Stokes is weaker at ordinary temperatures because few molecules occupy the excited level (Boltzmann population). Most instruments and the bundled reference library cover the Stokes side only (about 600–3000 cm⁻¹).</li>
      </ul>
      <EnergyLevels />
      <p className="text-xs text-slate-600">The “virtual state” is not a real energy level of the molecule; it only represents the short-lived distortion of the electron cloud while the photon interacts.</p>
      <SchematicSpectrum />

      <h3 className="font-semibold">Raman shift and excitation wavelength</h3>
      <p>Raman shift is the <b>energy difference</b> between laser and scattered light, expressed as a difference of wavenumbers (1/wavelength). With wavelengths in nm and 1 cm = 10⁷ nm:</p>
      <p className={f}>wavenumber (cm⁻¹) = 10⁷ / λ (nm)</p>
      <p className={f}>Raman shift (cm⁻¹) = 10⁷ / λ₀ (nm) − 10⁷ / λ_scattered (nm)</p>
      <p className={f}>λ_scattered (nm) = 10⁷ / (10⁷ / λ₀ (nm) − Raman shift (cm⁻¹))</p>
      <p>
        Worked example (arithmetic only): a 532 nm laser is 10⁷/532 ≈ 18 797 cm⁻¹. A Stokes band at +1000 cm⁻¹ is scattered at 10⁷/(18 797 − 1000) ≈ 561.9 nm; its anti-Stokes
        counterpart at −1000 cm⁻¹ is at 10⁷/(18 797 + 1000) ≈ 505.1 nm. The same vibration has the same shift for any laser, but a different scattered wavelength.
        Fluorescence, detector response and resonance enhancement do depend on the excitation wavelength, so a spectrum cannot be “recoloured” to another laser.
      </p>
      <p>Approximate anti-Stokes to Stokes intensity ratio for one mode, assuming thermal equilibrium, equal detector response and no resonance:</p>
      <p className={f}>I_AS / I_S = [(ν̃₀ + ν̃ₖ) / (ν̃₀ − ν̃ₖ)]⁴ · exp(−h c ν̃ₖ / (k_B T)) &nbsp; with h c / k_B ≈ 1.4388 cm·K</p>

      <h3 className="font-semibold">Rayleigh scattering intensity (not Raman intensity)</h3>
      <p>For a single small, non-absorbing dielectric sphere and unpolarised light:</p>
      <p className={f}>I = I₀ · (1 + cos²θ) / (2R²) · (2π/λ)⁴ · [(n² − 1)/(n² + 2)]² · (d/2)⁶</p>
      <ul className="list-disc pl-5">
        <li><b>I₀</b> incident irradiance; <b>I</b> scattered intensity at distance <b>R</b> and scattering angle <b>θ</b> (0 = forward).</li>
        <li><b>λ</b> wavelength in the medium; <b>d</b> particle diameter; <b>n</b> refractive index of the particle relative to the medium. Use one length unit for λ, d and R.</li>
        <li>Assumptions: d much smaller than λ, no absorption, single scattering, particle small enough to be a point dipole. Intensity ∝ λ⁻⁴ and ∝ d⁶, which is why shorter wavelengths scatter more.</li>
        <li>This is <b>elastic</b> scattering at the laser wavelength. It is not the Raman signal. Raman band intensity depends on the vibration’s polarisability derivative and scales as I₀ · (ν̃₀ − ν̃ₖ)⁴ · (∂α/∂Q)², and is many orders of magnitude weaker. RamanReach models neither intensity; it analyses band positions and shapes in supplied spectra, and it does not check that Rayleigh light was filtered out.</li>
      </ul>
    </section>
  )
}
