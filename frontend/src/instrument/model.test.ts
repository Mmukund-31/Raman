import * as THREE from 'three'
import { describe, expect, it } from 'vitest'
import { BEAMS, DICHROIC_NORMAL, PARTS, reflect, scatteredNm, STEPS, type Vec3 } from './model'

const part = (id: string) => PARTS.find(p => p.id === id)!
const near = (a: Vec3, b: Vec3, tol = 1e-9) => a.every((x, i) => Math.abs(x - b[i]) < tol)

describe('optical model', () => {
  it('the 45° dichroic turns the +x laser beam straight down to the objective', () => {
    expect(near(reflect([1, 0, 0], DICHROIC_NORMAL), [0, -1, 0])).toBe(true)
    // the rendered plate (thin along y, rotated −45° about z) has exactly this normal
    const n = new THREE.Vector3(0, 1, 0).applyEuler(new THREE.Euler(0, 0, -Math.PI / 4))
    expect(near([n.x, n.y, n.z], DICHROIC_NORMAL, 1e-12)).toBe(true)
  })

  it('excitation runs laser → bandpass → dichroic → objective → sample', () => {
    const [start, mirror, focus] = BEAMS.find(b => b.id === 'excitation')!.points
    expect(start[0]).toBeGreaterThan(part('laser').position[0])
    expect(start[0]).toBeLessThan(part('bandpass').position[0])
    expect(near(mirror, part('dichroic').position)).toBe(true)
    expect(focus[1]).toBeLessThan(part('objective').position[1])
    expect(focus[1]).toBeGreaterThan(part('sample').position[1])
  })

  it('the Raman signal passes the dichroic, longpass, lens and tube in order and ends at the slit', () => {
    const pts = BEAMS.find(b => b.id === 'raman')!.points
    expect(pts.every(p => p[0] === 0 && p[2] === 0)).toBe(true)
    const ys = ['dichroic', 'longpass', 'lens', 'tube', 'slit'].map(id => part(id).position[1])
    expect([...ys].sort((a, b) => a - b)).toEqual(ys)
    expect(pts.at(-1)![1]).toBe(part('slit').position[1])
  })

  it('residual laser light that leaks through the mirror ends at the beam dump', () => {
    const end = BEAMS.find(b => b.id === 'leak')!.points.at(-1)!
    expect(end[0]).toBeLessThan(part('dump').position[0])
    expect(end[0]).toBeGreaterThan(part('dump').position[0] - part('dump').size[0])
  })

  it('the 600–3000 cm⁻¹ window maps to 549.5–633.0 nm, inside the 450–650 nm spectrometer range', () => {
    expect(scatteredNm(532, 0)).toBeCloseTo(532, 9)
    const lo = scatteredNm(532, 600), hi = scatteredNm(532, 3000)
    expect(lo).toBeCloseTo(549.5, 1)
    expect(hi).toBeCloseTo(633.0, 1)
    expect(lo).toBeGreaterThan(450)
    expect(hi).toBeLessThan(650)
  })

  it('every tour step has components to show', () => {
    for (const s of STEPS) expect(PARTS.some(p => p.step === s.id)).toBe(true)
    expect(STEPS.map(s => s.n)).toEqual([1, 2, 3, 4, 5, 6])
  })
})
