import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { WALL_H, w2t } from './util'
import { materials } from './textures'
import { wallDamage } from './Collapse'
import { LightBeam } from './NightLights'

// The air inside the collapsed building (Reality panes only): dust hanging in every room
// that the lights carve shafts through, a sheared pipe spraying water into a puddle that
// spreads along the wall, a fire smouldering in the rubble of the no-go hazard room, and
// the building's own emergency lights flickering on a dying battery. Visual only: the sim,
// the radio and the robots never see any of it, and nothing here sits where a robot drives
// (floor-flat, hugging a wall, above head height, or inside the hazard zone). Deterministic
// from the floorplan.

function rng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}

const box = (poly) => {
  const xs = poly.map((p) => p[0])
  const ys = poly.map((p) => p[1])
  return [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
}

const THICK = { concrete: 0.3, brick: 0.2, drywall: 0.12, metal: 0.06 }

// Closest point on segment a-b to p (sim coords).
function segDist(p, a, b) {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)))
  const q = [a[0] + dx * t, a[1] + dy * t]
  return { d: Math.hypot(p[0] - q[0], p[1] - q[1]), q }
}

// --------------------------------------------------------------- lit haze
// Hundreds of faint billboards in one draw call. Dust scatters light from every direction,
// so instead of a normal the fragment sums the irradiance of every light in the scene
// (three's own light uniforms: headlights, the flood, the fire, the strobes all count).
// Drift (and, for smoke, the rising loop) runs in the vertex shader: no per-frame CPU work.
const HAZE_VERT = /* glsl */`
uniform float uTime;
uniform float uRise;      // > 0: smoke mode, puffs climb this far, spread, thin out and loop
attribute vec4 aSeed;     // phase, drift amplitude, screen rotation, opacity
varying vec2 vUv;
varying float vAlpha;
varying float vSeed;
varying float vWorldY;
varying vec3 vViewPos;
#include <fog_pars_vertex>
void main() {
  vUv = uv;
  vSeed = aSeed.x;
  vec3 center = (instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
  float size = length(instanceMatrix[0].xyz);
  float alpha = aSeed.w;
  // lazy drift: nothing moves fast in still air
  float t = uTime * 0.06 + aSeed.x;
  center.x += sin(t) * aSeed.y;
  center.z += cos(t * 0.73 + 1.9) * aSeed.y;
  center.y += sin(t * 1.31) * 0.08;
  if (uRise > 0.0) {
    float k = fract(uTime * 0.11 + aSeed.x * 0.159);
    center.y += k * uRise;
    center.x += k * k * aSeed.y * 2.0;
    size *= 0.55 + k * 1.7;
    alpha *= sin(3.14159 * k) * (1.0 - 0.5 * k);
  }
  vec4 mvPosition = modelViewMatrix * vec4(center, 1.0);
  // billboard in view space, a little flattened so it reads as a layer of haze, not a ball
  float c = cos(aSeed.z);
  float s = sin(aSeed.z);
  vec2 p = vec2(position.x, position.y * 0.62) * size;
  p = vec2(p.x * c - p.y * s, p.x * s + p.y * c);
  mvPosition.xy += p;
  // world height of this corner, to fade at the floor and above the wall tops
  vec3 upV = (viewMatrix * vec4(0.0, 1.0, 0.0, 0.0)).xyz;
  vWorldY = (modelMatrix * vec4(center, 1.0)).y + p.x * upV.x + p.y * upV.y;
  vViewPos = mvPosition.xyz;
  vAlpha = alpha;
  gl_Position = projectionMatrix * mvPosition;
  #include <fog_vertex>
}
`

const HAZE_FRAG = /* glsl */`
#include <common>
#include <lights_pars_begin>
#include <fog_pars_fragment>
uniform vec3 uColor;
uniform float uOpacity;
uniform float uTopFade;   // 1: gone above the wall tops (haze), 0: free to rise (smoke)
uniform float uWallH;
varying vec2 vUv;
varying float vAlpha;
varying float vSeed;
varying float vWorldY;
varying vec3 vViewPos;
void main() {
  // gaussian puff with no visible rim, so overlapping puffs merge into one haze, and a
  // little internal structure so a big one lit by a headlight is not a perfect disc
  vec2 q = (vUv - 0.5) * 2.0;
  float r2 = dot(q, q);
  float a = exp(-r2 * 3.5) * (1.0 - smoothstep(0.55, 1.0, r2)) * vAlpha * uOpacity;
  a *= 0.78 + 0.22 * sin(q.x * 5.0 + vSeed * 7.0) * sin(q.y * 4.0 + vSeed * 3.0);
  a *= smoothstep(0.0, 0.5, vWorldY);
  a *= mix(1.0, 1.0 - smoothstep(uWallH - 0.2, uWallH + 0.7, vWorldY), uTopFade);
  a *= smoothstep(0.6, 3.5, -vViewPos.z);   // never a wall of fog on the lens
  if (a < 0.002) discard;
  vec3 irr = ambientLightColor;
  #if NUM_HEMI_LIGHTS > 0
  for (int i = 0; i < NUM_HEMI_LIGHTS; i++) {
    irr += mix(hemisphereLights[i].groundColor, hemisphereLights[i].skyColor, 0.7);
  }
  #endif
  #if NUM_DIR_LIGHTS > 0
  for (int i = 0; i < NUM_DIR_LIGHTS; i++) {
    irr += directionalLights[i].color * 0.45;
  }
  #endif
  #if NUM_POINT_LIGHTS > 0
  for (int i = 0; i < NUM_POINT_LIGHTS; i++) {
    vec3 lv = pointLights[i].position - vViewPos;
    float d = length(lv);
    irr += pointLights[i].color * getDistanceAttenuation(d, pointLights[i].distance, pointLights[i].decay);
  }
  #endif
  #if NUM_SPOT_LIGHTS > 0
  for (int i = 0; i < NUM_SPOT_LIGHTS; i++) {
    vec3 lv = spotLights[i].position - vViewPos;
    float d = length(lv);
    float ang = dot(lv / max(d, 0.001), spotLights[i].direction);
    irr += spotLights[i].color * getSpotAttenuation(spotLights[i].coneCos, spotLights[i].penumbraCos, ang)
         * getDistanceAttenuation(d, spotLights[i].distance, spotLights[i].decay);
  }
  #endif
  vec3 lit = uColor * irr * RECIPROCAL_PI;
  lit /= 1.0 + 0.6 * lit;   // soft shoulder: a puff in a headlight glows, never a white disc
  gl_FragColor = vec4(lit, a);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
  #include <fog_fragment>
}
`

function hazeMaterial({ color, opacity, rise = 0, topFade = 1 }) {
  const m = new THREE.ShaderMaterial({
    uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.lights, THREE.UniformsLib.fog, {
      uTime: { value: 0 }, uColor: { value: new THREE.Color(color) },
      uOpacity: { value: opacity }, uRise: { value: rise }, uTopFade: { value: topFade }, uWallH: { value: WALL_H },
    }]),
    vertexShader: HAZE_VERT,
    fragmentShader: HAZE_FRAG,
    lights: true,
    fog: true,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
  return m
}

// items: { x, y, h (sim), s size, a opacity, ph phase, amp drift, rot }. The mesh sits at `origin`
// (three.js) so transparency sorting sees it where the cloud actually is.
function HazeCloud({ items, material, origin, renderOrder = 3 }) {
  const ref = useRef()
  const geom = useMemo(() => {
    const g = new THREE.PlaneGeometry(1, 1)
    const seeds = new Float32Array(items.length * 4)
    items.forEach((it, i) => seeds.set([it.ph, it.amp, it.rot, it.a], i * 4))
    g.setAttribute('aSeed', new THREE.InstancedBufferAttribute(seeds, 4))
    return g
  }, [items])
  useEffect(() => () => geom.dispose(), [geom])
  useLayoutEffect(() => {
    if (!ref.current) return
    const m = new THREE.Matrix4()
    items.forEach((it, i) => {
      m.makeScale(it.s, it.s, it.s)
      m.setPosition(it.x - origin[0], it.h - origin[1], -it.y - origin[2])
      ref.current.setMatrixAt(i, m)
    })
    ref.current.instanceMatrix.needsUpdate = true
  }, [items, origin])
  if (!items.length) return null
  return <instancedMesh ref={ref} args={[geom, material, items.length]} position={origin} frustumCulled={false} renderOrder={renderOrder} />
}

// Where the dust hangs: everywhere, thicker over the rubble piles and in the hazard zone
// where the roof came down. Low and large: it settles.
function layoutHaze(fp, count) {
  const r = rng(31337)
  const [W, H] = fp.size
  const rooms = fp.rooms ?? []
  const rubble = fp.rubble ?? []
  const hazards = fp.hazards ?? []
  const items = []
  const add = (x, y, h, s) => items.push({
    x: Math.min(W - 0.8, Math.max(0.8, x)), y: Math.min(H - 0.8, Math.max(0.8, y)), h: Math.min(2.2, Math.max(0.3, h)), s,
    a: (0.04 + r() * 0.06) * (1.15 - ((s - 2) / 3) * 0.4), ph: r() * 6.283, amp: 0.3 + r() * 0.6, rot: (r() - 0.5) * 0.6,
  })
  const size = () => 2 + 3 * r() ** 2 // 2 to 5 m, mostly small
  const nRubble = rubble.length ? Math.round(count * 0.3) : 0
  const nHaz = hazards.length ? Math.round(count * 0.2) : 0
  const nRoom = count - nRubble - nHaz
  const areas = rooms.map((rm) => { const [x0, x1, y0, y1] = box(rm.poly); return (x1 - x0) * (y1 - y0) })
  const total = areas.reduce((a, b) => a + b, 0) || 1
  rooms.forEach((rm, i) => {
    const [x0, x1, y0, y1] = box(rm.poly)
    const n = Math.round((nRoom * areas[i]) / total)
    for (let k = 0; k < n; k++) add(x0 + 0.8 + r() * (x1 - x0 - 1.6), y0 + 0.8 + r() * (y1 - y0 - 1.6), 0.3 + 1.9 * r() ** 1.5, size())
  })
  rubble.forEach((rb) => {
    const [x0, x1, y0, y1] = box(rb.poly)
    const n = Math.round(nRubble / rubble.length)
    for (let k = 0; k < n; k++) {
      const a = r() * 6.283
      const d = r() ** 0.7 * ((x1 - x0) / 2 + 2.2)
      add((x0 + x1) / 2 + Math.cos(a) * d, (y0 + y1) / 2 + Math.sin(a) * d * 0.8, 0.4 + (rb.height || 1) * 0.5 + r() * 1.0, size())
    }
  })
  hazards.forEach((hz) => {
    const [x0, x1, y0, y1] = box(hz.poly)
    const n = Math.round(nHaz / hazards.length)
    for (let k = 0; k < n; k++) add(x0 + 0.6 + r() * (x1 - x0 - 1.2), y0 + 0.6 + r() * (y1 - y0 - 1.2), 0.4 + 1.7 * r() ** 1.2, size())
  })
  return items
}

function Haze({ fp, night, perf }) {
  const items = useMemo(() => layoutHaze(fp, perf ? 100 : 350), [fp, perf])
  const mat = useMemo(() => hazeMaterial({ color: '#a8a095', opacity: 1 }), [])
  useEffect(() => () => mat.dispose(), [mat])
  const origin = useMemo(() => [fp.size[0] / 2, 1, -fp.size[1] / 2], [fp])
  useFrame(({ clock }) => {
    mat.uniforms.uTime.value = clock.elapsedTime
    mat.uniforms.uOpacity.value = night ? 1 : 0.5
  })
  return <HazeCloud items={items} material={mat} origin={origin} />
}

// --------------------------------------------------------------- broken pipe and water
// The wet room: a break room, kitchen, lab or plant room if the plan has one. The pipe comes
// out of its north wall between the windows and clear of the doors; the whole stub stays
// within 0.5 m of the wall line, so it never reads as blocking a robot.
function wetSpot(fp) {
  const rooms = fp.rooms ?? []
  const room = rooms.find((rm) => /break|kitchen|pharm|lab|boiler/i.test(rm.name)) ?? rooms[1] ?? rooms[0]
  if (!room) return null
  const [x0, x1, , y1] = box(room.poly)
  const segs = fp.walls.map((w, i) => ({ w, i })).filter(({ w }) => w.material !== 'metal'
    && Math.abs(w.a[1] - y1) < 0.3 && Math.abs(w.b[1] - y1) < 0.3
    && Math.min(w.a[0], w.b[0]) < x1 - 0.5 && Math.max(w.a[0], w.b[0]) > x0 + 0.5)
  if (!segs.length) return null
  const damage = wallDamage(fp)
  const doors = fp.doors ?? []
  // keep the splash off the thermal targets (decoys stand against walls, survivors lie near them)
  const targets = [...(fp.decoys ?? []), ...(fp.survivors ?? [])].map((t) => t.pos).filter(Boolean)
  const pref = x0 + (x1 - x0) * 0.65
  let best = null
  for (let px = x0 + 1; px <= x1 - 1; px += 0.25) {
    const seg = segs.find(({ w }) => px > Math.min(w.a[0], w.b[0]) + 0.4 && px < Math.max(w.a[0], w.b[0]) - 0.4)
    if (!seg) continue
    if (doors.some((d) => Math.hypot(d.at[0] - px, d.at[1] - y1) < 1.6)) continue
    if (targets.some((p) => Math.hypot(p[0] - px, p[1] - (y1 - 1.3)) < 1.8)) continue
    const dmg = damage[seg.i]
    if (dmg) {
      const local = (px - (seg.w.a[0] + seg.w.b[0]) / 2) * (Math.sign(seg.w.b[0] - seg.w.a[0]) || 1)
      if (dmg.windows.some((win) => Math.abs(win.x - local) < 1.05)) continue
      if (dmg.breaches.some((b) => Math.abs(b.x - local) < b.rx * 1.2 + 0.5)) continue
    }
    if (!best || Math.abs(px - pref) < Math.abs(best.px - pref)) best = { px, seg }
  }
  if (!best) best = { px: pref, seg: segs[0] }
  const half = (THICK[best.seg.w.material] ?? 0.2) / 2
  const face = y1 - half // inner face of the wall (sim y)
  const stub = 0.43 - half - 0.07 // riser stands 7 cm off the face; the crushed end stays inside 0.5 m
  return { px: best.px, face, stub, land: face - 0.07 - stub - 0.95 }
}

let pipeMats = null
function pipeMaterials() {
  if (pipeMats) return pipeMats
  const t = materials()
  pipeMats = {
    pipe: new THREE.MeshStandardMaterial({ color: '#8b9096', metalness: 0.7, roughness: 0.42 }),
    bracket: new THREE.MeshStandardMaterial({ color: '#3a3f45', metalness: 0.5, roughness: 0.6 }),
    wet: new THREE.MeshStandardMaterial({ map: t.dust, color: '#15181b', transparent: true, opacity: 0.7, depthWrite: false, roughness: 1,
      polygonOffset: true, polygonOffsetFactor: -2 }),
    scorch: new THREE.MeshStandardMaterial({ map: t.dust, color: '#0b0a09', transparent: true, opacity: 0.9, depthWrite: false, roughness: 1 }),
  }
  return pipeMats
}

// Static: the riser up the wall, the elbow, the sheared stub with its crushed end, brackets,
// and the dark streak where the water has been running down the wall.
function PipeStub({ spot }) {
  const M = pipeMaterials()
  const { px, face, stub } = spot
  const riserY = face - 0.07
  return (
    <group>
      <mesh position={w2t(px, riserY, (0.15 + WALL_H) / 2)} material={M.pipe} castShadow>
        <cylinderGeometry args={[0.045, 0.045, WALL_H - 0.15, 10]} />
      </mesh>
      {[0.6, 1.9].map((h) => (
        <mesh key={h} position={w2t(px, face - 0.04, h)} material={M.bracket}><boxGeometry args={[0.14, 0.05, 0.08]} /></mesh>
      ))}
      <mesh position={w2t(px, riserY, 1.3)} material={M.pipe} castShadow><sphereGeometry args={[0.062, 10, 8]} /></mesh>
      <mesh position={w2t(px, riserY - stub / 2, 1.3)} rotation={[Math.PI / 2, 0, 0]} material={M.pipe} castShadow>
        <cylinderGeometry args={[0.045, 0.045, stub, 10]} />
      </mesh>
      {/* the sheared end, crushed flat where the slab came past it */}
      <mesh position={w2t(px, riserY - stub - 0.015, 1.3)} rotation={[Math.PI / 2, 0, 0.3]} scale={[1.35, 1, 0.55]} material={M.pipe}>
        <cylinderGeometry args={[0.058, 0.05, 0.035, 10]} />
      </mesh>
      {/* water running down the wall and spraying back onto it */}
      <mesh position={w2t(px, face - 0.006, 0.66)} material={M.wet}><planeGeometry args={[0.9, 1.4]} /></mesh>
    </group>
  )
}

let wetShape = null
// A puddle outline that is not a perfect circle.
function puddleGeometry() {
  if (wetShape) return wetShape
  const r = rng(2024)
  const bumps = Array.from({ length: 4 }, () => [r() * 6.283, 0.05 + r() * 0.08, 1 + Math.floor(r() * 3)])
  const s = new THREE.Shape()
  const n = 36
  for (let k = 0; k < n; k++) {
    const a = (k / n) * Math.PI * 2
    let rad = 1
    for (const [ph, amp, f] of bumps) rad += Math.sin(a * f + ph) * amp
    if (k) s.lineTo(Math.cos(a) * rad, Math.sin(a) * rad)
    else s.moveTo(Math.cos(a) * rad, Math.sin(a) * rad)
  }
  wetShape = new THREE.ShapeGeometry(s)
  return wetShape
}

const FALL_T = Math.sqrt((2 * 1.3) / 9.81) // seconds for water to fall from the break to the floor

// Live: the jet (points on a parabola, phase advanced each frame), the splash where it lands,
// and the puddle growing out from there along the wall for the first minute.
function Water({ spot, perf }) {
  const N = perf ? 120 : 200
  const NS = perf ? 30 : 60
  const { geom, seeds } = useMemo(() => {
    const r = rng(777)
    const seeds = new Float32Array((N + NS) * 3) // phase, speed, lateral
    for (let i = 0; i < N; i++) seeds.set([r(), 1.6 + r() * 0.5, (r() - 0.5) * 0.5], i * 3)
    for (let i = N; i < N + NS; i++) seeds.set([r(), r() * 6.283, 0.2 + r() * 0.25], i * 3)
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array((N + NS) * 3), 3).setUsage(THREE.DynamicDrawUsage))
    return { geom: g, seeds }
  }, [N, NS])
  useEffect(() => () => geom.dispose(), [geom])
  const puddle = useRef()
  const halo = useRef()
  const born = useRef(-1)
  const sx = spot.px
  const sy = 1.3
  const sz = -(spot.face - 0.07 - spot.stub) // three.js z of the break; the jet goes +z (south, into the room)
  const landZ = -spot.land
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    if (born.current < 0) born.current = t
    const p = geom.attributes.position.array
    for (let i = 0; i < N; i++) {
      const k = (seeds[i * 3] + t / FALL_T) % 1
      const tau = k * FALL_T
      p[i * 3] = sx + seeds[i * 3 + 2] * tau
      p[i * 3 + 1] = sy - 4.905 * tau * tau
      p[i * 3 + 2] = sz + seeds[i * 3 + 1] * tau
    }
    for (let i = N; i < N + NS; i++) {
      const k = (seeds[i * 3] + t * 1.6) % 1
      const a = seeds[i * 3 + 1]
      const d = k * seeds[i * 3 + 2] * 1.6
      p[i * 3] = sx + Math.cos(a) * d
      p[i * 3 + 1] = 0.02 + Math.sin(3.1416 * k) * 0.14
      p[i * 3 + 2] = landZ + Math.sin(a) * d * 0.7
    }
    geom.attributes.position.needsUpdate = true
    // the puddle: half a metre across at the start, 2.5 m along the wall after a minute, never
    // further than 1.8 m out from the wall, and a ripple from the water hitting it
    const g = Math.min(1, (t - born.current) / 60)
    const ease = g * g * (3 - 2 * g)
    const ripple = 1 + 0.01 * Math.sin(t * 2.3) + 0.004 * Math.sin(t * 5.1)
    const ra = (0.5 + 2.0 * ease) * ripple
    const rb = Math.min(0.62, 0.5 + 2.0 * ease) * ripple
    if (puddle.current) puddle.current.scale.set(ra, rb, 1)
    if (halo.current) halo.current.scale.set(ra * 2.4, rb * 2.6, 1)
  })
  return (
    <group>
      <points geometry={geom} frustumCulled={false} renderOrder={4}>
        <pointsMaterial map={materials().puff} color="#cfe9ff" size={0.035} sizeAttenuation transparent opacity={0.8} depthWrite={false}
                        blending={THREE.AdditiveBlending} />
      </points>
      <mesh ref={halo} position={[sx, 0.010, landZ]} rotation={[-Math.PI / 2, 0, 0]} material={pipeMaterials().wet}>
        <planeGeometry args={[1, 1]} />
      </mesh>
      <mesh ref={puddle} position={[sx, 0.013, landZ]} rotation={[-Math.PI / 2, 0, 0]} geometry={puddleGeometry()} receiveShadow>
        <meshStandardMaterial color="#0b1014" metalness={0.95} roughness={0.08} transparent opacity={0.85} envMapIntensity={1.5} />
      </mesh>
    </group>
  )
}

// --------------------------------------------------------------- fire in the hazard room
// Southern half of the no-go zone, just past the broken edge of the roof slab that still
// hangs over it, at the foot of the rubble mound: robots never go there, so it can burn.
function firePlace(fp) {
  const hz = fp.hazards?.[0]
  if (!hz) return null
  const [x0, x1, y0, y1] = box(hz.poly)
  return { x: (x0 + x1) / 2 + Math.min(0.6, (x1 - x0) * 0.1), y: y0 + (y1 - y0) * 0.46 }
}

function Scorch({ at }) {
  return (
    <mesh position={w2t(at.x, at.y, 0.011)} rotation={[-Math.PI / 2, 0, 0.4]} material={pipeMaterials().scorch}>
      <planeGeometry args={[4.2, 3.4]} />
    </mesh>
  )
}

const FLAME_COLORS = ['#ff8c2a', '#ffb347', '#ff6a14', '#ffd27a', '#ff9a3c']

function Fire({ at, night, perf }) {
  const NE = perf ? 60 : 120
  const flames = useMemo(() => Array.from({ length: perf ? 4 : 6 }, (_, i) => {
    const r = rng(900 + i * 31)
    return { dx: (r() - 0.5) * 1.5, dz: (r() - 0.5) * 1.1, w: 0.6 + r() * 0.5, h: 0.9 + r() * 0.9, ph: r() * 6.283, color: FLAME_COLORS[i % 5] }
  }), [perf])
  const { embers, seeds } = useMemo(() => {
    const r = rng(4411)
    const seeds = new Float32Array(NE * 4) // dx, dz, climb speed, phase
    for (let i = 0; i < NE; i++) seeds.set([(r() - 0.5) * 1.6, (r() - 0.5) * 1.2, 0.5 + r() * 0.9, r()], i * 4)
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(NE * 3), 3).setUsage(THREE.DynamicDrawUsage))
    g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(NE * 3), 3).setUsage(THREE.DynamicDrawUsage))
    return { embers: g, seeds }
  }, [NE])
  useEffect(() => () => embers.dispose(), [embers])
  const smokeMat = useMemo(() => hazeMaterial({ color: '#6a625c', opacity: 1, rise: 5.5, topFade: 0 }), [])
  useEffect(() => () => smokeMat.dispose(), [smokeMat])
  const smoke = useMemo(() => {
    const r = rng(5150)
    return Array.from({ length: perf ? 6 : 10 }, () => ({
      x: at.x + (r() - 0.5) * 0.9, y: at.y + (r() - 0.5) * 0.7, h: 1.1, s: 1.4 + r() * 0.7,
      a: 0.55 + r() * 0.3, ph: r() * 6.283, amp: 0.2 + r() * 0.3, rot: (r() - 0.5) * 0.8,
    }))
  }, [at, perf])
  const origin = useMemo(() => [at.x, 1, -at.y], [at])
  const flameGroup = useRef()
  const glow = useRef()
  const light = useRef()
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    smokeMat.uniforms.uTime.value = t
    const kids = flameGroup.current?.children
    if (kids) {
      for (let i = 0; i < flames.length; i++) {
        const f = flames[i]
        const sp = kids[i]
        const s = 1 + 0.18 * Math.sin(t * 9.1 + f.ph) + 0.12 * Math.sin(t * 15.7 + f.ph * 2.3)
        sp.scale.set(f.w * (1.1 - 0.1 * s), f.h * s, 1)
        sp.position.y = 0.2 + (f.h * s) / 2
        sp.material.opacity = 0.6 + 0.3 * Math.sin(t * 11.3 + f.ph * 1.7)
      }
    }
    if (glow.current) glow.current.material.opacity = 0.10 + 0.04 * Math.sin(t * 7.7)
    if (light.current) {
      light.current.intensity = 13 + 3 * Math.sin(t * 13) + 2 * Math.sin(t * 7.3 + 1)
      light.current.position.x = at.x + 0.05 * Math.sin(t * 5.3)
      light.current.position.z = -at.y + 0.05 * Math.cos(t * 4.1)
    }
    const p = embers.attributes.position.array
    const c = embers.attributes.color.array
    for (let i = 0; i < NE; i++) {
      const k = (seeds[i * 4 + 3] + (t * seeds[i * 4 + 2]) / 3.5) % 1
      p[i * 3] = at.x + seeds[i * 4] * (1 + k * 0.5) + Math.sin(t * 2 + i) * 0.15 * k
      p[i * 3 + 1] = 0.3 + k * 3.5
      p[i * 3 + 2] = -at.y + seeds[i * 4 + 1] * (1 + k * 0.5) + Math.cos(t * 1.7 + i) * 0.15 * k
      const f = (1 - k) * (1 - k) // dim as they climb and cool: additive black is invisible
      c[i * 3] = f
      c[i * 3 + 1] = f * 0.45
      c[i * 3 + 2] = f * 0.08
    }
    embers.attributes.position.needsUpdate = true
    embers.attributes.color.needsUpdate = true
  })
  const puffTex = materials().puff
  return (
    <group>
      <group ref={flameGroup} position={[at.x, 0, -at.y]}>
        {flames.map((f, i) => (
          <sprite key={i} position={[f.dx, 0.2 + f.h / 2, f.dz]} scale={[f.w, f.h, 1]} renderOrder={4}>
            <spriteMaterial map={puffTex} color={f.color} transparent opacity={0.8} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
          </sprite>
        ))}
      </group>
      {/* heat glow on the ground and the rubble around the fire */}
      <sprite ref={glow} position={[at.x, 0.3, -at.y]} scale={[3.2, 2.2, 1]} renderOrder={4}>
        <spriteMaterial map={puffTex} color="#ff6a14" transparent opacity={0.1} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
      </sprite>
      <points geometry={embers} frustumCulled={false} renderOrder={4}>
        <pointsMaterial map={puffTex} vertexColors size={0.05} sizeAttenuation transparent depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
      </points>
      <HazeCloud items={smoke} material={smokeMat} origin={origin} renderOrder={3} />
      <pointLight ref={light} position={[at.x, 1.0, -at.y]} color="#ff7a1a" intensity={13} distance={14} decay={1.6} />
    </group>
  )
}

// --------------------------------------------------------------- emergency lights
// Two of the building's own fixtures still have battery: a red beacon on the wall just
// inside the entrance, and an amber light at the far end of the biggest room. Mounted at
// 2 m, so they hang above anything a robot drives through.
function mountOn(q, toward, w, beacon, color) {
  const half = (THICK[w?.material] ?? 0.2) / 2
  let dx = toward[0] - q[0]
  let dy = toward[1] - q[1]
  const L = Math.hypot(dx, dy) || 1
  dx /= L
  dy /= L
  return { x: q[0] + dx * (half + 0.06), y: q[1] + dy * (half + 0.06), h: 1.98, face: [dx, dy], beacon, color }
}

function fixtureSpots(fp) {
  const [, H] = fp.size
  const entry = fp.entry ?? [1, H / 2]
  const cp = fp.command_post?.pos ?? [-2, H / 2]
  const walls = fp.walls.filter((w) => w.material !== 'metal')
  const out = []
  // 1.6 m in from the entrance, on the nearest wall that is not the one the door is cut in
  const L = Math.hypot(entry[0] - cp[0], entry[1] - cp[1]) || 1
  const p = [entry[0] + ((entry[0] - cp[0]) / L) * 1.6, entry[1] + ((entry[1] - cp[1]) / L) * 1.6]
  let near = null
  for (const w of walls) {
    const s = segDist(p, w.a, w.b)
    if (Math.hypot(s.q[0] - entry[0], s.q[1] - entry[1]) < 1.2) continue
    if (!near || s.d < near.d) near = { ...s, w }
  }
  if (near) out.push(mountOn(near.q, p, near.w, true, '#ff2419'))
  // the far end of the largest room: the middle of its side farthest from the entrance
  let big = null
  for (const rm of fp.rooms ?? []) {
    const b = box(rm.poly)
    const area = (b[1] - b[0]) * (b[3] - b[2])
    if (!big || area > big.area) big = { b, area }
  }
  if (big) {
    const [x0, x1, y0, y1] = big.b
    const c = [(x0 + x1) / 2, (y0 + y1) / 2]
    const mids = [[x0, c[1]], [x1, c[1]], [c[0], y0], [c[0], y1]]
    const far = mids.reduce((m, q) => (Math.hypot(q[0] - entry[0], q[1] - entry[1]) > Math.hypot(m[0] - entry[0], m[1] - entry[1]) ? q : m))
    const w = walls.find((wl) => segDist(far, wl.a, wl.b).d < 0.3)
    out.push(mountOn(far, c, w, false, '#ffa126'))
  }
  return out
}

// Irregular flicker: a buzz, the odd dropout, and now and then a long one.
function flick(t, ph) {
  if (Math.sin(t * 0.61 + ph) > 0.93) return 0.05
  return Math.sin(t * 7.3 + ph) * Math.sin(t * 2.17 + ph * 1.3) > -0.55 ? 1 : 0.15
}

const BEACON_Q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, -1, 0), new THREE.Vector3(3, -1.6, 0).normalize())

function EmergencyLight({ spot, night, perf }) {
  const lens = useMemo(() => new THREE.MeshStandardMaterial({ color: spot.color, emissive: spot.color, emissiveIntensity: 2, toneMapped: false }), [spot.color])
  useEffect(() => () => lens.dispose(), [lens])
  const light = useRef()
  const beam = useRef()
  const spin = useRef()
  const tgt = useMemo(() => new THREE.Object3D(), [])
  const ph = (spot.x * 7.1 + spot.y * 3.3) % 6.283
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    const on = flick(t, ph)
    lens.emissiveIntensity = on * (2.4 + 0.6 * Math.sin(t * 41))
    if (light.current) light.current.intensity = on * 4.5
    if (spin.current) spin.current.rotation.y = t * ((Math.PI * 2) / 3)
    if (beam.current) beam.current.intensity = on * (night ? 28 : 10)
  })
  return (
    <group position={w2t(spot.x, spot.y, spot.h)} rotation={[0, Math.atan2(spot.face[0], -spot.face[1]), 0]}>
      <mesh castShadow>
        <boxGeometry args={[0.3, 0.14, 0.1]} />
        <meshStandardMaterial color="#2a2d31" roughness={0.6} metalness={0.4} />
      </mesh>
      <mesh position={[0, 0, 0.055]} material={lens}><boxGeometry args={[0.22, 0.08, 0.02]} /></mesh>
      <pointLight ref={light} position={[0, -0.05, 0.25]} color={spot.color} distance={6} decay={1.8} intensity={4} />
      {spot.beacon && !perf && (
        // the beacon dome on a short arm off the wall; its target and light cone sweep together
        <group position={[0, 0.16, 0.18]}>
          <mesh material={lens}><cylinderGeometry args={[0.06, 0.07, 0.1, 12]} /></mesh>
          <group ref={spin}>
            <primitive object={tgt} position={[3, -1.6, 0]} />
            <group quaternion={BEACON_Q}><LightBeam length={5.5} radius={1.4} color={spot.color} opacity={night ? 0.16 : 0.05} /></group>
          </group>
          <spotLight ref={beam} target={tgt} angle={0.5} penumbra={0.45} distance={12} decay={1.5} color={spot.color} intensity={20} />
        </group>
      )}
    </group>
  )
}

// --------------------------------------------------------------- exports
// Static set dressing (goes inside <Baked>): the pipe run and the scorch under the fire.
export function AtmosphereStatic({ fp }) {
  const spot = useMemo(() => wetSpot(fp), [fp])
  const fire = useMemo(() => firePlace(fp), [fp])
  return (
    <group>
      {spot && <PipeStub spot={spot} />}
      {fire && <Scorch at={fire} />}
    </group>
  )
}

// Everything that moves or glows. `night` halves the haze by day; `perf` thins the haze,
// the water and the embers and drops the sweeping beacon (4 lights in all, 3 with perf).
export function AtmosphereLive({ fp, night = false, perf = false }) {
  const spot = useMemo(() => wetSpot(fp), [fp])
  const fire = useMemo(() => firePlace(fp), [fp])
  const fixtures = useMemo(() => fixtureSpots(fp), [fp])
  return (
    <group>
      <Haze fp={fp} night={night} perf={perf} />
      {spot && <Water spot={spot} perf={perf} />}
      {fire && <Fire at={fire} night={night} perf={perf} />}
      {fixtures.map((f, i) => <EmergencyLight key={i} spot={f} night={night} perf={perf} />)}
    </group>
  )
}
