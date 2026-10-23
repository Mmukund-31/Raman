/**
 * Physical layout of the CubeRaman back-scattering spectrometer, as built (github.com/jacobbusshart/CubeRaman).
 *
 * The cube sits flat on the bench and the whole optical path is horizontal, at the height of the cube centre:
 *   +x face  laser insert (laser module + 532 nm bandpass)       −x face  beam-dump insert (opposite the laser)
 *   +z face  sample insert (20× objective → vial on a stage)     −z face  filter & focus insert → spectrometer
 *   lid      mirror insert: the 550 nm dichroic hangs from it at 45°
 * Scene units are 1 = 10 mm. Optical spacings follow the published parts (f = 19 mm achromat, 2.4 mm working distance,
 * Ø1" dichroic, Ø12 mm laser); the housing and spectrometer proportions are illustrative.
 */
export type Vec3 = [number, number, number]
export type ModuleId = 'laser' | 'mirror' | 'lid' | 'sample' | 'stage' | 'dump' | 'filter' | 'spectrometer'
export type BeamId = 'excitation' | 'raman' | 'rayleigh' | 'leak' | 'dispersed'
export type StepId = 'laser' | 'mirror' | 'sample' | 'return' | 'rejection' | 'focus' | 'spectrometer' | 'data'

/** Half the cube edge (50 mm cube). The bench is at y = −HALF. */
export const HALF = 2.5
export const BENCH_Y = -HALF

/** Positions along the optical axes (scene units). */
export const OPTICS = {
  laserFront: 2.9, // laser module emitting face, on +x
  laserBack: 6.2,
  bandpassX: 2.15,
  dumpX: -3.3, // absorbing cone tip of the beam dump, on −x
  objectiveBack: 2.7,
  objectiveNose: 5.0,
  workingDistance: 0.24, // 2.4 mm
  longpassZ: -2.15,
  lensZ: -3.9,
  focalLength: 1.9, // AC127-019-A, f = 19 mm
  objectiveAperture: 0.32, // radius of the collimated beam between objective and lens
}
export const FOCUS_Z = OPTICS.objectiveNose + OPTICS.workingDistance
export const SLIT_Z = OPTICS.lensZ - OPTICS.focalLength

/** The dichroic at the cube centre, rotated 45° about the vertical axis. Its normal bisects −laser and the objective. */
export const DICHROIC_NORMAL: Vec3 = [Math.SQRT1_2, 0, Math.SQRT1_2]

export function reflect(d: Vec3, n: Vec3): Vec3 {
  const k = 2 * (d[0] * n[0] + d[1] * n[1] + d[2] * n[2])
  return [d[0] - k * n[0], d[1] - k * n[1], d[2] - k * n[2]]
}

/** Spectrometer box (world coordinates) and a simplified Czerny–Turner layout inside it, in the optical plane (y = 0). */
export const SPECTROMETER = {
  min: [-1.4, BENCH_Y, SLIT_Z - 7.6] as Vec3,
  max: [5.4, 1.5, SLIT_Z] as Vec3,
  slit: [0, 0, SLIT_Z - 0.15] as Vec3,
  collimator: [-0.6, 0, SLIT_Z - 6.8] as Vec3,
  grating: [2.0, 0, SLIT_Z - 3.8] as Vec3,
  focuser: [4.2, 0, SLIT_Z - 6.8] as Vec3,
  detector: [4.2, 0, SLIT_Z - 0.8] as Vec3,
  detectorWidth: 1.8,
}

/** Stokes Raman shift (cm⁻¹) → scattered wavelength (nm). */
export const scatteredNm = (excitationNm: number, shiftCm1: number) => 1e7 / (1e7 / excitationNm - shiftCm1)

/** Approximate sRGB colour of visible light, for drawing the dispersed spectrum. */
export function wavelengthColour(nm: number): string {
  const stops: [number, number, number, number][] = [[450, 40, 80, 255], [495, 0, 200, 255], [530, 40, 220, 60], [570, 235, 230, 0], [600, 255, 150, 0], [650, 255, 20, 0]]
  const c = Math.min(Math.max(nm, stops[0][0]), stops[stops.length - 1][0])
  const k = stops.findIndex(s => s[0] >= c)
  const [a, b] = k <= 0 ? [stops[0], stops[0]] : [stops[k - 1], stops[k]]
  const f = b[0] === a[0] ? 0 : (c - a[0]) / (b[0] - a[0])
  const hex = (i: 1 | 2 | 3) => Math.round(a[i] + (b[i] - a[i]) * f).toString(16).padStart(2, '0')
  return `#${hex(1)}${hex(2)}${hex(3)}`
}

/** Wavelengths drawn as the dispersed fan: the fingerprint window 600–3000 cm⁻¹ seen from 532 nm. */
export const DISPERSED_NM = [600, 1200, 1800, 2400, 3000].map(s => scatteredNm(532, s))

export interface Beam { id: BeamId; label: string; colour: string; points: Vec3[]; photons: number; speed: number }

const C0: Vec3 = [0, 0, 0]
export const BEAMS: Beam[] = [
  { id: 'excitation', label: 'Laser · 532 nm', colour: '#16a34a', points: [[OPTICS.laserFront, 0, 0], C0, [0, 0, FOCUS_Z]], photons: 22, speed: 1 },
  { id: 'raman', label: 'Raman signal · 550–633 nm', colour: '#f97316', points: [[0, 0, FOCUS_Z], C0, [0, 0, SLIT_Z]], photons: 14, speed: 0.6 },
  { id: 'rayleigh', label: 'Rayleigh · 532 nm (rejected)', colour: '#22c55e', points: [[0, 0, FOCUS_Z], C0, [0, 0, OPTICS.longpassZ + 0.05]], photons: 6, speed: 0.6 },
  { id: 'leak', label: 'Residual laser → dump', colour: '#22c55e', points: [C0, [OPTICS.dumpX, 0, 0]], photons: 4, speed: 1 },
  { id: 'dispersed', label: 'Dispersed spectrum', colour: '#fb923c', points: [SPECTROMETER.slit, SPECTROMETER.collimator, SPECTROMETER.grating], photons: 8, speed: 0.6 },
]

/** Radius of the Raman light envelope at z: a cone from the focus to the objective, collimated, then focused onto the slit. */
export function ramanRadius(z: number): number {
  const a = OPTICS.objectiveAperture
  if (z >= OPTICS.objectiveBack) return a * Math.max(0, FOCUS_Z - z) / (FOCUS_Z - OPTICS.objectiveBack)
  if (z >= OPTICS.lensZ) return a
  return Math.max(0.015, a * (z - SLIT_Z) / (OPTICS.lensZ - SLIT_Z))
}

export interface ModuleInfo { id: ModuleId; name: string; anchor: Vec3; explode: Vec3; step: StepId; spec: string }

export const MODULES: ModuleInfo[] = [
  { id: 'laser', name: 'Laser insert', anchor: [4.6, 1.0, 0], explode: [3.5, 0, 0], step: 'laser', spec: '532 nm · ~30 mW · Ø12 mm · Class 3B' },
  { id: 'mirror', name: 'Dichroic mirror', anchor: [0, 1.6, 0], explode: [0, 2.6, 0], step: 'mirror', spec: 'DMLP550 · Ø1″ · 45°' },
  { id: 'lid', name: 'Cube lid', anchor: [0, 2.9, 0], explode: [0, 4.6, 0], step: 'mirror', spec: 'Holds the kinematic mirror mount' },
  { id: 'sample', name: '20× objective', anchor: [0, 1.25, 3.9], explode: [0, 0, 2.2], step: 'sample', spec: 'Infinity-corrected · WD 2.4 mm' },
  { id: 'stage', name: 'Sample stage', anchor: [0, 1.9, 5.7], explode: [0, 0, 4.2], step: 'sample', spec: 'Vial on a micrometer focus stage' },
  { id: 'dump', name: 'Beam dump', anchor: [-3.5, 1.2, 0], explode: [-3.5, 0, 0], step: 'rejection', spec: 'Absorbing cone, threaded body' },
  { id: 'filter', name: 'Filter & focus tube', anchor: [0, 1.1, -4.3], explode: [0, 0, -2.2], step: 'focus', spec: 'FELH0550 + f = 19 mm achromat + SMA905' },
  { id: 'spectrometer', name: 'Spectrometer', anchor: [2.0, 2.0, -9.5], explode: [0, 0, -4.6], step: 'spectrometer', spec: 'BTC100-2S · 100 µm slit · 450–650 nm' },
]

export interface Step {
  id: StepId; n: number; title: string; lede: string; body: string
  camera: Vec3; target: Vec3
  modules: ModuleId[]; beams: BeamId[]; inside: boolean
}

const ALL_BEAMS: BeamId[] = ['excitation', 'raman', 'rayleigh', 'leak', 'dispersed']

export const STEPS: Step[] = [
  {
    id: 'laser', n: 1, title: 'Laser and clean-up filter', camera: [12.5, 6.3, 10.5], target: [2.8, 0, 0], modules: ['laser'], beams: ['excitation'], inside: true,
    lede: 'A 532 nm green laser module enters through one side of the cube.',
    body: 'The cheap diode-pumped module leaks some infrared and its line is not perfectly narrow, so a 532 nm bandpass filter (10 nm wide) cleans the beam right inside the laser insert. A kinematic mount lets you tilt the laser to align it. It runs at about 2.7–3.0 V, below its 3.7 V rating, for a cleaner and cooler beam.',
  },
  {
    id: 'mirror', n: 2, title: 'Dichroic mirror', camera: [7.6, 9.2, 9.6], target: [0, 0.3, 0], modules: ['mirror', 'lid'], beams: ['excitation'], inside: true,
    lede: 'A 45° dichroic mirror hanging from the lid turns the laser 90° toward the sample.',
    body: 'The DMLP550 reflects light shorter than 550 nm and transmits longer wavelengths. The green laser is reflected into the objective. The Raman light coming back from the sample is red-shifted, so it passes straight through the same mirror. Its kinematic mount in the lid is how the beam is steered during alignment.',
  },
  {
    id: 'sample', n: 3, title: 'Objective and sample', camera: [10, 4.8, 13.2], target: [0, -0.5, 4.8], modules: ['sample', 'stage'], beams: ['excitation'], inside: true,
    lede: 'A 20× objective focuses the beam into a tiny spot inside the sample.',
    body: 'The sample, here a liquid in a glass vial, sits about 2.4 mm in front of the objective on a micrometer stage. Turning the micrometer moves the focus into the sample to maximise the signal. Solids, powders and liquids in vials can all be measured.',
  },
  {
    id: 'return', n: 4, title: 'Back-scattered light', camera: [11, 6.8, 7.6], target: [0, 0, 1.8], modules: ['sample', 'mirror'], beams: ['raman', 'rayleigh'], inside: true,
    lede: 'The same objective collects the light scattered straight back.',
    body: 'Almost every photon scatters elastically and stays at 532 nm (Rayleigh). About one in ten million gives a little energy to a molecular vibration and returns at a longer wavelength. That small, molecule-specific shift is the Raman signal. The collected light leaves the objective as a parallel beam and heads back through the dichroic.',
  },
  {
    id: 'rejection', n: 5, title: 'Rejecting the laser', camera: [-9, 7.8, 9.4], target: [-1.2, 0, -0.8], modules: ['dump', 'filter'], beams: ['rayleigh', 'leak', 'raman'], inside: true,
    lede: 'Two filter stages and a beam dump remove the overwhelming 532 nm light.',
    body: 'Rayleigh light is millions of times brighter than the Raman light. The dichroic reflects most of it away, and a FELH0550 longpass filter (550 nm cut-on) blocks what is left. The small fraction of laser light that leaks through the mirror ends up in the beam dump opposite the laser, where a cone in a threaded tube absorbs it so it cannot bounce back as stray light.',
  },
  {
    id: 'focus', n: 6, title: 'Focusing onto the slit', camera: [9.6, 5.6, -1.0], target: [0, 0, -4.2], modules: ['filter'], beams: ['raman'], inside: true,
    lede: 'An f = 19 mm achromatic lens focuses the Raman light onto the spectrometer slit.',
    body: 'Because the objective is infinity-corrected, the light between objective and lens is parallel, so the filters can sit anywhere in that space. The achromat works as the tube lens and its threaded SM05 tube sets the focus. An SMA905 adapter attaches the whole insert directly to the spectrometer input.',
  },
  {
    id: 'spectrometer', n: 7, title: 'Dispersion and detection', camera: [10.5, 14, -4], target: [2, -0.4, -9.4], modules: ['spectrometer'], beams: ['raman', 'dispersed'], inside: true,
    lede: 'Inside the spectrometer a grating spreads the light by wavelength onto a detector.',
    body: 'The 100 µm entrance slit sets the resolution. A concave mirror makes the light parallel, a diffraction grating sends each wavelength off at a slightly different angle, and a second mirror focuses that rainbow onto a linear CCD. Each pixel then corresponds to one wavelength in the 450–650 nm range.',
  },
  {
    id: 'data', n: 8, title: 'From counts to a report', camera: [17, 11.5, 18], target: [1.2, -0.6, -1.2], modules: [], beams: ALL_BEAMS, inside: false,
    lede: 'The spectrometer sends counts per pixel over USB. RamanReach turns them into a report.',
    body: 'Software converts each pixel from wavelength to Raman shift relative to 532 nm and saves the spectrum. Upload that file to RamanReach and it validates it, removes the fluorescence baseline, finds the peaks, compares them with a reference library, and assembles the report.',
  },
]

export const OVERVIEW = { camera: [17, 11.5, 18] as Vec3, target: [1.2, -0.6, -1.2] as Vec3 }
export const EXPLODED = { camera: [23, 16, 24] as Vec3, target: [1.0, 0.4, -1.6] as Vec3 }

/** RamanReach's analysis, in the order the backend orchestrator runs it. */
export const REPORT_FLOW: { title: string; body: string }[] = [
  { title: 'Measure', body: 'CubeRaman records a spectrum, and the acquisition software exports Raman shift and intensity.' },
  { title: 'Upload and validate', body: 'Upload a CSV with raman_shift_cm1 (or wavelength_nm plus the excitation) and intensity. RamanReach checks the columns, range and sampling.' },
  { title: 'Clean the spectrum', body: 'Asymmetric least-squares baseline removal, Savitzky–Golay smoothing and vector normalisation.' },
  { title: 'Find and match peaks', body: 'Bands are located, then the spectrum is compared with reference spectra by cosine similarity and peak agreement.' },
  { title: 'Check robustness', body: 'Experimental conditions are reviewed, and matches are re-tested under small wavenumber shifts. PCA runs when you upload three or more spectra.' },
  { title: 'Report', body: 'One report with the processed spectrum, ranked matches, quality metrics and each analysis it could, or could not, perform.' },
]

export const SPECS: [string, string][] = [
  ['Configuration', 'Back-scattering (180°)'],
  ['Excitation', '532 nm, ~30 mW, Class 3B'],
  ['Laser clean-up', '532 nm bandpass, 10 nm FWHM'],
  ['Beamsplitter', 'DMLP550 longpass dichroic, 45°'],
  ['Objective', '20× infinity-corrected, WD 2.4 mm'],
  ['Rayleigh rejection', 'FELH0550 longpass, 550 nm'],
  ['Tube lens', 'AC127-019-A achromat, f = 19 mm'],
  ['Spectrometer', 'B&W Tek BTC100-2S, 100 µm slit'],
  ['Measurable range', '≈ 600–3000 cm⁻¹'],
  ['Housing', '3D-printed PETG-CF cube with inserts'],
]
