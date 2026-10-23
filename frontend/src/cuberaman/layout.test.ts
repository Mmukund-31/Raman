import { describe, expect, it } from 'vitest'
import { BEAMS, DICHROIC_NORMAL, FOCUS_Z, HALF, MODULES, OPTICS, ramanRadius, reflect, scatteredNm, SLIT_Z, SPECTROMETER, STEPS, wavelengthColour } from './layout'

describe('CubeRaman layout', () => {
  it('turns the laser (travelling −x) into the objective (+z) at the 45° dichroic', () => {
    const out = reflect([-1, 0, 0], DICHROIC_NORMAL)
    expect(out[0]).toBeCloseTo(0); expect(out[1]).toBeCloseTo(0); expect(out[2]).toBeCloseTo(1)
  })

  it('keeps the optical path horizontal, at the cube centre', () => {
    for (const b of BEAMS) for (const p of b.points) expect(p[1]).toBe(0)
  })

  it('uses the published optical spacings', () => {
    expect(FOCUS_Z - OPTICS.objectiveNose).toBeCloseTo(0.24) // 2.4 mm working distance
    expect(OPTICS.lensZ - SLIT_Z).toBeCloseTo(1.9) // f = 19 mm achromat focuses on the slit
    expect(SPECTROMETER.max[2]).toBeCloseTo(SLIT_Z) // the slit sits at the spectrometer input
  })

  it('places each insert on its own face and keeps filters inside the cube', () => {
    expect(OPTICS.laserFront).toBeGreaterThan(HALF)
    expect(OPTICS.dumpX).toBeLessThan(-HALF)
    expect(Math.abs(OPTICS.bandpassX)).toBeLessThan(HALF)
    expect(Math.abs(OPTICS.longpassZ)).toBeLessThan(HALF)
  })

  it('collimates Raman light between objective and lens and focuses it at both ends', () => {
    expect(ramanRadius(FOCUS_Z)).toBe(0)
    expect(ramanRadius(0)).toBe(OPTICS.objectiveAperture)
    expect(ramanRadius(SLIT_Z)).toBeLessThan(0.05)
  })

  it('maps the fingerprint window to 550–633 nm, past the 550 nm filters', () => {
    expect(scatteredNm(532, 600)).toBeCloseTo(549.5, 0)
    expect(scatteredNm(532, 3000)).toBeCloseTo(633.0, 0)
    expect(wavelengthColour(532)).toMatch(/^#[0-9a-f]{6}$/)
  })

  it('tour steps reference real modules and modules point at real steps', () => {
    const ids = new Set(MODULES.map(m => m.id))
    for (const s of STEPS) for (const m of s.modules) expect(ids.has(m)).toBe(true)
    const steps = new Set(STEPS.map(s => s.id))
    for (const m of MODULES) expect(steps.has(m.step)).toBe(true)
  })
})
