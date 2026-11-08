import { useEffect, useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { w2t } from './util'
import { useSim } from '../store'
import { fmtClock } from '../format'

// The thermal scout camera, rendered from the scene. Every surface gets a temperature and the
// camera shows it in a white-hot grey scale, like the real FLIR crops the detector judges: the
// building near ambient (walls and floor about 19-21 C by how dark the surface is, metal a little
// colder at 17.5 C), lamps warm, people 34 C, decoys and floor-plan heat sources at their own
// temperature. A material, an object or any ancestor can set `userData.thermalTemp` (C). Light beams, dust
// and decals do not show in long-wave infrared and are hidden. The overlay (ThermalOverlay) adds
// the scale, a crosshair with the spot temperature and REC; CSS adds a slight blur and noise.
export const T_MIN = 16
export const T_MAX = 37
export const PERSON_C = 34
export const DECOY_C = { radiator: 48, engine: 70, 'coffee machine': 62 }

// white hot: colder = darker; a gentle curve keeps the building's small differences readable
export const thermalGray = (t) => Math.pow(Math.min(1, Math.max(0, (t - T_MIN) / (T_MAX - T_MIN))), 0.9)

const mats = new Map()
const ours = new Set()
function thermalMaterial(t) {
  const k = Math.round(t * 4) / 4
  if (!mats.has(k)) {
    const g = thermalGray(k)
    // grey levels as the screen shows them (sRGB), like the real crops: cold surroundings dark,
    // people near white. Mostly emitted, a little shading so shapes read by angle.
    const grey = (v) => new THREE.Color().setRGB(v, v, v, THREE.SRGBColorSpace)
    const m = new THREE.MeshLambertMaterial({ color: grey(g * 0.45), emissive: grey(g * 0.85) })
    mats.set(k, m)
    ours.add(m)
  }
  return mats.get(k)
}

function inherited(o) {
  for (let p = o; p; p = p.parent) if (p.userData?.thermalTemp != null) return p.userData.thermalTemp
  return null
}
export function surfaceTemp(o, m) {
  if (m?.userData?.thermalTemp != null) return m.userData.thermalTemp // a material's own (skin, clothes)
  const own = inherited(o)
  if (own != null) return own
  if (!m) return 19.5
  const e = m.emissive
  if (e && (m.emissiveIntensity ?? 1) > 0.5 && e.r + e.g + e.b > 0.6) return 42 // lamps, screens
  if ((m.metalness ?? 0) >= 0.5) return 17.5
  const c = m.color ?? { r: 0.5, g: 0.5, b: 0.5 }
  return 18.5 + (0.3 * c.r + 0.59 * c.g + 0.11 * c.b) * 2.5
}
const invisibleInIR = (m) => m && m.transparent && (m.blending === THREE.AdditiveBlending || (m.opacity ?? 1) < 0.6)

// Swaps every mesh to its temperature's material while mounted (new meshes every 0.4 s) and
// restores the originals on unmount.
export function ThermalLook() {
  const scene = useThree((s) => s.scene)
  useEffect(() => {
    const touched = new Set()
    const apply = () => {
      scene.traverse((o) => {
        // visible light means nothing to a long-wave camera: headlights, lamps and the sun go dark
        if ((o.isSpotLight || o.isPointLight || o.isDirectionalLight || o.isRectAreaLight) && o.userData.irIntensity == null) {
          o.userData.irIntensity = o.intensity
          o.intensity = 0
          touched.add(o)
          return
        }
        if (o.isSprite || o.isPoints || o.isLine) {
          if (o.visible) { o.userData.irHidden = true; o.visible = false; touched.add(o) }
          return
        }
        if (!o.isMesh) return
        const cur = o.material
        const isOurs = Array.isArray(cur) ? cur.every((m) => ours.has(m)) : ours.has(cur)
        if (isOurs) return
        // first time, or React gave the mesh a new material since: (re)capture and swap
        const first = Array.isArray(cur) ? cur[0] : cur
        if (invisibleInIR(first)) {
          if (o.visible) { o.userData.irHidden = true; o.visible = false; touched.add(o) }
          return
        }
        o.userData.irOrig = cur
        o.userData.irTemp = surfaceTemp(o, first)
        o.material = Array.isArray(cur) ? cur.map((m) => thermalMaterial(surfaceTemp(o, m))) : thermalMaterial(o.userData.irTemp)
        touched.add(o)
      })
    }
    apply()
    const id = setInterval(apply, 400)
    return () => {
      clearInterval(id)
      for (const o of touched) {
        if (o.userData.irOrig) { o.material = o.userData.irOrig; delete o.userData.irOrig; delete o.userData.irTemp }
        if (o.userData.irHidden) { o.visible = true; delete o.userData.irHidden }
        if (o.userData.irIntensity != null) { o.intensity = o.userData.irIntensity; delete o.userData.irIntensity }
      }
    }
  }, [scene])
  return null
}

// Spot temperature under the crosshair, 4 times a second, written straight into the overlay.
export function SpotMeter({ out }) {
  const { scene, camera } = useThree()
  const ray = useMemo(() => new THREE.Raycaster(), [])
  const last = useRef(0)
  useFrame(() => {
    const now = performance.now()
    if (now - last.current < 250 || !out.current) return
    last.current = now
    ray.setFromCamera({ x: 0, y: 0 }, camera)
    ray.far = 40
    const hit = ray.intersectObjects(scene.children, true).find((h) => h.object.visible && h.object.userData.irTemp != null)
    const t = hit ? hit.object.userData.irTemp + (Math.random() - 0.5) * 0.2 : null
    out.current.textContent = t == null ? '-- °C' : `${t.toFixed(1)} °C`
  })
  return null
}

// Floor-plan heat sources (Aziz's `heat_sources`: generator, space heater, hot pipe, server rack,
// dog, laptop, sunlit) at their temperature; drawn only in the thermal view.
export function HeatSources({ fp }) {
  return (fp?.heat_sources ?? []).map((h) => {
    const s = Math.max(0.2, h.size_m ?? 0.6)
    const flat = h.type === 'sunlit' || h.type === 'laptop'
    return (
      <mesh key={h.id} position={w2t(h.x, h.y, flat ? 0.03 : s / 2)} userData={{ thermalTemp: h.temp_c ?? 40 }}>
        {flat ? <boxGeometry args={[s, 0.04, s]} /> : <boxGeometry args={[s, s, s * 0.8]} />}
        <meshStandardMaterial color="#444" />
      </mesh>
    )
  })
}

// Sensor noise: one small random tile, made once
let noiseUrl = null
export function noiseTile() {
  if (noiseUrl || typeof document === 'undefined') return noiseUrl
  const c = document.createElement('canvas')
  c.width = c.height = 96
  const ctx = c.getContext('2d')
  const img = ctx.createImageData(96, 96)
  for (let i = 0; i < img.data.length; i += 4) {
    const v = Math.random() * 255
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v
    img.data[i + 3] = 255
  }
  ctx.putImageData(img, 0, 0)
  noiseUrl = c.toDataURL('image/png')
  return noiseUrl
}

// FLIR-style overlay over the camera picture: palette name, REC with the mission clock, the
// temperature scale, the centre crosshair and its spot reading.
function RecClock() {
  const t = useSim((s) => s.time)
  return <>{fmtClock(t)}</>
}
export function ThermalOverlay({ spot }) {
  return (
    <div className="thermal-hud" aria-hidden>
      <div className="thermal-noise" style={{ backgroundImage: `url(${noiseTile()})` }} />
      <span className="th-mode mono">IR · WHITE HOT</span>
      <span className="th-rec mono"><i />REC <RecClock /></span>
      <div className="th-scale">
        <span className="mono">{T_MAX}°C</span>
        <i />
        <span className="mono">{T_MIN}°C</span>
      </div>
      <div className="th-cross"><i /><b ref={spot} className="mono">-- °C</b></div>
    </div>
  )
}
