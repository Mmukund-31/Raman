import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { webglAvailable } from '../instrument/webgl'
import {
  BEAMS, BENCH_Y, DICHROIC_NORMAL, EXPLODED, DISPERSED_NM, FOCUS_Z, HALF, MODULES, OPTICS, OVERVIEW, ramanRadius, SLIT_Z, SPECTROMETER, STEPS,
  wavelengthColour, type BeamId, type ModuleId, type StepId, type Vec3,
} from './layout'

const ACCENT = new THREE.Color('#3b6ef5')
const v = (p: Vec3) => new THREE.Vector3(...p)
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
const Y = new THREE.Vector3(0, 1, 0)
const Z = new THREE.Vector3(0, 0, 1)

type Owner = ModuleId | 'frame'
type Kind = 'print' | 'plate' | 'metal' | 'steel' | 'brass' | 'black' | 'glass' | 'bandpass' | 'longpass' | 'mirror' | 'liquid' | 'cap' | 'pcb' | 'grating' | 'red'

function makeMaterial(kind: Kind): THREE.MeshStandardMaterial {
  const S = (o: THREE.MeshStandardMaterialParameters) => new THREE.MeshStandardMaterial(o)
  const P = (o: THREE.MeshPhysicalMaterialParameters) => new THREE.MeshPhysicalMaterial({ transparent: true, depthWrite: false, ...o })
  switch (kind) {
    case 'print': return S({ color: '#2a2f38', roughness: 0.82, metalness: 0.05 }) // black PETG-CF
    case 'plate': return S({ color: '#353b46', roughness: 0.78, metalness: 0.05 })
    case 'metal': return S({ color: '#d9dee5', roughness: 0.26, metalness: 0.9 })
    case 'steel': return S({ color: '#7b8492', roughness: 0.35, metalness: 0.8 })
    case 'brass': return S({ color: '#c0893d', roughness: 0.3, metalness: 0.85 })
    case 'black': return S({ color: '#0d0f13', roughness: 0.95 })
    case 'red': return S({ color: '#dc2626', roughness: 0.6 })
    case 'pcb': return S({ color: '#1f4d3a', roughness: 0.7 })
    case 'grating': return S({ color: '#c4b5fd', roughness: 0.15, metalness: 0.9 })
    case 'glass': return P({ color: '#e0f2fe', roughness: 0.05, opacity: 0.35 })
    case 'bandpass': return P({ color: '#4ade80', roughness: 0.1, opacity: 0.6 })
    case 'longpass': return P({ color: '#f59e0b', roughness: 0.1, opacity: 0.6 })
    case 'mirror': return P({ color: '#a5b4fc', roughness: 0.05, metalness: 0.6, opacity: 0.8 })
    case 'liquid': return P({ color: '#bae6fd', roughness: 0.2, opacity: 0.5 })
    case 'cap': return P({ color: '#f1f5f9', roughness: 0.4, opacity: 0.85 })
  }
}

// ---- geometry helpers (all in world coordinates; one scene unit = 10 mm) ----

/** Cylinder along an axis from coordinate a to b with radii rA (at a) and rB (at b); `c` gives the off-axis coordinates. */
function cyl(axis: 'x' | 'y' | 'z', a: number, b: number, rA: number, rB = rA, c: Vec3 = [0, 0, 0], seg = 40, open = false) {
  const lo = Math.min(a, b), hi = Math.max(a, b)
  const g = new THREE.CylinderGeometry(a < b ? rB : rA, a < b ? rA : rB, hi - lo, seg, 1, open)
  if (axis === 'x') g.rotateZ(-Math.PI / 2)
  if (axis === 'z') g.rotateX(Math.PI / 2)
  const m = (lo + hi) / 2
  g.translate(axis === 'x' ? m : c[0], axis === 'y' ? m : c[1], axis === 'z' ? m : c[2])
  return g
}

function box(min: Vec3, max: Vec3) {
  const g = new THREE.BoxGeometry(max[0] - min[0], max[1] - min[1], max[2] - min[2])
  g.translate((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2)
  return g
}

/** Square printed plate in the xy-plane (normal +z), centred, with a central bore and four corner screw holes. */
function plate(size: number, t: number, bore: number, screws = true) {
  const h = size / 2
  const s = new THREE.Shape()
  s.moveTo(-h, -h); s.lineTo(h, -h); s.lineTo(h, h); s.lineTo(-h, h); s.lineTo(-h, -h)
  const hole = (x: number, y: number, r: number) => { const p = new THREE.Path(); p.absarc(x, y, r, 0, Math.PI * 2, true); s.holes.push(p) }
  if (bore) hole(0, 0, bore)
  if (screws) for (const [x, y] of [[1, 1], [-1, 1], [1, -1], [-1, -1]]) hole(x * (h - 0.35), y * (h - 0.35), 0.12)
  const g = new THREE.ExtrudeGeometry(s, { depth: t, bevelEnabled: false, curveSegments: 36 })
  g.translate(0, 0, -t / 2)
  return g
}

/** Orient a +z-normal geometry so its normal points along n, then move it to p. */
function face(g: THREE.BufferGeometry, n: THREE.Vector3, p: Vec3) {
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(Z, n.clone().normalize()))
  g.translate(...p)
  return g
}

/** Flat optic (disc) whose face normal is n, centred at p. */
function disc(r: number, t: number, n: THREE.Vector3, p: Vec3, seg = 48) {
  const g = new THREE.CylinderGeometry(r, r, t, seg)
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(Y, n.clone().normalize()))
  g.translate(...p)
  return g
}

function ring(R: number, tube: number, n: THREE.Vector3, p: Vec3) { return face(new THREE.TorusGeometry(R, tube, 10, 48), n, p) }

function curveTube(points: Vec3[], r: number) { return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(v)), 48, r, 8, false) }

function helix(c: Vec3, r: number, len: number, turns: number, tube: number) {
  const pts: THREE.Vector3[] = []
  for (let i = 0; i <= turns * 24; i++) { const t = i / (turns * 24), a = t * turns * Math.PI * 2; pts.push(new THREE.Vector3(c[0] + r * Math.cos(a), c[1] + r * Math.sin(a), c[2] + t * len)) }
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), turns * 24, tube, 6, false)
}

const bisector = (p: Vec3, a: Vec3, b: Vec3) => v(a).sub(v(p)).normalize().add(v(b).sub(v(p)).normalize()).normalize()

// ---- the instrument ----

interface Mat { m: THREE.MeshStandardMaterial; owner: Owner; shell: boolean; base: number }

function buildInstrument() {
  const groups = new Map<Owner, THREE.Group>()
  const mats: Mat[] = []
  const cache = new Map<string, THREE.MeshStandardMaterial>()
  const group = (o: Owner) => { let g = groups.get(o); if (!g) { g = new THREE.Group(); g.userData.owner = o; groups.set(o, g) } return g }
  /** Add a mesh; `shell` parts fade out in the inside view so the light path can be seen. */
  const add = (o: Owner, g: THREE.BufferGeometry, kind: Kind, shell = false, edges = false) => {
    const key = `${o}:${kind}:${shell}`
    let m = cache.get(key)
    if (!m) { m = makeMaterial(kind); m.emissive.copy(ACCENT); m.emissiveIntensity = 0; cache.set(key, m); mats.push({ m, owner: o, shell, base: m.opacity }) }
    const mesh = new THREE.Mesh(g, m)
    mesh.castShadow = !m.transparent
    mesh.receiveShadow = true
    group(o).add(mesh)
    if (edges) {
      const lm = new THREE.LineBasicMaterial({ color: '#59616e', transparent: true })
      mats.push({ m: lm as unknown as THREE.MeshStandardMaterial, owner: o, shell, base: 1 })
      group(o).add(new THREE.LineSegments(new THREE.EdgesGeometry(g, 30), lm))
    }
    return mesh
  }
  const H = HALF, T = 0.25, PS = 4.6, faceAt = H + T / 2

  // Base cube: printed frame of twelve edge bars plus a closed bottom.
  const b = 0.42, e = H - b / 2
  for (const s1 of [-1, 1]) for (const s2 of [-1, 1]) {
    add('frame', box([-H, s1 * e - b / 2, s2 * e - b / 2], [H, s1 * e + b / 2, s2 * e + b / 2]), 'print', true, true)
    add('frame', box([s1 * e - b / 2, -H, s2 * e - b / 2], [s1 * e + b / 2, H, s2 * e + b / 2]), 'print', true, true)
    add('frame', box([s1 * e - b / 2, s2 * e - b / 2, -H], [s1 * e + b / 2, s2 * e + b / 2, H]), 'print', true, true)
  }
  add('frame', face(plate(PS, T, 0), new THREE.Vector3(0, -1, 0), [0, -faceAt + T, 0]), 'plate', true)

  // Laser insert (+x): side plate, insert tube with the bandpass, kinematic mount, Ø12 mm laser module and its leads.
  add('laser', face(plate(PS, T, 0.75), new THREE.Vector3(1, 0, 0), [faceAt, 0, 0]), 'plate', true, true)
  add('laser', cyl('x', 1.55, H, 0.6, 0.6, [0, 0, 0], 40, true), 'print', true)
  add('laser', disc(0.52, 0.06, new THREE.Vector3(1, 0, 0), [OPTICS.bandpassX, 0, 0]), 'bandpass')
  add('laser', ring(0.56, 0.06, new THREE.Vector3(1, 0, 0), [OPTICS.bandpassX - 0.08, 0, 0]), 'steel')
  add('laser', face(plate(2.2, 0.35, 0.62), new THREE.Vector3(1, 0, 0), [H + T + 0.18, 0, 0]), 'print', false, true)
  add('laser', cyl('x', H + T + 0.35, 3.75, 0.9, 0.8), 'print')
  for (const [y, z] of [[0.8, 0.8], [-0.8, 0.8], [0.8, -0.8]]) add('laser', cyl('x', H + T + 0.35, H + T + 0.5, 0.16, 0.16, [0, y, z], 6), 'steel')
  add('laser', cyl('x', OPTICS.laserFront, OPTICS.laserBack, 0.6), 'metal')
  add('laser', cyl('x', OPTICS.laserBack, OPTICS.laserBack + 0.3, 0.5, 0.42), 'brass')
  add('laser', new THREE.CircleGeometry(0.2, 32).rotateY(-Math.PI / 2).translate(OPTICS.laserFront - 0.01, 0, 0), 'bandpass')
  const lead = (dz: number): Vec3[] => [[OPTICS.laserBack + 0.3, 0, dz], [7.3, -0.1, dz + 0.4], [7.9, -1.6, dz + 1.6], [8.3, BENCH_Y + 0.06, dz + 3.4], [8.6, BENCH_Y + 0.06, dz + 5.5]]
  add('laser', curveTube(lead(0.08), 0.06), 'red')
  add('laser', curveTube(lead(-0.08), 0.06), 'black')

  // Mirror insert: kinematic plate under the lid, a hanger and backplate, and the Ø1" dichroic at 45°.
  const n = v(DICHROIC_NORMAL)
  add('mirror', disc(1.27, 0.08, n, [0, 0, 0]), 'mirror')
  add('mirror', ring(1.3, 0.07, n, [0, 0, 0]), 'steel')
  const back = n.clone().multiplyScalar(-0.22)
  add('mirror', face(plate(2.7, 0.18, 1.05, false), n, [back.x, back.y, back.z]), 'print', false, true)
  add('mirror', box([-0.18, 1.3, -0.18], [0.18, H - 0.3, 0.18]).translate(back.x, 0, back.z), 'print')
  add('mirror', box([-1.1, H - 0.3, -1.1], [1.1, H - 0.05, 1.1]).rotateY(Math.PI / 4), 'print', false, true)

  // Lid: closes the cube, with the X-shaped adjustment slots for the mirror mount.
  add('lid', face(plate(5.0, 0.3, 0), Y, [0, H + 0.15, 0]), 'plate', true, true)
  for (const a of [Math.PI / 4, -Math.PI / 4]) add('lid', box([-1.8, 0, -0.09], [1.8, 0.02, 0.09]).rotateY(a).translate(0, H + 0.3, 0), 'black', true)
  add('lid', cyl('y', H + 0.3, H + 0.42, 0.2, 0.2, [0, 0, 0], 6), 'steel', true)

  // Sample insert (+z): side plate and the 20× infinity-corrected objective.
  add('sample', face(plate(PS, T, 1.15), Z, [0, 0, faceAt]), 'plate', true, true)
  add('sample', cyl('z', OPTICS.objectiveBack - 0.08, 2.9, 1.06), 'steel', true)
  add('sample', cyl('z', 2.9, 4.2, 1.0), 'metal', true)
  add('sample', cyl('z', 3.3, 3.6, 1.03), 'black', true)
  add('sample', cyl('z', 4.2, 4.75, 1.0, 0.6), 'metal', true)
  add('sample', cyl('z', 4.75, OPTICS.objectiveNose, 0.45), 'metal', true)
  add('sample', disc(0.26, 0.02, Z, [0, 0, OPTICS.objectiveNose + 0.005]), 'glass')

  // Sample stage: base, carriage with a vial sleeve, the vial, and a micrometer that pushes the carriage against a spring.
  const vialZ = FOCUS_Z + 0.42, my = -1.78
  add('stage', box([-1.6, BENCH_Y, 4.6], [1.9, BENCH_Y + 0.3, 10.4]), 'print', false, true)
  add('stage', box([-1.1, BENCH_Y + 0.3, 4.9], [1.7, -1.55, 6.8]), 'print', false, true)
  add('stage', cyl('y', -1.55, -0.55, 0.78, 0.78, [0, 0, vialZ]), 'print')
  add('stage', cyl('y', -1.5, 1.25, 0.55, 0.55, [0, 0, vialZ]), 'glass')
  add('stage', cyl('y', -1.45, 0.7, 0.5, 0.5, [0, 0, vialZ]), 'liquid')
  add('stage', cyl('y', 1.25, 1.6, 0.6, 0.6, [0, 0, vialZ]), 'cap')
  add('stage', box([-0.8, BENCH_Y + 0.3, 9.0], [0.8, -0.95, 9.8]), 'print', false, true)
  add('stage', cyl('z', 6.8, 9.0, 0.1, 0.1, [0, my, 0]), 'metal')
  add('stage', cyl('z', 9.8, 11.4, 0.3, 0.3, [0, my, 0]), 'metal')
  add('stage', cyl('z', 11.4, 12.6, 0.42, 0.42, [0, my, 0], 28), 'metal')
  add('stage', cyl('z', 12.6, 13.0, 0.25, 0.25, [0, my, 0]), 'steel')
  add('stage', cyl('z', H + T, 4.9, 0.06, 0.06, [1.4, -1.85, 0]), 'steel')
  add('stage', helix([1.4, -1.85, H + T], 0.18, 4.9 - H - T, 9, 0.03), 'metal')

  // Beam dump (−x): side plate, aperture, threaded body and the absorbing cone.
  add('dump', face(plate(PS, T, 0.75), new THREE.Vector3(-1, 0, 0), [-faceAt, 0, 0]), 'plate', true, true)
  add('dump', face(plate(1.5, 0.1, 0.3, false), new THREE.Vector3(-1, 0, 0), [-2.15, 0, 0]), 'print')
  add('dump', cyl('x', -H - T, -4.6, 0.85, 0.85, [0, 0, 0], 40, true), 'print', true)
  for (let k = 0; k < 9; k++) add('dump', ring(0.87, 0.05, new THREE.Vector3(1, 0, 0), [-H - T - 0.12 - k * 0.2, 0, 0]), 'print', true)
  add('dump', new THREE.ConeGeometry(0.78, 4.6 + OPTICS.dumpX, 40).rotateZ(-Math.PI / 2).translate((OPTICS.dumpX - 4.6) / 2, 0, 0), 'black')
  add('dump', disc(0.85, 0.06, new THREE.Vector3(1, 0, 0), [-4.6, 0, 0]), 'print', true)

  // Filter & focus (−z): longpass filter, SM1 tube, lock ring, SM05 tube with the achromat, SMA905 adapter.
  const nz = new THREE.Vector3(0, 0, -1)
  add('filter', face(plate(PS, T, 0.75), nz, [0, 0, -faceAt]), 'plate', true, true)
  add('filter', disc(0.6, 0.06, Z, [0, 0, OPTICS.longpassZ]), 'longpass')
  add('filter', ring(0.62, 0.06, Z, [0, 0, OPTICS.longpassZ - 0.08]), 'steel')
  add('filter', cyl('z', -H - T, -3.55, 0.85, 0.85, [0, 0, 0], 40, true), 'print', true)
  add('filter', cyl('z', -3.55, -3.75, 0.98, 0.98, [0, 0, 0], 6), 'print', true)
  add('filter', cyl('z', -3.75, -5.25, 0.52, 0.52, [0, 0, 0], 40, true), 'print', true)
  add('filter', new THREE.SphereGeometry(1, 40, 20).scale(0.42, 0.42, 0.12).translate(0, 0, OPTICS.lensZ), 'glass')
  add('filter', cyl('z', -5.25, -5.6, 0.42, 0.42, [0, 0, 0], 6), 'brass', true)
  add('filter', cyl('z', -5.6, SLIT_Z, 0.22), 'metal', true)

  // Spectrometer: printed case with vents, and a simplified Czerny–Turner bench inside it.
  const S = SPECTROMETER
  add('spectrometer', box(S.min, S.max), 'print', true, true)
  for (let k = 0; k < 6; k++) {
    const z = S.max[2] - 1.2 - k * 1.0
    add('spectrometer', box([0.3 + (k % 2) * 0.4, S.max[1], z - 0.1], [3.9 + (k % 2) * 0.4, S.max[1] + 0.02, z + 0.1]), 'black', true)
  }
  add('spectrometer', box([S.min[0] + 0.15, S.min[1] + 0.05, S.min[2] + 0.15], [S.max[0] - 0.15, S.min[1] + 0.15, S.max[2] - 0.15]), 'pcb')
  add('spectrometer', box([-0.38, -0.55, S.slit[2] - 0.03], [0.38, 0.55, S.slit[2] + 0.03]), 'steel')
  add('spectrometer', box([-0.02, -0.35, S.slit[2] - 0.035], [0.02, 0.35, S.slit[2] + 0.035]), 'bandpass')
  add('spectrometer', disc(0.6, 0.1, bisector(S.collimator, S.slit, S.grating), S.collimator), 'metal')
  add('spectrometer', disc(0.72, 0.12, bisector(S.grating, S.collimator, S.focuser), S.grating, 4), 'grating')
  add('spectrometer', disc(0.75, 0.1, bisector(S.focuser, S.grating, S.detector), S.focuser), 'metal')
  const d = S.detector, w = S.detectorWidth
  add('spectrometer', box([d[0] - w / 2, -0.25, d[2]], [d[0] + w / 2, 0.25, d[2] + 0.25]), 'black')
  add('spectrometer', box([d[0] - 0.6, S.min[1] + 0.15, S.max[2] - 3.6], [d[0] + 0.6, S.min[1] + 0.35, S.max[2] - 2.0]), 'black')
  add('spectrometer', box([3.8, -1.75, S.min[2] - 0.25], [4.5, -1.35, S.min[2]]), 'metal')
  add('spectrometer', curveTube([[4.15, -1.55, S.min[2] - 0.25], [4.2, -1.8, S.min[2] - 1.4], [4.6, BENCH_Y + 0.06, S.min[2] - 2.6], [5.6, BENCH_Y + 0.06, S.min[2] - 4.2]], 0.09), 'black')

  return { groups, mats }
}

// ---- light paths ----

interface BeamObj { id: BeamId; objs: THREE.Object3D[]; mats: { m: THREE.Material & { opacity: number }; base: number }[]; anim: (t: number) => void }

function buildBeams(reduced: boolean) {
  const out: BeamObj[] = []
  const tmp = new THREE.Vector3(), m4 = new THREE.Matrix4()
  const basic = (colour: string, opacity: number) => new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity, depthWrite: false })
  const polyline = (pts: Vec3[]) => {
    const p = new THREE.CurvePath<THREE.Vector3>()
    for (let i = 0; i < pts.length - 1; i++) p.add(new THREE.LineCurve3(v(pts[i]), v(pts[i + 1])))
    return p
  }
  /** Photons streaming along a path; `offset` maps (u, point, i) to a displaced point (for the wide Raman cone). */
  const photons = (path: THREE.CurvePath<THREE.Vector3>, count: number, speed: number, colour: string, r: number, offset?: (i: number, p: THREE.Vector3) => void) => {
    const mat = basic(colour, 0.95)
    const mesh = new THREE.InstancedMesh(new THREE.SphereGeometry(r, 10, 10), mat, count)
    const len = path.getLength()
    const anim = (t: number) => {
      for (let i = 0; i < count; i++) {
        const u = reduced ? i / count : ((i / count) + (t * speed * 2.2) / len) % 1
        path.getPointAt(u, tmp)
        offset?.(i, tmp)
        mesh.setMatrixAt(i, m4.makeTranslation(tmp.x, tmp.y, tmp.z))
      }
      mesh.instanceMatrix.needsUpdate = true
    }
    return { mesh, mat, anim }
  }
  for (const b of BEAMS) {
    const path = polyline(b.points)
    const o: BeamObj = { id: b.id, objs: [], mats: [], anim: () => {} }
    const track = (obj: THREE.Mesh | THREE.InstancedMesh, m: THREE.MeshBasicMaterial) => { o.objs.push(obj); o.mats.push({ m, base: m.opacity }) }
    if (b.id === 'raman') {
      // a filled envelope: cone from the focus, collimated through the cube, focused onto the slit
      const prof: THREE.Vector2[] = []
      for (let k = 0; k <= 160; k++) { const z = SLIT_Z + (FOCUS_Z - SLIT_Z) * (k / 160); prof.push(new THREE.Vector2(ramanRadius(z), z)) }
      const env = new THREE.Mesh(new THREE.LatheGeometry(prof, 40).rotateX(Math.PI / 2), basic(b.colour, 0.2))
      track(env, env.material as THREE.MeshBasicMaterial)
      const seeds = Array.from({ length: b.photons }, (_, i) => [((i * 2.399) % (Math.PI * 2)), 0.35 + 0.6 * ((i * 0.618) % 1)])
      const p = photons(path, b.photons, b.speed, b.colour, 0.07, (i, q) => { const r = ramanRadius(q.z) * seeds[i][1]; q.x += r * Math.cos(seeds[i][0]); q.y += r * Math.sin(seeds[i][0]) })
      track(p.mesh, p.mat); o.anim = p.anim
    } else if (b.id === 'dispersed') {
      // slit → collimator → grating as one beam, then a fan of wavelengths → focusing mirror → detector pixels
      const S = SPECTROMETER
      const segs: [Vec3, Vec3, number][] = [[S.slit, S.collimator, 0.05], [S.collimator, S.grating, 0.1]]
      for (const [a, c, r] of segs) { const m = new THREE.Mesh(new THREE.TubeGeometry(polyline([a, c]), 8, r, 12), basic(b.colour, 0.35)); track(m, m.material as THREE.MeshBasicMaterial) }
      const anims = [photons(path, b.photons, b.speed, b.colour, 0.07)]
      DISPERSED_NM.forEach((nm, k) => {
        const u = k / (DISPERSED_NM.length - 1) - 0.5, col = wavelengthColour(nm)
        const f: Vec3 = [S.focuser[0] + u * 0.9, 0, S.focuser[2] + u * 0.25]
        const px: Vec3 = [S.detector[0] + u * (S.detectorWidth - 0.3), 0, S.detector[2] - 0.01]
        const ray = polyline([S.grating, f, px])
        const m = new THREE.Mesh(new THREE.TubeGeometry(ray, 24, 0.03, 8), basic(col, 0.85)); track(m, m.material as THREE.MeshBasicMaterial)
        const pix = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.3, 0.02).translate(...px), basic(col, 1)); track(pix, pix.material as THREE.MeshBasicMaterial)
        anims.push(photons(ray, 2, b.speed, col, 0.06))
      })
      anims.forEach(a => track(a.mesh, a.mat))
      o.anim = t => anims.forEach(a => a.anim(t))
    } else {
      const r = b.id === 'excitation' ? 0.045 : 0.025
      const m = new THREE.Mesh(new THREE.TubeGeometry(path, 64, r, 12), basic(b.colour, b.id === 'excitation' ? 0.75 : 0.3))
      track(m, m.material as THREE.MeshBasicMaterial)
      const p = photons(path, b.photons, b.speed, b.colour, b.id === 'excitation' ? 0.07 : 0.055)
      track(p.mesh, p.mat); o.anim = p.anim
    }
    out.push(o)
  }
  // the bright laser focus in the sample
  const spotMat = basic('#4ade80', 0.95)
  const spot = new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 16), spotMat)
  spot.position.set(0, 0, FOCUS_Z)
  const ex = out.find(o => o.id === 'excitation')!
  ex.objs.push(spot); ex.mats.push({ m: spotMat, base: 0.95 })
  const exAnim = ex.anim
  ex.anim = t => { exAnim(t); spot.scale.setScalar(1 + 0.25 * Math.sin(t * 5)) }
  return out
}

export interface SceneProps { step: StepId | null; exploded: boolean; inside: boolean; onSelect: (s: StepId) => void }

export function CubeRamanScene({ step, exploded, inside, onSelect }: SceneProps) {
  const host = useRef<HTMLDivElement>(null)
  const labels = useRef<Partial<Record<ModuleId, HTMLButtonElement | null>>>({})
  const state = useRef({ step, exploded, inside, onSelect })
  const [failed] = useState(() => !webglAvailable())
  useEffect(() => { state.current = { step, exploded, inside, onSelect } }, [step, exploded, inside, onSelect])

  useEffect(() => {
    const el = host.current
    if (!el || failed) return
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFShadowMap
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 300)
    camera.position.copy(v(OVERVIEW.camera))
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.copy(v(OVERVIEW.target))
    controls.enableDamping = true
    controls.minDistance = 5
    controls.maxDistance = 40
    controls.maxPolarAngle = Math.PI * 0.53
    controls.autoRotateSpeed = 0.5
    let userMoved = false
    controls.addEventListener('start', () => { userMoved = true })

    scene.add(new THREE.HemisphereLight('#ffffff', '#cbd5e1', 1.6))
    const sun = new THREE.DirectionalLight('#ffffff', 2.4)
    sun.position.set(8, 16, 10)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    Object.assign(sun.shadow.camera, { left: -16, right: 16, top: 16, bottom: -16, near: 1, far: 60 })
    sun.shadow.bias = -0.0005
    scene.add(sun)
    const fill = new THREE.DirectionalLight('#dbe6fe', 1.0)
    fill.position.set(-10, 6, -4)
    scene.add(fill)
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(80, 80), new THREE.ShadowMaterial({ opacity: 0.1 }))
    ground.rotation.x = -Math.PI / 2
    ground.position.y = BENCH_Y - 0.005
    ground.receiveShadow = true
    scene.add(ground)

    const { groups, mats } = buildInstrument()
    groups.forEach(g => scene.add(g))
    const beams = buildBeams(reduced)
    beams.forEach(b => b.objs.forEach(o => scene.add(o)))
    const moduleOf = new Map(MODULES.map(m => [m.id, m]))

    // click a part to jump to its step (ignore drags)
    const ray = new THREE.Raycaster(), ndc = new THREE.Vector2()
    let down: [number, number] | null = null
    const onDown = (e: PointerEvent) => { down = [e.clientX, e.clientY] }
    const onUp = (e: PointerEvent) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return
      const r = renderer.domElement.getBoundingClientRect()
      ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
      ray.setFromCamera(ndc, camera)
      for (const hit of ray.intersectObjects([...groups.values()], true)) {
        let o: THREE.Object3D | null = hit.object
        while (o && !o.userData.owner) o = o.parent
        const mod = o ? moduleOf.get(o.userData.owner as ModuleId) : undefined
        if (mod) { state.current.onSelect(mod.step); return }
        if (o?.userData.owner === 'frame') return
      }
    }
    renderer.domElement.addEventListener('pointerdown', onDown)
    renderer.domElement.addEventListener('pointerup', onUp)

    let explode = 0, see = 0
    let fly: { from: THREE.Vector3; to: THREE.Vector3; tFrom: THREE.Vector3; tTo: THREE.Vector3; t0: number } | null = null
    let lastView: string | undefined = undefined
    const tmp = new THREE.Vector3()
    const timer = new THREE.Timer()
    let raf = 0

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight
      renderer.setSize(w, h, false)
      renderer.domElement.style.width = '100%'; renderer.domElement.style.height = '100%'
      camera.aspect = w / Math.max(h, 1)
      // keep the whole instrument in frame on narrow screens
      camera.fov = camera.aspect < 1 ? 32 / Math.max(camera.aspect, 0.55) : 32
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    resize()

    const loop = () => {
      raf = requestAnimationFrame(loop)
      timer.update()
      const t = timer.getElapsed()
      const { step: s, exploded: ex, inside: ins } = state.current
      const cur = s ? STEPS.find(x => x.id === s)! : null

      const view = s ?? (ex ? 'exploded' : 'overview')
      if (view !== lastView) { // fly the camera to the selected step or view
        const dest = cur ?? (ex ? EXPLODED : OVERVIEW)
        fly = { from: camera.position.clone(), to: v(dest.camera), tFrom: controls.target.clone(), tTo: v(dest.target), t0: t }
        if (lastView === undefined || reduced) { camera.position.copy(fly.to); controls.target.copy(fly.tTo); fly = null }
        lastView = view
        userMoved = s !== null
      }
      if (fly) {
        const k = Math.min(1, (t - fly.t0) / 1.6)
        camera.position.lerpVectors(fly.from, fly.to, ease(k))
        controls.target.lerpVectors(fly.tFrom, fly.tTo, ease(k))
        if (k >= 1) fly = null
      }
      controls.autoRotate = !reduced && !fly && !s && !userMoved

      const rate = reduced ? 1 : 0.08
      explode += ((ex ? 1 : 0) - explode) * rate
      see += (((cur ? cur.inside : ins) && !ex ? 1 : 0) - see) * rate
      for (const [o, g] of groups) {
        const ofs = o === 'frame' ? null : moduleOf.get(o)?.explode
        if (ofs) g.position.set(ofs[0] * explode, ofs[1] * explode, ofs[2] * explode)
      }
      for (const x of mats) {
        if (x.shell) {
          const op = x.base * (1 - 0.86 * see)
          x.m.opacity = op
          const tr = op < 0.995 || x.base < 1
          if (x.m.transparent !== tr) { x.m.transparent = tr; x.m.depthWrite = !tr; x.m.needsUpdate = true }
        }
        if (x.m.emissive) {
          const on = cur !== null && x.owner !== 'frame' && cur.modules.includes(x.owner)
          x.m.emissiveIntensity += ((on ? 0.09 + 0.04 * Math.sin(t * 3) : 0) - x.m.emissiveIntensity) * 0.15
        }
      }
      for (const b of beams) {
        const want = (1 - explode) * (cur && !cur.beams.includes(b.id) ? 0.1 : 1)
        b.mats.forEach(x => { x.m.opacity = x.base * want })
        b.objs.forEach(o => { o.visible = want > 0.02 })
        b.anim(t)
      }

      controls.update()
      renderer.render(scene, camera)

      const w = el.clientWidth, h = el.clientHeight
      for (const m of MODULES) {
        const lab = labels.current[m.id]
        if (!lab) continue
        tmp.set(m.anchor[0] + m.explode[0] * explode, m.anchor[1] + m.explode[1] * explode, m.anchor[2] + m.explode[2] * explode).project(camera)
        lab.style.transform = `translate(-50%, -100%) translate(${((tmp.x + 1) / 2) * w}px, ${((1 - tmp.y) / 2) * h}px)`
        lab.style.visibility = tmp.z < 1 && Math.abs(tmp.x) < 1.05 && Math.abs(tmp.y) < 1.05 ? 'visible' : 'hidden'
      }
    }
    loop()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      timer.dispose()
      renderer.domElement.removeEventListener('pointerdown', onDown)
      renderer.domElement.removeEventListener('pointerup', onUp)
      scene.traverse(o => {
        const m = o as THREE.Mesh
        m.geometry?.dispose()
        const ms = Array.isArray(m.material) ? m.material : m.material ? [m.material] : []
        ms.forEach(mm => mm.dispose())
      })
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [failed])

  if (failed) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-slate-500">
        3D view unavailable: this browser does not support WebGL. The step-by-step tour is still available.
      </div>
    )
  }

  const cur = step ? STEPS.find(s => s.id === step) : null
  const shown = MODULES.filter(m => (cur ? cur.modules.includes(m.id) : exploded || m.id !== 'lid'))
  return (
    <div ref={host} className="relative h-full w-full cursor-grab touch-none active:cursor-grabbing" role="img"
      aria-label="Interactive 3D model of the CubeRaman spectrometer: laser, dichroic mirror cube, objective and sample stage, beam dump, filter and focus tube, and spectrometer">
      {shown.map(m => (
        <button key={m.id} ref={e => { labels.current[m.id] = e }} onClick={() => onSelect(m.step)} style={{ visibility: 'hidden' }}
          className={`absolute top-0 left-0 rounded-full border px-2.5 py-1 text-[11px] font-medium whitespace-nowrap shadow-sm backdrop-blur transition-colors ${
            cur ? 'z-10 border-accent-500 bg-accent-600 text-white' : 'border-slate-200 bg-white/90 text-slate-700 hover:border-accent-500 hover:text-accent-700 max-sm:hidden'}`}>
          {m.name}
        </button>
      ))}
    </div>
  )
}
