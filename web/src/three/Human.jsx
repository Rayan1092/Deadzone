import { Fragment, useMemo } from 'react'
import * as THREE from 'three'
import { materials, tiledSet } from './textures'

// A trapped survivor at true scale (about 1.72 m), lying on their back where they fell:
// a sculpted torso (lathe profile: hips, waist, chest, shoulders; flattened front to back),
// tapered limbs with rounded joints, hands, shoes, a shaped head with nose, ears and hair,
// and dusty clothes with a woven-fabric surface. One arm thrown up beside the head, one
// knee bent, a slab pinning the legs. Local frame: x toward the head, y up, z to their left.
// Outfits vary per survivor id so the three people don't look cloned.

const OUTFITS = [
  { top: '#33486b', legs: '#2c3138', skin: '#c99a7a', hair: '#2a1d14', shoe: '#2a221c' },
  { top: '#6e2e2a', legs: '#3a3e45', skin: '#8d5e43', hair: '#14100c', shoe: '#1b1b1b' },
  { top: '#56693f', legs: '#25303c', skin: '#e3bc9a', hair: '#6b4a2b', shoe: '#3b2f25' },
  { top: '#b45f12', legs: '#30363f', skin: '#b07b5a', hair: '#1d1510', shoe: '#222' },
]

let fabric = null
function fabricMaps() {
  // fine weave for clothes, from the shared procedural carpet surface at a tighter repeat
  fabric ??= tiledSet(materials().carpet, 6, 6)
  return fabric
}

const cache = new Map()
function outfitMats(id) {
  let h = 0
  for (const ch of id ?? '') h = (h * 31 + ch.charCodeAt(0)) % 997
  const o = OUTFITS[h % OUTFITS.length]
  if (!cache.has(o)) {
    const dusty = (hex, amt = 0.28) => new THREE.Color(hex).lerp(new THREE.Color('#b9ad9a'), amt) // collapse dust
    const f = fabricMaps()
    cache.set(o, {
      top: new THREE.MeshStandardMaterial({ color: dusty(o.top), roughness: 0.92, normalMap: f.normalMap, normalScale: new THREE.Vector2(0.6, 0.6) }),
      legs: new THREE.MeshStandardMaterial({ color: dusty(o.legs, 0.22), roughness: 0.9, normalMap: f.normalMap, normalScale: new THREE.Vector2(0.5, 0.5) }),
      skin: new THREE.MeshStandardMaterial({ color: dusty(o.skin, 0.12), roughness: 0.55 }),
      hair: new THREE.MeshStandardMaterial({ color: dusty(o.hair, 0.15), roughness: 0.85 }),
      shoe: new THREE.MeshStandardMaterial({ color: o.shoe, roughness: 0.6, metalness: 0.05 }),
      sole: new THREE.MeshStandardMaterial({ color: '#1a1a1a', roughness: 0.9 }),
    })
    // body heat for the thermal camera (thermal.jsx): skin hottest, clothes and hair a little cooler, shoes near the floor
    const m = cache.get(o)
    m.skin.userData.thermalTemp = 34.5; m.top.userData.thermalTemp = 31; m.legs.userData.thermalTemp = 30.5
    m.hair.userData.thermalTemp = 30; m.shoe.userData.thermalTemp = 24; m.sole.userData.thermalTemp = 22
  }
  return cache.get(o)
}

// Torso: lathe of the body's half-width along its length (hips -> neck base), flattened
// front to back, laid along +x.
let torsoGeom = null
function torso() {
  if (torsoGeom) return torsoGeom
  const prof = [[0.0, 0.0], [0.15, 0.01], [0.175, 0.07], [0.165, 0.14], [0.142, 0.22], [0.15, 0.3], [0.17, 0.38],
    [0.185, 0.45], [0.18, 0.5], [0.13, 0.55], [0.06, 0.575], [0.0, 0.58]].map(([r, y]) => new THREE.Vector2(r, y))
  const g = new THREE.LatheGeometry(prof, 28)
  g.scale(1, 1, 0.62)          // chest is deeper side to side than front to back
  g.rotateZ(-Math.PI / 2)      // lathe axis y -> body axis +x
  torsoGeom = g
  return g
}

// Head: an egg-shaped lathe (chin narrower than the crown), facing up.
let headGeom = null
function head() {
  if (headGeom) return headGeom
  const prof = [[0, 0], [0.045, 0.01], [0.07, 0.04], [0.085, 0.09], [0.09, 0.13], [0.082, 0.18], [0.06, 0.21], [0, 0.225]]
    .map(([r, y]) => new THREE.Vector2(r, y))
  const g = new THREE.LatheGeometry(prof, 24)
  g.scale(1, 1, 1.12)
  g.rotateZ(-Math.PI / 2)      // chin -> crown along +x
  headGeom = g
  return g
}

// Tapered segment from a to b (radii r0 at a, r1 at b) with a rounded joint at a.
function Seg({ a, b, r0, r1, m, joint = true }) {
  const A = new THREE.Vector3(...a)
  const B = new THREE.Vector3(...b)
  const mid = A.clone().add(B).multiplyScalar(0.5)
  const dir = B.clone().sub(A)
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize())
  return (
    <>
      <mesh position={mid} quaternion={q} material={m} castShadow receiveShadow>
        <cylinderGeometry args={[r1, r0, dir.length(), 16, 1]} />
      </mesh>
      {joint && <mesh position={A} material={m} castShadow><sphereGeometry args={[r0, 16, 12]} /></mesh>}
    </>
  )
}

function Hand({ at, rot, m }) {
  return (
    <group position={at} rotation={rot}>
      <mesh material={m} scale={[1, 0.38, 0.85]} castShadow><sphereGeometry args={[0.05, 12, 10]} /></mesh>
      <mesh material={m} position={[0.045, 0, 0.012]} scale={[1.4, 0.32, 0.7]}><sphereGeometry args={[0.03, 10, 8]} /></mesh>
      <mesh material={m} position={[0.01, 0, -0.04]} rotation={[0, 0.7, 0]} scale={[1.2, 0.5, 0.5]}><sphereGeometry args={[0.02, 8, 6]} /></mesh>
    </group>
  )
}

// Shoe on a foot lying on its heel: toes up (+y), sole facing away from the body (-x).
function Shoe({ at, rot, M }) {
  return (
    <group position={at} rotation={rot}>
      <mesh material={M.shoe} position={[0.01, 0.07, 0]} scale={[0.8, 1.9, 0.95]} castShadow><sphereGeometry args={[0.055, 14, 10]} /></mesh>
      <mesh material={M.sole} position={[-0.035, 0.07, 0]}><boxGeometry args={[0.02, 0.24, 0.095]} /></mesh>
    </group>
  )
}

// ------------------------------------------------------------------ posed survivors
// The three demo survivors are posed like the real thermal crops the detector judges (the crop
// manifest's `pose`): S1 crouched low on the floor, S2 kneeling bent over, S3 slumped in a chair.
// Same body parts as the lying figure. A pose is the hips, the spine and front directions (the
// torso's frame: x along the spine, y out of the chest, z to their left) and the elbows, hands,
// knees and ankles in the figure's frame (y up, facing +x, their left is -z). Limb lengths match
// the lying figure (upper arm ~0.26, forearm ~0.27, thigh ~0.44, shin ~0.44 m).
const POSES = {
  crouching: {
    hips: [-0.12, 0.36, 0], spine: [0.42, 0.9, 0], front: [0.9, -0.42, 0], headRot: [0, 0, 0.45], feet: 'stand',
    L: { elbow: [0.28, 0.62, -0.26], hand: [0.4, 0.42, -0.1], knee: [0.3, 0.5, -0.14], ankle: [0.08, 0.1, -0.15] },
    R: { elbow: [0.28, 0.62, 0.26], hand: [0.4, 0.42, 0.1], knee: [0.3, 0.5, 0.14], ankle: [0.08, 0.1, 0.15] },
  },
  kneeling: {
    hips: [-0.12, 0.44, 0], spine: [0.96, 0.27, 0], front: [0.27, -0.96, 0], headRot: [0, 0, 0.35], feet: 'kneel',
    L: { elbow: [0.42, 0.32, -0.25], hand: [0.5, 0.06, -0.2], knee: [0.02, 0.08, -0.12], ankle: [-0.4, 0.06, -0.13] },
    R: { elbow: [0.42, 0.32, 0.25], hand: [0.5, 0.06, 0.2], knee: [0.02, 0.08, 0.12], ankle: [-0.4, 0.06, 0.13] },
  },
  // a command post operator: upright on a chair, hands on a laptop on the table in front
  operator: {
    hips: [-0.04, 0.58, 0], spine: [0.05, 1, 0], front: [1, -0.05, 0], headRot: [0, 0, 0.2], feet: 'stand',
    L: { elbow: [0.12, 0.85, -0.24], hand: [0.37, 0.78, -0.15], knee: [0.4, 0.56, -0.13], ankle: [0.46, 0.1, -0.15] },
    R: { elbow: [0.12, 0.85, 0.24], hand: [0.37, 0.78, 0.15], knee: [0.4, 0.56, 0.13], ankle: [0.46, 0.1, 0.15] },
  },
  sitting: {
    hips: [-0.04, 0.58, 0], spine: [-0.3, 0.95, 0], front: [0.95, 0.3, 0], headRot: [0.5, 0, 0.25], feet: 'stand',
    L: { elbow: [-0.12, 0.72, -0.27], hand: [0, 0.5, -0.3], knee: [0.4, 0.56, -0.13], ankle: [0.46, 0.1, -0.15] },
    R: { elbow: [-0.12, 0.72, 0.27], hand: [0, 0.5, 0.3], knee: [0.4, 0.56, 0.13], ankle: [0.46, 0.1, 0.15] },
  },
}
export const HUMAN_POSES = ['lying', ...Object.keys(POSES)]

// rotation taking local x to `xDir` and local y to `yDir` (made perpendicular), z = x × y
function basis(xDir, yDir) {
  const x = new THREE.Vector3(...xDir).normalize()
  const yv = new THREE.Vector3(...yDir)
  const y = yv.sub(x.clone().multiplyScalar(yv.dot(x))).normalize()
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, x.clone().cross(y)))
}
const SHOE_STAND = basis([0, 1, 0], [1, 0, 0])    // sole down, toes forward
const SHOE_KNEEL = basis([0, -1, 0], [-1, 0, 0])  // kneeling: top of the foot on the floor, sole up, toes back

function Head({ M }) {
  return (
    <>
      <mesh geometry={head()} material={M.skin} castShadow />
      <mesh position={[0.11, 0.075, 0]} rotation={[0, 0, -Math.PI / 2]} material={M.skin}><coneGeometry args={[0.016, 0.04, 8]} /></mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[0.11, 0, s * 0.098]} scale={[1, 1.4, 0.4]} material={M.skin}><sphereGeometry args={[0.02, 8, 6]} /></mesh>
      ))}
      <mesh position={[0.12, -0.005, 0]} rotation={[0, 0, -Math.PI / 2]} scale={[0.97, 1.05, 1.16]} material={M.hair}>
        <sphereGeometry args={[0.096, 18, 12, 0, Math.PI * 2, 0, Math.PI * 0.6]} />
      </mesh>
    </>
  )
}

function PosedBody({ M, P }) {
  const q = useMemo(() => basis(P.spine, P.front), [P])
  const hips = new THREE.Vector3(...P.hips)
  const at = (l) => hips.clone().add(new THREE.Vector3(...l).applyQuaternion(q)).toArray()
  const shoulder = { L: at([0.44, 0.02, 0.19]), R: at([0.44, 0.02, -0.19]) }
  const hip = { L: at([-0.01, -0.01, 0.09]), R: at([-0.01, -0.01, -0.09]) }
  const kneel = P.feet === 'kneel'
  return (
    <group>
      <group position={P.hips} quaternion={q}>
        <mesh geometry={torso()} material={M.top} castShadow receiveShadow />
        <mesh position={[0.03, 0, 0]} rotation={[0, 0, Math.PI / 2]} scale={[1, 1, 0.64]} material={M.legs} castShadow>
          <cylinderGeometry args={[0.172, 0.168, 0.1, 24]} />
        </mesh>
        <Seg a={[0.55, 0, 0]} b={[0.65, 0.005, 0]} r0={0.05} r1={0.048} m={M.skin} joint={false} />
        <group position={[0.63, 0.005, 0]} rotation={P.headRot}><Head M={M} /></group>
      </group>
      {['L', 'R'].map((s) => {
        const j = P[s]
        return (
          <Fragment key={s}>
            <Seg a={shoulder[s]} b={j.elbow} r0={0.05} r1={0.042} m={M.top} />
            <Seg a={j.elbow} b={j.hand} r0={0.042} r1={0.034} m={M.top} />
            <Hand at={j.hand} rot={[0, 0, 0]} m={M.skin} />
            <Seg a={hip[s]} b={j.knee} r0={0.085} r1={0.06} m={M.legs} />
            <Seg a={j.knee} b={j.ankle} r0={0.058} r1={0.042} m={M.legs} />
            <group position={[j.ankle[0], kneel ? 0.07 : 0.045, j.ankle[2]]} quaternion={kneel ? SHOE_KNEEL : SHOE_STAND}>
              <mesh material={M.shoe} position={[0.01, 0.07, 0]} scale={[0.8, 1.9, 0.95]} castShadow><sphereGeometry args={[0.055, 14, 10]} /></mesh>
              <mesh material={M.sole} position={[-0.035, 0.07, 0]}><boxGeometry args={[0.02, 0.24, 0.095]} /></mesh>
            </group>
          </Fragment>
        )
      })}
    </group>
  )
}

export default function Human({ id, angle = 0, pose = 'lying' }) {
  const M = useMemo(() => outfitMats(id), [id])
  if (POSES[pose]) return <group rotation={[0, angle, 0]}><PosedBody M={M} P={POSES[pose]} /></group>
  const y = 0.11 // body axis height above the floor when lying on the back
  return (
    <group rotation={[0, angle, 0]}>
      {/* hips at x = -0.05, neck base at x = 0.53 */}
      <mesh geometry={torso()} position={[-0.05, y, 0]} material={M.top} castShadow receiveShadow />
      {/* belt line / trousers over the hips */}
      <mesh position={[-0.02, y, 0]} rotation={[0, 0, Math.PI / 2]} scale={[1, 1, 0.64]} material={M.legs} castShadow>
        <cylinderGeometry args={[0.172, 0.168, 0.1, 24]} />
      </mesh>
      {/* neck and head, turned to one side */}
      <Seg a={[0.5, y, 0]} b={[0.6, y + 0.005, 0]} r0={0.05} r1={0.048} m={M.skin} joint={false} />
      <group position={[0.58, y + 0.005, 0]} rotation={[0.45, 0, 0]}>
        <mesh geometry={head()} material={M.skin} castShadow />
        <mesh position={[0.11, 0.075, 0]} rotation={[0, 0, -Math.PI / 2]} material={M.skin}><coneGeometry args={[0.016, 0.04, 8]} /></mesh>
        {[-1, 1].map((s) => (
          <mesh key={s} position={[0.11, 0, s * 0.098]} scale={[1, 1.4, 0.4]} material={M.skin}><sphereGeometry args={[0.02, 8, 6]} /></mesh>
        ))}
        <mesh position={[0.12, -0.005, 0]} rotation={[0, 0, -Math.PI / 2]} scale={[0.97, 1.05, 1.16]} material={M.hair}>
          <sphereGeometry args={[0.096, 18, 12, 0, Math.PI * 2, 0, Math.PI * 0.6]} />
        </mesh>
      </group>
      {/* left arm flung up beside the head; right arm across the stomach */}
      <Seg a={[0.44, y + 0.02, 0.19]} b={[0.66, y - 0.03, 0.3]} r0={0.05} r1={0.042} m={M.top} />
      <Seg a={[0.66, y - 0.03, 0.3]} b={[0.9, y - 0.06, 0.25]} r0={0.042} r1={0.034} m={M.top} />
      <Hand at={[0.96, y - 0.08, 0.24]} rot={[0, -0.2, 0]} m={M.skin} />
      <Seg a={[0.44, y + 0.02, -0.19]} b={[0.2, y + 0.02, -0.24]} r0={0.05} r1={0.042} m={M.top} />
      <Seg a={[0.2, y + 0.02, -0.24]} b={[0.12, y + 0.1, -0.05]} r0={0.042} r1={0.034} m={M.top} />
      <Hand at={[0.1, y + 0.12, 0.02]} rot={[0.3, 1.2, 0]} m={M.skin} />
      {/* legs: left straight, right knee raised */}
      <Seg a={[-0.06, y - 0.01, 0.09]} b={[-0.5, y - 0.04, 0.11]} r0={0.085} r1={0.06} m={M.legs} />
      <Seg a={[-0.5, y - 0.04, 0.11]} b={[-0.92, y - 0.06, 0.12]} r0={0.058} r1={0.042} m={M.legs} />
      <Shoe at={[-0.96, y - 0.1, 0.12]} rot={[0.35, 0, 0.15]} M={M} />
      <Seg a={[-0.06, y - 0.01, -0.09]} b={[-0.42, y + 0.2, -0.14]} r0={0.085} r1={0.06} m={M.legs} />
      <Seg a={[-0.42, y + 0.2, -0.14]} b={[-0.7, y - 0.07, -0.17]} r0={0.058} r1={0.042} m={M.legs} />
      <Shoe at={[-0.73, y - 0.1, -0.17]} rot={[-0.3, 0, -0.1]} M={M} />
    </group>
  )
}
