import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { BEAMS, CUBE, OVERVIEW, PARTS, STEPS, type Part, type StepId, type Vec3 } from './model'
import { webglAvailable } from './webgl'

const ACCENT = new THREE.Color('#3b6ef5')
const OVERVIEW_LABELS = new Set(['laser', 'dichroic', 'objective', 'sample', 'dump', 'spectrometer'])
const v = (p: Vec3) => new THREE.Vector3(...p)
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)

function material(kind: Part['material']): THREE.MeshStandardMaterial {
  switch (kind) {
    case 'body': return new THREE.MeshStandardMaterial({ color: '#273244', roughness: 0.75, metalness: 0.05 })
    case 'metal': return new THREE.MeshStandardMaterial({ color: '#cfd6df', roughness: 0.32, metalness: 0.85 })
    case 'dump': return new THREE.MeshStandardMaterial({ color: '#111827', roughness: 0.95 })
    case 'sample': return new THREE.MeshStandardMaterial({ color: '#e7ebf0', roughness: 0.5 })
    case 'mirror': return new THREE.MeshPhysicalMaterial({ color: '#c7d2fe', roughness: 0.08, metalness: 0.6, transparent: true, opacity: 0.72 })
    case 'filter': return new THREE.MeshPhysicalMaterial({ color: '#fde68a', roughness: 0.1, transparent: true, opacity: 0.55 })
    case 'glass': return new THREE.MeshPhysicalMaterial({ color: '#dbeafe', roughness: 0.05, transparent: true, opacity: 0.45 })
  }
}

function geometry(p: Part): THREE.BufferGeometry {
  const [a, b, c] = p.size
  switch (p.kind) {
    case 'cylinder': case 'disk': return new THREE.CylinderGeometry(a, a, b, 48)
    case 'lens': return new THREE.SphereGeometry(1, 48, 24).scale(a, b, a)
    case 'plate': case 'box': case 'sample': return new THREE.BoxGeometry(a, b, c)
  }
}

function buildPart(p: Part) {
  const mat = material(p.material)
  if (p.id === 'bandpass') mat.color.set('#86efac')
  const mesh = new THREE.Mesh(geometry(p), mat)
  mesh.castShadow = mesh.receiveShadow = true
  if (p.axis === 'x') mesh.rotation.z = Math.PI / 2
  if (p.kind === 'plate') mesh.rotation.z = -Math.PI / 4 // normal (1, 1, 0)/√2: laser +x is reflected to −y
  const g = new THREE.Group()
  g.add(mesh)
  if (p.id === 'laser') { // emitting aperture
    const ap = new THREE.Mesh(new THREE.CircleGeometry(0.16, 32), new THREE.MeshBasicMaterial({ color: '#22c55e' }))
    ap.position.x = p.size[1] / 2 + 0.001; ap.rotation.y = Math.PI / 2; g.add(ap)
  }
  if (p.id === 'sample') { // a small specimen on the slide
    const s = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.12, 32), new THREE.MeshStandardMaterial({ color: '#f5f5f4', roughness: 0.3 }))
    s.position.y = 0.18; s.castShadow = true; g.add(s)
  }
  if (p.id === 'spectrometer') { // grating hint on the face
    const plate = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 0.6), new THREE.MeshStandardMaterial({ color: '#94a3b8', metalness: 0.6, roughness: 0.25 }))
    plate.position.z = p.size[2] / 2 + 0.002; g.add(plate)
  }
  g.position.set(...p.position)
  return { group: g, mesh, mat }
}

function beamPath(points: Vec3[]) {
  const path = new THREE.CurvePath<THREE.Vector3>()
  for (let i = 0; i < points.length - 1; i++) path.add(new THREE.LineCurve3(v(points[i]), v(points[i + 1])))
  return path
}

export function CubeScene({ step, exploded, onSelect }: { step: StepId | null; exploded: boolean; onSelect: (s: StepId) => void }) {
  const host = useRef<HTMLDivElement>(null)
  const labels = useRef<Record<string, HTMLButtonElement | null>>({})
  const state = useRef({ step, exploded })
  const [failed] = useState(() => !webglAvailable())
  useEffect(() => { state.current = { step, exploded } }, [step, exploded])

  useEffect(() => {
    const el = host.current
    if (!el || failed) return
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 200)
    camera.position.copy(v(OVERVIEW.camera))
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.copy(v(OVERVIEW.target))
    controls.enableDamping = true
    controls.minDistance = 6
    controls.maxDistance = 30
    controls.enablePan = false

    scene.add(new THREE.HemisphereLight('#ffffff', '#cbd5e1', 1.4))
    const sun = new THREE.DirectionalLight('#ffffff', 2.2)
    sun.position.set(6, 14, 8)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    Object.assign(sun.shadow.camera, { left: -10, right: 10, top: 12, bottom: -10 })
    scene.add(sun)
    const fill = new THREE.DirectionalLight('#dbe6fe', 0.8)
    fill.position.set(-8, 4, -6)
    scene.add(fill)
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(60, 60), new THREE.ShadowMaterial({ opacity: 0.08 }))
    ground.rotation.x = -Math.PI / 2
    ground.position.y = -5.6
    ground.receiveShadow = true
    scene.add(ground)

    // the 3D-printed cube: faint shell with crisp edges
    const shell = new THREE.Group()
    const box = new THREE.BoxGeometry(CUBE.half * 2, CUBE.half * 2, CUBE.half * 2)
    shell.add(new THREE.Mesh(box, new THREE.MeshStandardMaterial({ color: '#334155', transparent: true, opacity: 0.07, roughness: 0.9, depthWrite: false })))
    shell.add(new THREE.LineSegments(new THREE.EdgesGeometry(box), new THREE.LineBasicMaterial({ color: '#94a3b8' })))
    scene.add(shell)

    const parts = PARTS.map(p => ({ p, ...buildPart(p) }))
    parts.forEach(x => scene.add(x.group))

    const beams = BEAMS.map(b => {
      const path = beamPath(b.points)
      const len = path.getLength()
      const tubeMat = new THREE.MeshBasicMaterial({ color: b.colour, transparent: true, opacity: b.opacity, depthWrite: false })
      const tube = new THREE.Mesh(new THREE.TubeGeometry(path, 64 * (b.points.length - 1), b.radius, 16, false), tubeMat)
      const dotMat = new THREE.MeshBasicMaterial({ color: b.colour, transparent: true, opacity: 0.95 })
      const dots = new THREE.InstancedMesh(new THREE.SphereGeometry(Math.max(0.05, b.radius * 0.8), 12, 12), dotMat, b.photons)
      scene.add(tube, dots)
      return { b, path, len, tube, tubeMat, dots, dotMat }
    })

    let explode = 0
    let fly: { from: THREE.Vector3; to: THREE.Vector3; tFrom: THREE.Vector3; tTo: THREE.Vector3; t0: number } | null = null
    let lastStep: StepId | null | undefined = undefined
    const m4 = new THREE.Matrix4()
    const tmp = new THREE.Vector3()
    const clock = new THREE.Clock()
    let raf = 0

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight
      renderer.setSize(w, h, false)
      renderer.domElement.style.width = '100%'; renderer.domElement.style.height = '100%'
      camera.aspect = w / Math.max(h, 1)
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    resize()

    const loop = () => {
      raf = requestAnimationFrame(loop)
      const t = clock.getElapsedTime()
      const { step: s, exploded: ex } = state.current

      if (s !== lastStep) { // fly the camera to the selected step
        const dest = s ? STEPS.find(x => x.id === s)! : OVERVIEW
        fly = { from: camera.position.clone(), to: v(dest.camera), tFrom: controls.target.clone(), tTo: v(dest.target), t0: t }
        if (lastStep === undefined || reduced) { camera.position.copy(fly.to); controls.target.copy(fly.tTo); fly = null }
        lastStep = s
      }
      if (fly) {
        const k = Math.min(1, (t - fly.t0) / 1.4)
        camera.position.lerpVectors(fly.from, fly.to, ease(k))
        controls.target.lerpVectors(fly.tFrom, fly.tTo, ease(k))
        if (k >= 1) fly = null
      }

      explode += ((ex ? 1 : 0) - explode) * (reduced ? 1 : 0.08)
      for (const x of parts) {
        x.group.position.set(x.p.position[0] + x.p.explode[0] * explode, x.p.position[1] + x.p.explode[1] * explode, x.p.position[2] + x.p.explode[2] * explode)
        const on = s !== null && x.p.step === s
        x.mat.emissive.copy(ACCENT)
        x.mat.emissiveIntensity += ((on ? 0.45 : 0) - x.mat.emissiveIntensity) * 0.15
      }
      for (const bm of beams) {
        const vis = 1 - explode
        bm.tubeMat.opacity = bm.b.opacity * vis
        bm.dotMat.opacity = 0.95 * vis
        for (let i = 0; i < bm.b.photons; i++) {
          const u = reduced ? i / bm.b.photons : ((i / bm.b.photons) + (t * bm.b.speed * 2.2) / bm.len) % 1
          bm.path.getPointAt(u, tmp)
          m4.makeTranslation(tmp.x, tmp.y, tmp.z)
          bm.dots.setMatrixAt(i, m4)
        }
        bm.dots.instanceMatrix.needsUpdate = true
      }

      controls.update()
      renderer.render(scene, camera)

      const w = el.clientWidth, h = el.clientHeight
      for (const x of parts) {
        const lab = labels.current[x.p.id]
        if (!lab) continue
        x.group.getWorldPosition(tmp)
        tmp.project(camera)
        lab.style.transform = `translate(-50%, -50%) translate(${((tmp.x + 1) / 2) * w}px, ${((1 - tmp.y) / 2) * h - 26}px)`
        lab.style.visibility = tmp.z < 1 ? 'visible' : 'hidden'
      }
    }
    loop()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      scene.traverse(o => {
        const m = o as THREE.Mesh
        m.geometry?.dispose()
        const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : []
        mats.forEach(mm => mm.dispose())
      })
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [failed])

  if (failed) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-slate-500">
        3D view unavailable: this browser does not support WebGL. The step-by-step explanation is still available.
      </div>
    )
  }

  return (
    <div ref={host} className="relative h-full w-full cursor-grab active:cursor-grabbing" aria-label="Interactive 3D model of a back-scattering Raman probe" role="img">
      {PARTS.filter(p => (step ? p.step === step : OVERVIEW_LABELS.has(p.id))).map(p => {
        const on = step === p.step
        return (
          <button key={p.id} ref={e => { labels.current[p.id] = e }} onClick={() => onSelect(p.step)} style={{ visibility: 'hidden' }}
            className={`absolute top-0 left-0 rounded-full border px-2.5 py-1 text-[11px] font-medium whitespace-nowrap shadow-sm backdrop-blur transition-colors ${
              on ? 'z-10 border-accent-500 bg-accent-600 text-white' : 'border-slate-200 bg-white/85 text-slate-700 hover:border-accent-500'}`}>
            {p.name}
          </button>
        )
      })}
    </div>
  )
}
