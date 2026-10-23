/**
 * Geometry and narrative of a CubeRaman-style back-scattering Raman probe.
 *
 * Component choices and specifications follow the public CubeRaman README (github.com/jacobbusshart/CubeRaman).
 * The layout is a simplified, original schematic in arbitrary scene units, not a CAD reproduction.
 */
export type Vec3 = [number, number, number]
export type StepId = 'laser' | 'dichroic' | 'sample' | 'rejection' | 'focus' | 'spectrometer'

export interface Part {
  id: string; name: string; step: StepId; kind: 'cylinder' | 'box' | 'disk' | 'plate' | 'lens' | 'sample'
  position: Vec3; size: Vec3; axis?: 'x' | 'y'; explode: Vec3; material: 'body' | 'metal' | 'glass' | 'filter' | 'mirror' | 'sample' | 'dump'
  spec?: string
}

const C = 2.2 // half-width of the printed cube

export const PARTS: Part[] = [
  { id: 'laser', name: 'Laser module', step: 'laser', kind: 'cylinder', axis: 'x', position: [-5.4, 0, 0], size: [0.55, 2.2, 0], explode: [-2.2, 0, 0], material: 'metal', spec: '532 nm · ~30 mW · Class 3B' },
  { id: 'bandpass', name: 'Laser-line bandpass', step: 'laser', kind: 'disk', axis: 'x', position: [-3.4, 0, 0], size: [0.6, 0.08, 0], explode: [-1.4, 0, 0], material: 'filter', spec: '532 nm CWL · 10 nm FWHM' },
  { id: 'dichroic', name: 'Dichroic mirror', step: 'dichroic', kind: 'plate', position: [0, 0, 0], size: [1.7, 0.06, 1.2], explode: [0, 0, 2.6], material: 'mirror', spec: '550 nm longpass · 45°' },
  { id: 'objective', name: '20× objective', step: 'sample', kind: 'cylinder', axis: 'y', position: [0, -3.4, 0], size: [0.55, 1.8, 0], explode: [0, -1.6, 0], material: 'metal', spec: 'Infinity-corrected · WD ≈ 2.4 mm' },
  { id: 'sample', name: 'Sample', step: 'sample', kind: 'sample', position: [0, -5.25, 0], size: [1.6, 0.25, 1.6], explode: [0, -2.4, 0], material: 'sample', spec: 'Solids, liquids, through vials' },
  { id: 'longpass', name: 'Longpass filter', step: 'rejection', kind: 'disk', axis: 'y', position: [0, 2.9, 0], size: [0.6, 0.08, 0], explode: [0, 1.4, 0], material: 'filter', spec: '550 nm edge · blocks Rayleigh' },
  { id: 'dump', name: 'Beam dump', step: 'rejection', kind: 'box', position: [3.3, 0, 0], size: [0.9, 1.1, 1.1], explode: [2.2, 0, 0], material: 'dump', spec: 'Absorbs residual 532 nm light' },
  { id: 'lens', name: 'Achromatic lens', step: 'focus', kind: 'lens', axis: 'y', position: [0, 3.7, 0], size: [0.6, 0.22, 0], explode: [0, 2.0, 0], material: 'glass', spec: 'f = 19 mm doublet' },
  { id: 'tube', name: 'Lens tube + SMA905', step: 'focus', kind: 'cylinder', axis: 'y', position: [0, 4.6, 0], size: [0.5, 1.6, 0], explode: [0, 2.6, 0], material: 'body', spec: 'Sets the focus on the slit' },
  { id: 'slit', name: 'Entrance slit', step: 'spectrometer', kind: 'box', position: [0, 5.55, 0], size: [0.9, 0.12, 0.9], explode: [0, 3.0, 0], material: 'metal', spec: '100 µm · limits resolution' },
  { id: 'spectrometer', name: 'Spectrometer', step: 'spectrometer', kind: 'box', position: [0, 6.6, 0], size: [3.6, 1.8, 2.0], explode: [0, 3.4, 0], material: 'body', spec: '450–650 nm · 600–3000 cm⁻¹' },
]

export const CUBE = { half: C }

/** Mirror reflection of direction d about a plane with unit normal n. */
export function reflect(d: Vec3, n: Vec3): Vec3 {
  const k = 2 * (d[0] * n[0] + d[1] * n[1] + d[2] * n[2])
  return [d[0] - k * n[0], d[1] - k * n[1], d[2] - k * n[2]]
}

/** The dichroic sits at 45°: its normal bisects the incoming laser (+x) and the objective (−y). */
export const DICHROIC_NORMAL: Vec3 = [Math.SQRT1_2, Math.SQRT1_2, 0]

const laserExit: Vec3 = [-4.3, 0, 0]
const focal: Vec3 = [0, -5.1, 0]
const slit: Vec3 = [0, 5.55, 0]

export interface Beam { id: string; label: string; colour: string; points: Vec3[]; radius: number; opacity: number; photons: number; speed: number }

export const BEAMS: Beam[] = [
  { id: 'excitation', label: 'Excitation · 532 nm', colour: '#22c55e', points: [laserExit, [0, 0, 0], focal], radius: 0.05, opacity: 0.55, photons: 26, speed: 1 },
  { id: 'raman', label: 'Raman signal · > 550 nm', colour: '#f97316', points: [focal, [0, 0, 0], slit], radius: 0.13, opacity: 0.22, photons: 9, speed: 0.55 },
  { id: 'leak', label: 'Residual laser to dump', colour: '#22c55e', points: [[0, 0, 0], [2.9, 0, 0]], radius: 0.025, opacity: 0.25, photons: 4, speed: 1 },
]

export interface Step {
  id: StepId; n: number; title: string; lede: string; body: string; camera: Vec3; target: Vec3
}

export const STEPS: Step[] = [
  {
    id: 'laser', n: 1, title: 'Laser excitation', camera: [-9, 3.5, 9], target: [-3.6, 0, 0],
    lede: 'A green 532 nm laser supplies a single, well-defined wavelength.',
    body: 'Diode-pumped modules leak a little infrared and are not perfectly monochromatic, so a narrow 10 nm bandpass filter cleans the beam before it enters the cube. Running the module slightly below its rated voltage gives a cleaner, cooler beam.',
  },
  {
    id: 'dichroic', n: 2, title: 'Dichroic beamsplitter', camera: [5, 4, 9], target: [0, 0, 0],
    lede: 'A 45° longpass mirror turns the laser 90° toward the sample.',
    body: 'The dichroic reflects light below 550 nm and transmits light above it. The laser is reflected down into the objective, while the slightly longer-wavelength Raman light returning from the sample passes straight through on its way to the detector.',
  },
  {
    id: 'sample', n: 3, title: 'Focus and back-scattering', camera: [6, -3, 8], target: [0, -4.2, 0],
    lede: 'One objective both focuses the laser and collects the scattered light.',
    body: 'A 20× objective concentrates the beam into a small spot on the sample. Almost all light scatters elastically at 532 nm (Rayleigh); roughly one photon in ten million loses energy to a molecular vibration and returns at a longer wavelength. That shift is the chemical fingerprint.',
  },
  {
    id: 'rejection', n: 4, title: 'Rejecting the laser', camera: [8, 2.5, 7], target: [1.2, 1.4, 0],
    lede: 'Two filter stages remove the overwhelming 532 nm light.',
    body: 'Rayleigh light is millions of times stronger than the Raman signal. The dichroic removes most of it, a 550 nm longpass filter removes the rest, and any laser light that leaks straight through the mirror is absorbed by a beam dump so it cannot bounce back as stray light.',
  },
  {
    id: 'focus', n: 5, title: 'Focusing onto the slit', camera: [6, 6, 8], target: [0, 4.2, 0],
    lede: 'An achromatic lens focuses the collected light onto the spectrometer slit.',
    body: 'The lens acts as a tube lens for the infinity-corrected objective. Its position in the threaded lens tube sets the focus, and an SMA905 adapter couples the tube directly to the spectrometer input.',
  },
  {
    id: 'spectrometer', n: 6, title: 'Dispersion and detection', camera: [7, 9, 9], target: [0, 6.2, 0],
    lede: 'Inside the spectrometer, light is spread by wavelength onto a detector.',
    body: 'A 100 µm slit defines the image of the light source and is the main limit on spectral resolution. A diffraction grating disperses the light across a linear detector; each pixel maps to a wavelength, which software converts to Raman shift in cm⁻¹ using the 532 nm excitation.',
  },
]

export const OVERVIEW = { camera: [10, 6, 13] as Vec3, target: [0, 0.6, 0] as Vec3 }

export const SPECS: [string, string][] = [
  ['Configuration', 'Back-scattering (180°)'],
  ['Excitation', '532 nm, ~30 mW, Class 3B'],
  ['Laser clean-up', '532 nm bandpass, 10 nm FWHM'],
  ['Beamsplitter', '550 nm longpass dichroic, 45°'],
  ['Objective', '20× infinity-corrected'],
  ['Rayleigh rejection', '550 nm longpass filter'],
  ['Slit', '100 µm'],
  ['Spectral window', '600–3000 cm⁻¹ (450–650 nm)'],
  ['Housing', '3D-printed PETG-CF, modular inserts'],
  ['Approximate cost', '≈ €750 bill of materials'],
]

/** Raman shift (cm⁻¹) → scattered wavelength (nm) for a given excitation; Stokes side. */
export const scatteredNm = (excitationNm: number, shiftCm1: number) => 1e7 / (1e7 / excitationNm - shiftCm1)

export const PIPELINE: [string, string][] = [
  ['Wavelength to Raman shift', 'Each detector pixel is calibrated to a wavelength, then expressed as a shift from 532 nm.'],
  ['Cosmic-spike removal', 'Single-pixel spikes from cosmic rays are detected and removed.'],
  ['Baseline correction', 'Broad fluorescence background is estimated and subtracted.'],
  ['Smoothing and normalisation', 'Noise is reduced without shifting peaks; intensities are scaled for comparison.'],
  ['Peak detection', 'Bands are located and characterised by position and height.'],
  ['Library matching', 'The spectrum is compared with reference spectra by band shape.'],
]
