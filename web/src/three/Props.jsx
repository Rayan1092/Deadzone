import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { MAST_H, w2t } from './util'
import { materials, signTexture, tiledSet } from './textures'

// Set dressing for the Reality world: furniture against the walls, the decoy heat
// sources as the real objects they are, boilers in the (no-go) boiler room, the command
// truck and its mast outside. Everything hugs walls or sits where the robots never go
// (hazard rooms, outside), because robots plan on the occupancy grid only.
// Props face local +z; rot is the sim heading of local x, like the walls.

// --------------------------------------------------------------- materials
let plain = null
function mats() {
  if (plain) return plain
  const std = (o) => new THREE.MeshStandardMaterial(o)
  plain = {
    wood: std({ color: '#8a6a4a', roughness: 0.65 }),
    laminate: std({ color: '#d6d0c4', roughness: 0.5 }),
    steel: std({ color: '#9ca3ab', metalness: 0.85, roughness: 0.35 }),
    darkSteel: std({ color: '#3b4148', metalness: 0.7, roughness: 0.45 }),
    paintedGrey: std({ color: '#6b7380', metalness: 0.3, roughness: 0.55 }),
    black: std({ color: '#16181b', roughness: 0.5 }),
    rubber: std({ color: '#141516', roughness: 0.9 }),
    fabric: std({ color: '#2f3b4f', roughness: 0.95 }),
    screen: std({ color: '#0a0c10', metalness: 0.4, roughness: 0.15 }),
    cardboard: std({ color: '#a27b4f', roughness: 0.9 }),
    cardboardDark: std({ color: '#8a6640', roughness: 0.9 }),
    wrap: std({ color: '#cfd8dc', roughness: 0.3, transparent: true, opacity: 0.85 }),
    pallet: std({ color: '#9b7b52', roughness: 0.85 }),
    rackOrange: std({ color: '#e0641b', roughness: 0.5, metalness: 0.3 }),
    rackBlue: std({ color: '#1f4e9c', roughness: 0.5, metalness: 0.3 }),
    yellow: std({ color: '#f2b705', roughness: 0.5, metalness: 0.2 }),
    boiler: std({ color: '#8b2c22', roughness: 0.55, metalness: 0.4 }),
    copper: std({ color: '#b06a3b', metalness: 0.85, roughness: 0.35 }),
    pipe: std({ color: '#6f7780', metalness: 0.7, roughness: 0.4 }),
    white: std({ color: '#e6e8ea', roughness: 0.45 }),
    paper: std({ color: '#f1efe9', roughness: 0.9, side: THREE.DoubleSide }),
    glass: std({ color: '#0f1a24', metalness: 0.9, roughness: 0.08 }),
    truckWhite: std({ color: '#eef0f2', roughness: 0.35, metalness: 0.2 }),
    truckRed: std({ color: '#b91c1c', roughness: 0.4, metalness: 0.2 }),
    chrome: std({ color: '#d1d5db', metalness: 1, roughness: 0.2 }),
    cone: std({ color: '#f97316', roughness: 0.55 }),
    vending: std({ color: '#cfe7ff', emissive: '#7cc4ff', emissiveIntensity: 1.4, toneMapped: false }),
    tape: std({ ...tiledSet(materials().tape, 1, 1), roughness: 0.6 }),
  }
  return plain
}
let coldMat = null
function cold() {
  coldMat ??= new THREE.MeshStandardMaterial({ color: '#16295f', emissive: '#0b1d5c', roughness: 1 })
  return new Proxy({}, { get: () => coldMat })
}

// A box / cylinder with a shared material.
function B({ m, s, p = [0, 0, 0], r, shadow = true }) {
  return (
    <mesh position={p} rotation={r} material={m} castShadow={shadow} receiveShadow>
      <boxGeometry args={s} />
    </mesh>
  )
}
function C({ m, rt, rb = rt, h, p = [0, 0, 0], r, seg = 16, shadow = true }) {
  return (
    <mesh position={p} rotation={r} material={m} castShadow={shadow} receiveShadow>
      <cylinderGeometry args={[rt, rb, h, seg]} />
    </mesh>
  )
}

// Place a prop at sim (x, y) with sim heading `rot` (radians).
function At({ x, y, rot = 0, h = 0, children }) {
  return <group position={w2t(x, y, h)} rotation={[0, rot, 0]}>{children}</group>
}

// --------------------------------------------------------------- furniture
function Desk({ M }) {
  return (
    <group>
      <B m={M.laminate} s={[1.4, 0.04, 0.7]} p={[0, 0.74, 0]} />
      {[-0.66, 0.66].map((x) => <B key={x} m={M.darkSteel} s={[0.05, 0.72, 0.64]} p={[x, 0.36, 0]} />)}
      <B m={M.darkSteel} s={[1.3, 0.35, 0.02]} p={[0, 0.5, -0.3]} />
      {/* monitor, keyboard */}
      <B m={M.black} s={[0.56, 0.34, 0.03]} p={[0.1, 1.0, -0.18]} r={[-0.08, 0, 0]} />
      <B m={M.screen} s={[0.52, 0.3, 0.005]} p={[0.1, 1.0, -0.16]} r={[-0.08, 0, 0]} shadow={false} />
      <B m={M.black} s={[0.06, 0.1, 0.06]} p={[0.1, 0.8, -0.2]} />
      <B m={M.black} s={[0.42, 0.02, 0.14]} p={[0.05, 0.77, 0.1]} />
      <B m={M.paper} s={[0.21, 0.004, 0.3]} p={[-0.45, 0.762, 0.05]} r={[0, 0.3, 0]} shadow={false} />
    </group>
  )
}

function Chair({ M, tipped = false }) {
  return (
    <group rotation={tipped ? [Math.PI / 2 - 0.05, 0, 0.3] : [0, 0, 0]} position={tipped ? [0, 0.26, 0] : [0, 0, 0]}>
      <B m={M.fabric} s={[0.48, 0.08, 0.46]} p={[0, 0.48, 0]} />
      <B m={M.fabric} s={[0.46, 0.5, 0.07]} p={[0, 0.8, 0.22]} r={[0.12, 0, 0]} />
      <C m={M.darkSteel} rt={0.025} h={0.36} p={[0, 0.28, 0]} seg={8} />
      {[0, 1, 2, 3, 4].map((i) => (
        <B key={i} m={M.darkSteel} s={[0.3, 0.03, 0.04]} r={[0, (i * Math.PI * 2) / 5, 0]}
           p={[Math.cos((i * Math.PI * 2) / 5) * 0.15, 0.07, -Math.sin((i * Math.PI * 2) / 5) * 0.15]} />
      ))}
    </group>
  )
}

function FilingCabinet({ M }) {
  return (
    <group>
      <B m={M.paintedGrey} s={[0.46, 1.32, 0.6]} p={[0, 0.66, 0]} />
      {[0.25, 0.58, 0.91, 1.22].map((y) => <B key={y} m={M.darkSteel} s={[0.2, 0.03, 0.02]} p={[0, y, 0.305]} shadow={false} />)}
    </group>
  )
}

function Bookshelf({ M, len = 1.6 }) {
  const books = [0.45, 0.85, 1.25, 1.65]
  return (
    <group>
      <B m={M.wood} s={[len, 1.9, 0.04]} p={[0, 0.95, -0.15]} />
      {[-len / 2, len / 2].map((x) => <B key={x} m={M.wood} s={[0.03, 1.9, 0.34]} p={[x, 0.95, 0]} />)}
      {[0.05, 0.42, 0.82, 1.22, 1.62, 1.9].map((y) => <B key={y} m={M.wood} s={[len, 0.03, 0.34]} p={[0, y, 0]} />)}
      {books.map((y, i) => (
        <B key={y} m={i % 2 ? M.cardboard : M.fabric} s={[len * (0.5 + (i % 3) * 0.12), 0.3, 0.24]} p={[-len * 0.12 + i * 0.05, y - 0.22, 0]} />
      ))}
    </group>
  )
}

function Whiteboard({ M }) {
  return (
    <group>
      <B m={M.chrome} s={[1.8, 1.1, 0.03]} p={[0, 1.45, 0]} />
      <B m={M.white} s={[1.74, 1.04, 0.01]} p={[0, 1.45, 0.02]} shadow={false} />
    </group>
  )
}

function Boxes({ M, n = 3, seed = 1 }) {
  let s = seed
  const r = () => (s = (s * 16807) % 2147483647) / 2147483647
  return Array.from({ length: n }, (_, i) => {
    const w = 0.4 + r() * 0.25
    return <B key={i} m={i % 2 ? M.cardboardDark : M.cardboard} s={[w, 0.3 + r() * 0.15, w * 0.8]}
              p={[(r() - 0.5) * 0.4, 0.18 + Math.floor(i / 2) * 0.36, (r() - 0.5) * 0.3]} r={[0, r() * 0.6, 0]} />
  })
}

// Steel shelving: four uprights, four shelves, cartons.
function Shelving({ M, len = 2, depth = 0.5, seed = 3 }) {
  const levels = [0.1, 0.65, 1.2, 1.75]
  return (
    <group>
      {[-len / 2, len / 2].flatMap((x) => [-depth / 2, depth / 2].map((z) => (
        <B key={`${x}${z}`} m={M.paintedGrey} s={[0.04, 2.0, 0.04]} p={[x, 1.0, z]} />
      )))}
      {levels.map((y, i) => (
        <group key={y}>
          <B m={M.steel} s={[len, 0.03, depth]} p={[0, y, 0]} />
          <group position={[-len / 4, y + 0.02, 0]}><Boxes M={M} n={2} seed={seed + i * 13} /></group>
          {i % 2 === 0 && <group position={[len / 4, y + 0.02, 0]}><Boxes M={M} n={1} seed={seed + i * 29} /></group>}
        </group>
      ))}
    </group>
  )
}

function Pallet({ M, load = true, seed = 5 }) {
  return (
    <group>
      {[-0.5, 0, 0.5].map((x) => <B key={x} m={M.pallet} s={[0.1, 0.1, 1.0]} p={[x, 0.05, 0]} />)}
      {[-0.45, -0.15, 0.15, 0.45].map((z) => <B key={z} m={M.pallet} s={[1.2, 0.03, 0.14]} p={[0, 0.115, z]} />)}
      {load && (
        <>
          <group position={[0, 0.13, 0]}><Boxes M={M} n={4} seed={seed} /></group>
          <B m={M.wrap} s={[1.1, 0.75, 0.95]} p={[0, 0.52, 0]} shadow={false} />
        </>
      )}
    </group>
  )
}

// Pallet rack: orange uprights, blue beams, two loaded levels.
function PalletRack({ M, len = 2.7, depth = 0.8, seed = 7 }) {
  return (
    <group>
      {[-len / 2, len / 2].flatMap((x) => [-depth / 2, depth / 2].map((z) => (
        <B key={`${x}${z}`} m={M.rackOrange} s={[0.08, 2.1, 0.06]} p={[x, 1.05, z]} />
      )))}
      {[0.12, 1.15].map((y) => (
        <group key={y}>
          {[-depth / 2, depth / 2].map((z) => <B key={z} m={M.rackBlue} s={[len, 0.1, 0.05]} p={[0, y, z]} />)}
          <group position={[-0.65, y + 0.06, 0]} scale={[1, 1, 0.78]}><Pallet M={M} seed={seed + y * 10} /></group>
          <group position={[0.65, y + 0.06, 0]} scale={[1, 1, 0.78]}><Pallet M={M} seed={seed + y * 20} load={y < 1} /></group>
        </group>
      ))}
    </group>
  )
}

function Forklift({ M }) {
  return (
    <group>
      <B m={M.yellow} s={[1.5, 0.6, 1.05]} p={[-0.15, 0.55, 0]} />
      <B m={M.darkSteel} s={[0.5, 0.55, 1.0]} p={[-0.75, 0.55, 0]} />
      <B m={M.black} s={[0.45, 0.1, 0.5]} p={[-0.2, 0.9, 0]} />
      <B m={M.black} s={[0.1, 0.4, 0.5]} p={[-0.42, 1.12, 0]} />
      {/* overhead guard */}
      {[[-0.6, -0.45], [-0.6, 0.45], [0.35, -0.45], [0.35, 0.45]].map(([x, z]) => (
        <B key={`${x}${z}`} m={M.black} s={[0.05, 1.3, 0.05]} p={[x, 1.5, z]} />
      ))}
      <B m={M.black} s={[1.0, 0.05, 0.95]} p={[-0.12, 2.15, 0]} />
      {/* mast and forks */}
      {[-0.3, 0.3].map((z) => <B key={z} m={M.darkSteel} s={[0.08, 2.0, 0.08]} p={[0.68, 1.0, z]} />)}
      {[-0.25, 0.25].map((z) => <B key={z} m={M.darkSteel} s={[1.0, 0.04, 0.1]} p={[1.2, 0.08, z]} />)}
      {[[-0.6, 0.55], [-0.6, -0.55], [0.45, 0.55], [0.45, -0.55]].map(([x, z]) => (
        <C key={`${x}${z}`} m={M.rubber} rt={0.26} h={0.2} p={[x, 0.26, z]} r={[Math.PI / 2, 0, 0]} />
      ))}
    </group>
  )
}

// --------------------------------------------------------------- the three decoys
// D1: cast-iron radiator knocked off its wall brackets.
function Radiator({ M }) {
  return (
    <group>
      {Array.from({ length: 12 }, (_, i) => (
        <B key={i} m={M.white} s={[0.055, 0.62, 0.18]} p={[-0.42 + i * 0.077, 0.38, 0]} />
      ))}
      <C m={M.pipe} rt={0.025} h={0.95} p={[0, 0.1, 0]} r={[0, 0, Math.PI / 2]} seg={8} />
      <C m={M.pipe} rt={0.025} h={0.95} p={[0, 0.66, 0]} r={[0, 0, Math.PI / 2]} seg={8} />
      {[-0.4, 0.4].map((x) => <B key={x} m={M.darkSteel} s={[0.05, 0.08, 0.22]} p={[x, 0.04, 0]} />)}
    </group>
  )
}

// D2: diesel engine on a skid, exhaust stack and radiator core.
function Engine({ M }) {
  return (
    <group>
      <B m={M.darkSteel} s={[1.6, 0.12, 0.9]} p={[0, 0.06, 0]} />
      <B m={M.boiler} s={[0.9, 0.6, 0.6]} p={[-0.1, 0.45, 0]} />
      <B m={M.darkSteel} s={[0.7, 0.18, 0.5]} p={[-0.1, 0.85, 0]} />
      {[-0.35, -0.12, 0.11, 0.34].map((x) => <C key={x} m={M.steel} rt={0.04} h={0.12} p={[x - 0.1, 0.99, 0]} seg={8} />)}
      <B m={M.black} s={[0.12, 0.7, 0.75]} p={[0.62, 0.48, 0]} />
      <C m={M.darkSteel} rt={0.22} h={0.08} p={[0.45, 0.45, 0]} r={[0, 0, Math.PI / 2]} />
      <C m={M.pipe} rt={0.05} h={0.9} p={[-0.55, 1.0, 0.2]} seg={10} />
      <C m={M.pipe} rt={0.07} h={0.15} p={[-0.55, 1.45, 0.2]} seg={10} />
    </group>
  )
}

// D3: espresso machine on a coffee cart.
function CoffeeCart({ M }) {
  return (
    <group>
      <B m={M.wood} s={[0.8, 0.04, 0.6]} p={[0, 0.88, 0]} />
      <B m={M.wood} s={[0.76, 0.03, 0.56]} p={[0, 0.3, 0]} />
      {[[-0.37, -0.27], [-0.37, 0.27], [0.37, -0.27], [0.37, 0.27]].map(([x, z]) => (
        <B key={`${x}${z}`} m={M.darkSteel} s={[0.04, 0.86, 0.04]} p={[x, 0.44, z]} />
      ))}
      <B m={M.chrome} s={[0.5, 0.42, 0.42]} p={[0, 1.11, -0.03]} />
      <B m={M.black} s={[0.44, 0.06, 0.12]} p={[0, 1.0, 0.2]} />
      {[-0.1, 0.1].map((x) => <C key={x} m={M.black} rt={0.035} h={0.06} p={[x, 1.08, 0.24]} seg={10} />)}
      <C m={M.white} rt={0.04} rb={0.03} h={0.08} p={[0.12, 0.94, 0.2]} seg={10} />
      <B m={M.cardboard} s={[0.3, 0.2, 0.2]} p={[0, 0.42, 0]} />
    </group>
  )
}

// --------------------------------------------------------------- kitchen
function Counter({ M, len = 3 }) {
  return (
    <group>
      <B m={M.laminate} s={[len, 0.86, 0.6]} p={[0, 0.43, 0]} />
      <B m={M.darkSteel} s={[len + 0.02, 0.04, 0.62]} p={[0, 0.88, 0]} />
      {Array.from({ length: Math.round(len / 0.6) - 1 }, (_, i) => (
        <B key={i} m={M.darkSteel} s={[0.01, 0.7, 0.01]} p={[-len / 2 + (i + 1) * 0.6, 0.45, 0.301]} shadow={false} />
      ))}
      <B m={M.steel} s={[0.6, 0.02, 0.4]} p={[0.5, 0.905, 0]} />
      <C m={M.chrome} rt={0.015} h={0.3} p={[0.5, 1.05, -0.2]} seg={6} />
      <B m={M.laminate} s={[len, 0.7, 0.35]} p={[0, 1.85, -0.12]} />
      <B m={M.white} s={[0.45, 0.28, 0.32]} p={[-0.9, 1.05, -0.05]} />
    </group>
  )
}

function Fridge({ M }) {
  return (
    <group>
      <B m={M.white} s={[0.7, 1.8, 0.68]} p={[0, 0.9, 0]} />
      <B m={M.darkSteel} s={[0.7, 0.01, 0.01]} p={[0, 1.22, 0.345]} shadow={false} />
      <B m={M.chrome} s={[0.03, 0.4, 0.03]} p={[0.28, 1.45, 0.36]} />
      <B m={M.chrome} s={[0.03, 0.4, 0.03]} p={[0.28, 0.85, 0.36]} />
    </group>
  )
}

function Vending({ M }) {
  return (
    <group>
      <B m={M.truckRed} s={[0.9, 1.85, 0.8]} p={[0, 0.925, 0]} />
      <B m={M.vending} s={[0.6, 1.3, 0.01]} p={[-0.1, 1.1, 0.401]} shadow={false} />
      <B m={M.black} s={[0.18, 0.5, 0.01]} p={[0.32, 1.2, 0.401]} shadow={false} />
    </group>
  )
}

// --------------------------------------------------------------- boiler room
function Boiler({ M }) {
  return (
    <group>
      <C m={M.boiler} rt={0.75} h={3} p={[0, 1.0, 0]} r={[0, 0, Math.PI / 2]} seg={28} />
      {[-1.5, 1.5].map((x) => <C key={x} m={M.darkSteel} rt={0.76} h={0.06} p={[x, 1.0, 0]} r={[0, 0, Math.PI / 2]} seg={28} />)}
      {[-0.9, 0.9].map((x) => <B key={x} m={M.darkSteel} s={[0.2, 0.4, 1.1]} p={[x, 0.2, 0]} />)}
      <B m={M.paintedGrey} s={[0.5, 0.8, 0.7]} p={[1.78, 0.9, 0]} />
      <C m={M.pipe} rt={0.12} h={1.3} p={[-1.0, 2.15, 0]} seg={12} />
      <C m={M.copper} rt={0.05} h={1.6} p={[0.4, 1.95, 0.45]} seg={8} />
      <C m={M.white} rt={0.08} h={0.03} p={[1.2, 1.4, 0.5]} r={[Math.PI / 2, 0, 0]} seg={14} />
    </group>
  )
}

// Pipe run along a wall: three lines at different heights, with brackets.
function PipeRun({ M, len }) {
  return (
    <group>
      {[[1.5, 0.09, M.pipe], [1.78, 0.06, M.copper], [1.98, 0.05, M.pipe]].map(([y, r, m]) => (
        <C key={y} m={m} rt={r} h={len} p={[0, y, 0]} r={[0, 0, Math.PI / 2]} seg={10} />
      ))}
      {Array.from({ length: Math.floor(len / 1.5) + 1 }, (_, i) => (
        <B key={i} m={M.darkSteel} s={[0.04, 0.6, 0.12]} p={[-len / 2 + i * 1.5, 1.75, -0.05]} />
      ))}
    </group>
  )
}

function Sign({ lines, w = 0.6, h = 0.3, bg, fg, y = 1.7 }) {
  const map = useMemo(() => signTexture(lines, { w: 256, h: Math.round((256 * h) / w), bg, fg, font: `bold ${Math.round(120 / (lines.length + 1))}px Inter, sans-serif` }), [lines, w, h, bg, fg])
  return (
    <mesh position={[0, y, 0.005]}>
      <planeGeometry args={[w, h]} />
      <meshStandardMaterial map={map} roughness={0.6} />
    </mesh>
  )
}

function Extinguisher({ M }) {
  return (
    <group>
      <C m={M.truckRed} rt={0.08} h={0.5} p={[0, 0.95, 0.1]} />
      <C m={M.black} rt={0.03} h={0.1} p={[0, 1.24, 0.1]} seg={8} />
    </group>
  )
}

// Scattered paper on the floor.
function Papers({ M, n = 6, seed = 9, spread = 1.5 }) {
  let s = seed
  const r = () => (s = (s * 16807) % 2147483647) / 2147483647
  return Array.from({ length: n }, (_, i) => (
    <mesh key={i} material={M.paper} rotation={[-Math.PI / 2, 0, r() * 6]}
          position={[(r() - 0.5) * spread, 0.008 + i * 0.001, (r() - 0.5) * spread]} receiveShadow>
      <planeGeometry args={[0.21, 0.3]} />
    </mesh>
  ))
}

// Painted floor line (sim coordinates), e.g. warehouse lanes.
function FloorLine({ a, b, w = 0.1, color = '#eab308' }) {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1])
  const ang = Math.atan2(b[1] - a[1], b[0] - a[0])
  return (
    <mesh position={w2t((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.006)} rotation={[-Math.PI / 2, 0, ang]} receiveShadow>
      <planeGeometry args={[len, w]} />
      <meshStandardMaterial color={color} roughness={0.7} />
    </mesh>
  )
}

// --------------------------------------------------------------- layout
const N = 0           // back to the north wall, facing south
const S = Math.PI     // back to the south wall
const W = Math.PI / 2 // back to the west wall, facing east
const E = -Math.PI / 2

// Decoy heat sources as the real objects they are, wherever the floorplan puts them.
const DECOY = { radiator: Radiator, engine: Engine, 'coffee machine': CoffeeCart }
function Decoys({ fp, M }) {
  return (fp.decoys ?? []).map((d, i) => {
    const Obj = DECOY[d.label]
    return Obj ? <At key={d.id} x={d.pos[0]} y={d.pos[1]} rot={0.15 + i * 0.1}><Obj M={M} /></At> : null
  })
}

// Furniture is laid out by hand for the demo building; other maps get the decoys and the
// collapse dressing (debris, damage) without furniture.
// --------------------------------------------------------------- any building
// Furniture for a floor plan we have never seen: each room is read from its name and
// furnished along its walls (desks and cabinets in offices, shelving and pallets in storage,
// a counter in break rooms, boilers in plant rooms, nothing in corridors), with a default
// for rooms we cannot classify. Everything hugs a wall (centre <= 0.5 m from the wall line),
// stays 1.2 m clear of door openings and 0.8 m from corners, so no robot path is touched.
const KIND = [
  [/corridor|hall|spine|stair|lobby|entry|passage/i, 'corridor'],
  [/office|admin|reception|loading office|meeting|ward|clinic|theatre|radiology/i, 'office'],
  [/storage|store|warehouse|stock|cage|supply|lab|pharm|archive/i, 'storage'],
  [/break|kitchen|canteen|cafe|waiting|staff/i, 'break'],
  [/boiler|plant|mechanical|utility|electrical|server/i, 'plant'],
]
function roomKind(name = '') {
  return (KIND.find(([re]) => re.test(name)) ?? [null, 'default'])[1]
}
function prng(seed) {
  let s = (seed % 2147483647) || 1
  return () => (s = (s * 16807) % 2147483647) / 2147483647
}
// Free spots along one side of a room, away from doors and corners. side: 'N' | 'S' | 'E' | 'W'.
function wallSlots(room, side, doors, step, inset) {
  const xs = room.poly.map((p) => p[0])
  const ys = room.poly.map((p) => p[1])
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const horiz = side === 'N' || side === 'S'
  const lo = (horiz ? x0 : y0) + 0.8
  const hi = (horiz ? x1 : y1) - 0.8
  const out = []
  for (let t = lo + step / 2; t <= hi - step / 2; t += step) {
    const x = horiz ? t : side === 'W' ? x0 + inset : x1 - inset
    const y = horiz ? (side === 'S' ? y0 + inset : y1 - inset) : t
    if (doors.some((d) => Math.hypot(d.at[0] - x, d.at[1] - y) < 1.2 + step / 2)) continue
    out.push({ x, y, rot: side === 'N' ? N : side === 'S' ? S : side === 'W' ? W : E })
  }
  return out
}
function GenericRoom({ room, fp, M }) {
  const kind = roomKind(room.name)
  if (kind === 'corridor') return null
  const xs = room.poly.map((p) => p[0])
  const ys = room.poly.map((p) => p[1])
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const r = prng(Math.round(x0 * 7 + y0 * 13 + x1 * 3 + y1 * 5) + 101)
  const doors = fp.doors ?? []
  const sides = ['N', 'E', 'S', 'W'].sort(() => r() - 0.5)
  const items = []
  const take = (side, step, inset, n, make) => {
    const slots = wallSlots(room, side, doors, step, inset)
    for (let i = 0; i < n && slots.length; i++) {
      const s = slots.splice(Math.floor(r() * slots.length), 1)[0]
      items.push({ ...s, el: make(i) })
    }
  }
  const area = (x1 - x0) * (y1 - y0)
  if (kind === 'office') {
    take(sides[0], 1.8, 0.45, Math.max(1, Math.round(area / 30)), (i) => <Desk M={M} key={`d${i}`} />)
    take(sides[1], 0.7, 0.4, 2, (i) => <FilingCabinet M={M} key={`c${i}`} />)
    take(sides[2], 2.0, 0.3, 1, () => <Bookshelf M={M} len={1.6} />)
    items.push({ x: (x0 + x1) / 2 + (r() - 0.5) * 2, y: (y0 + y1) / 2 + (r() - 0.5) * 2, rot: 0, el: <Papers M={M} n={6} seed={Math.round(x0 * 11 + y0)} /> })
  } else if (kind === 'storage') {
    take(sides[0], 2.2, 0.42, Math.max(1, Math.round(area / 25)), (i) => <Shelving M={M} seed={i * 7 + 31} />)
    take(sides[1], 2.2, 0.42, Math.max(1, Math.round(area / 40)), (i) => <Shelving M={M} seed={i * 11 + 61} />)
    if (area > 80) take(sides[2], 3.0, 0.5, 1, () => <PalletRack M={M} seed={83} />)
    else take(sides[2], 1.4, 0.5, 1, () => <Pallet M={M} seed={91} />)
  } else if (kind === 'break') {
    take(sides[0], 3.2, 0.42, 1, () => <Counter M={M} len={2.8} />)
    take(sides[1], 1.0, 0.45, 1, () => <Fridge M={M} />)
    take(sides[2], 1.2, 0.5, 1, () => <Vending M={M} />)
    take(sides[3], 0.8, 0.5, 2, (i) => <Chair M={M} tipped={i === 0} />)
  } else if (kind === 'plant') {
    take(sides[0], 3.4, 0.9, Math.max(1, Math.round(area / 60)), () => <Boiler M={M} />)
    const len = Math.min(x1 - x0, y1 - y0) - 1.5
    items.push({ x: (x0 + x1) / 2, y: y0 + 0.3, rot: S, el: <PipeRun M={M} len={Math.max(2, (x1 - x0) - 1.5)} /> })
    if (len > 3) items.push({ x: x0 + 0.25, y: (y0 + y1) / 2, rot: W, el: <PipeRun M={M} len={(y1 - y0) - 1.5} /> })
  } else {
    // unknown room: a desk, a shelf and a cabinet is enough to say "people used this"
    take(sides[0], 1.8, 0.45, 1, () => <Desk M={M} />)
    take(sides[1], 2.2, 0.42, 1, () => <Shelving M={M} seed={47} />)
    take(sides[2], 0.7, 0.4, 1, () => <FilingCabinet M={M} />)
  }
  return items.map((it, i) => <At key={i} x={it.x} y={it.y} rot={it.rot}>{it.el}</At>)
}

// ?generic=1 shows the generic furnishing on the demo building too (to compare)
const FORCE_GENERIC = (() => { try { return new URLSearchParams(location.search).has('generic') } catch { return false } })()

export function Interior({ fp, cold: isCold = false }) {
  const M = isCold ? cold() : mats()
  if (fp?.id !== 'collapse_01' || FORCE_GENERIC) {
    return (
      <group>
        <Decoys fp={fp} M={M} />
        {(fp?.rooms ?? []).map((room) => <GenericRoom key={room.id} room={room} fp={fp} M={M} />)}
      </group>
    )
  }
  return (
    <group>
      <Decoys fp={fp} M={M} />
      {/* Office A */}
      <At x={2.2} y={29.5} rot={N}><Desk M={M} /></At>
      <At x={7.4} y={29.5} rot={N}><Desk M={M} /></At>
      <At x={2.4} y={28.75} rot={N}><Chair M={M} /></At>
      <At x={7.0} y={28.5} rot={N + 0.6}><Chair M={M} tipped /></At>
      <At x={0.45} y={21.6} rot={W}><FilingCabinet M={M} /></At>
      <At x={0.45} y={22.1} rot={W}><FilingCabinet M={M} /></At>
      <At x={9.72} y={23} rot={E}><Bookshelf M={M} /></At>
      <At x={4} y={23.5}><Papers M={M} n={7} seed={11} spread={2.2} /></At>
      {/* Office B */}
      <At x={19.5} y={21.6} rot={E}><Desk M={M} /></At>
      <At x={19.5} y={25.6} rot={E}><Desk M={M} /></At>
      <At x={18.75} y={21.4} rot={E}><Chair M={M} /></At>
      <At x={18.5} y={26.2} rot={E + 1}><Chair M={M} tipped /></At>
      <At x={10.11} y={23.5} rot={W}><Whiteboard M={M} /></At>
      {/* bookshelf toppled face down off the north wall */}
      <At x={12.6} y={29.4} rot={N}><group rotation={[Math.PI / 2, 0, 0]} position={[0, 0.17, -0.2]}><Bookshelf M={M} len={1.8} /></group></At>
      <At x={16.5} y={21}><Papers M={M} n={5} seed={23} /></At>
      {/* Break room */}
      <At x={25.5} y={29.55} rot={N}><Counter M={M} len={3.6} /></At>
      <At x={31.45} y={29.45} rot={N}><Fridge M={M} /></At>
      <At x={20.58} y={20.2} rot={W}><Vending M={M} /></At>
      <At x={23.4} y={24.6} rot={1.2}><Chair M={M} tipped /></At>
      {/* Storage */}
      {[3, 5.2, 9.6].map((y, i) => <At key={y} x={0.42} y={y} rot={W}><Shelving M={M} seed={31 + i * 7} /></At>)}
      {[3.4, 9.4].map((x, i) => <At key={x} x={x} y={0.42} rot={S}><Shelving M={M} seed={61 + i * 7} /></At>)}
      <At x={11.4} y={12.35}><Boxes M={M} n={5} seed={71} /></At>
      <At x={10.8} y={0.9}><Boxes M={M} n={3} seed={79} /></At>
      {/* Boiler room (gas no-go: robots never enter) */}
      <At x={15.5} y={5.2} rot={Math.PI / 2}><Boiler M={M} /></At>
      <At x={20.5} y={5.2} rot={Math.PI / 2}><Boiler M={M} /></At>
      <At x={18} y={0.3} rot={S}><PipeRun M={M} len={11.4} /></At>
      <At x={12.25} y={6.5} rot={W}><PipeRun M={M} len={12.4} /></At>
      {/* Loading office */}
      <At x={31.5} y={10.2} rot={E}><Desk M={M} /></At>
      <At x={30.4} y={9.5} rot={E + 0.8}><Chair M={M} tipped /></At>
      <At x={24.45} y={2} rot={W}><FilingCabinet M={M} /></At>
      <At x={24.9} y={3.4} rot={W + 0.3}><group rotation={[0, 0, -Math.PI / 2]} position={[0.66, 0.3, 0]}><FilingCabinet M={M} /></group></At>
      <At x={27} y={8}><Papers M={M} n={6} seed={41} /></At>
      {/* Corridor */}
      <At x={8} y={13.1} rot={S}><Extinguisher M={M} /></At>
      <At x={30} y={16.9} rot={N}><Extinguisher M={M} /></At>
      <At x={19.4} y={13.11} rot={S}><Sign lines={['DANGER', 'GAS LEAK']} bg="#facc15" fg="#111111" w={0.62} h={0.42} /></At>
      <At x={0.16} y={16.9} rot={W}><Sign lines={['EXIT']} bg="#15803d" fg="#ffffff" w={0.5} h={0.2} y={2.05} /></At>
      {/* Warehouse */}
      <At x={39.45} y={16.5} rot={E}><PalletRack M={M} seed={83} /></At>
      <At x={33.3} y={1.6} rot={0}><Forklift M={M} /></At>
      <At x={32.85} y={29.2} rot={W}><Pallet M={M} seed={91} /></At>
      <At x={39.6} y={27.4} rot={E}><Shelving M={M} len={2.4} depth={0.45} seed={97} /></At>
      {!isCold && (
        <>
          <FloorLine a={[32.6, 9.6]} b={[32.6, 20.6]} />
          <FloorLine a={[38.4, 9.6]} b={[38.4, 13.6]} />
          <FloorLine a={[32.6, 9.6]} b={[36, 9.6]} />
        </>
      )}
    </group>
  )
}

// --------------------------------------------------------------- outside
// Asphalt lot around the building: parking bays, kerb, a line of cones by the entrance.
export function Lot({ W: w, H: h }) {
  const M = mats()
  const surf = useMemo(() => tiledSet(materials().asphalt, 260 / 3, 220 / 3), [w, h])
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(w / 2 - 5, h / 2, -0.01)} receiveShadow>
        <planeGeometry args={[260, 220]} />
        <meshStandardMaterial {...surf} color="#7c8086" roughness={0.92} normalScale={[0.5, 0.5]} />
      </mesh>
      {/* concrete apron around the walls */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(w / 2, h / 2, -0.004)} receiveShadow>
        <planeGeometry args={[w + 2.4, h + 2.4]} />
        <meshStandardMaterial color="#4a4e53" roughness={0.9} />
      </mesh>
      {Array.from({ length: 9 }, (_, i) => (
        <FloorLine key={i} a={[-13, 1 + i * 3.5]} b={[-8.5, 1 + i * 3.5]} w={0.12} color="#d9d9d4" />
      ))}
      <FloorLine a={[-7.2, -2]} b={[-7.2, 32]} w={0.12} color="#eab308" />
      {[[-0.8, 11.6], [-0.8, 12.6], [-0.8, 17.4], [-0.8, 18.4], [-6.4, 21.4]].map(([x, y]) => (
        <At key={`${x}${y}`} x={x} y={y}>
          <C m={M.cone} rt={0.03} rb={0.15} h={0.55} p={[0, 0.3, 0]} seg={12} />
          <B m={M.cone} s={[0.36, 0.04, 0.36]} p={[0, 0.02, 0]} />
          <C m={M.white} rt={0.08} rb={0.1} h={0.08} p={[0, 0.36, 0]} seg={12} shadow={false} />
        </At>
      ))}
    </group>
  )
}

// Command post: a response truck parked by the entrance with a telescoping antenna mast
// at the post's radio position. Light bar flashes; the beacon on the mast is where radio
// links and delivery pulses end (MAST_H).
export function CommandPost({ pos, entry, cold: isCold = false }) {
  const M = isCold ? cold() : mats()
  const red = useRef()
  const blue = useRef()
  useFrame(({ clock }) => {
    const t = clock.elapsedTime * 2.2
    if (red.current) red.current.emissiveIntensity = Math.sin(t * Math.PI) > 0 ? 3 : 0.1
    if (blue.current) blue.current.emissiveIntensity = Math.sin(t * Math.PI) > 0 ? 0.1 : 3
  })
  const livery = useMemo(() => signTexture(['INCIDENT COMMAND'], { w: 512, h: 64, bg: '#b91c1c', fg: '#ffffff', font: 'bold 40px Inter, sans-serif' }), [])
  const [x, y] = pos
  // park the truck beside the mast, parallel to the wall, on the side away from the building
  const [ex, ey] = entry ?? [x + 1, y]
  const dl = Math.hypot(ex - x, ey - y) || 1
  const dx = (ex - x) / dl
  const dy = (ey - y) / dl
  const truck = [x - dx * 1.18 - dy * 1.8, y - dy * 1.18 + dx * 1.8]
  const heading = Math.atan2(dx, -dy)
  return (
    <group>
      {/* truck: box body behind, cab facing north */}
      <At x={truck[0]} y={truck[1]} rot={heading}>
        <B m={M.darkSteel} s={[6.6, 0.3, 1.6]} p={[-0.1, 0.62, 0]} />
        <B m={M.truckWhite} s={[4.6, 2.3, 2.3]} p={[-1.1, 2.0, 0]} />
        {!isCold && [-1.151, 1.151].map((z) => (
          <mesh key={z} position={[-1.1, 1.55, z]} rotation={[0, z > 0 ? 0 : Math.PI, 0]}>
            <planeGeometry args={[4.4, 0.55]} />
            <meshStandardMaterial map={livery} roughness={0.4} />
          </mesh>
        ))}
        <B m={M.truckWhite} s={[1.9, 1.75, 2.2]} p={[2.25, 1.6, 0]} />
        <B m={M.glass} s={[0.05, 0.75, 2.0]} p={[3.2, 2.0, 0]} r={[0, 0, 0.12]} />
        {[-1.101, 1.101].map((z) => <B key={z} m={M.glass} s={[0.8, 0.6, 0.01]} p={[2.5, 2.05, z]} shadow={false} />)}
        <B m={M.chrome} s={[0.1, 0.3, 2.2]} p={[3.22, 0.95, 0]} />
        {/* light bar */}
        <mesh position={[2.3, 2.55, -0.45]}><boxGeometry args={[0.3, 0.14, 0.8]} />
          <meshStandardMaterial ref={red} color="#ff3030" emissive="#ff1a1a" toneMapped={false} /></mesh>
        <mesh position={[2.3, 2.55, 0.45]}><boxGeometry args={[0.3, 0.14, 0.8]} />
          <meshStandardMaterial ref={blue} color="#3060ff" emissive="#1a4dff" toneMapped={false} /></mesh>
        {/* roof dish and ladder */}
        <C m={M.white} rt={0.5} rb={0.12} h={0.25} p={[-2.3, 3.4, 0]} r={[0.5, 0, 0]} seg={20} />
        {[-3.0, -2.6, -2.2].map((xx) => <B key={xx} m={M.chrome} s={[0.03, 0.03, 0.5]} p={[xx, 2.0, -1.17]} r={[Math.PI / 2, 0, 0]} />)}
        {[[-3.0, 1.0], [-1.8, 1.0], [2.3, 1.0], [-3.0, -1.0], [-1.8, -1.0], [2.3, -1.0]].map(([xx, z]) => (
          <group key={`${xx}${z}`}>
            <C m={M.rubber} rt={0.47} h={0.32} p={[xx, 0.47, z]} r={[Math.PI / 2, 0, 0]} seg={20} />
            <C m={M.chrome} rt={0.22} h={0.33} p={[xx, 0.47, z]} r={[Math.PI / 2, 0, 0]} seg={12} />
          </group>
        ))}
      </At>
      {/* telescoping mast with antennas and the amber beacon */}
      <At x={x} y={y}>
        <C m={M.darkSteel} rt={0.35} rb={0.42} h={0.1} p={[0, 0.05, 0]} seg={6} />
        <C m={M.steel} rt={0.07} rb={0.09} h={1.8} p={[0, 0.9, 0]} seg={10} />
        <C m={M.steel} rt={0.055} rb={0.065} h={1.6} p={[0, 2.5, 0]} seg={10} />
        <C m={M.steel} rt={0.04} rb={0.05} h={1.0} p={[0, 3.6, 0]} seg={10} />
        <B m={M.darkSteel} s={[0.7, 0.05, 0.05]} p={[0, MAST_H - 0.15, 0]} />
        {[-0.33, 0.33].map((xx) => <C key={xx} m={M.white} rt={0.018} h={0.8} p={[xx, MAST_H + 0.2, 0]} seg={6} />)}
        <B m={M.white} s={[0.14, 0.5, 0.06]} p={[0, MAST_H - 0.45, 0.1]} />
        <mesh position={[0, MAST_H + 0.05, 0]}>
          <sphereGeometry args={[0.14, 16, 16]} />
          <meshStandardMaterial color="#f59e0b" emissive="#f59e0b" emissiveIntensity={isCold ? 0 : 2.5} toneMapped={false} />
        </mesh>
      </At>
    </group>
  )
}

// --------------------------------------------------------------- gas leak
// Hazard zone: yellow and black tape on the floor along its edge, and a slow drifting
// haze of gas inside it.
export function GasLeak({ hazard }) {
  const xs = hazard.poly.map((p) => p[0])
  const ys = hazard.poly.map((p) => p[1])
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const puffs = useMemo(() => {
    let s = 4242
    const r = () => (s = (s * 16807) % 2147483647) / 2147483647
    return Array.from({ length: 14 }, () => ({
      x: x0 + 0.8 + r() * (x1 - x0 - 1.6), y: y0 + 0.8 + r() * (y1 - y0 - 1.6),
      h: 0.4 + r() * 1.2, s: 2.2 + r() * 2.2, ph: r() * 6,
    }))
  }, [x0, x1, y0, y1])
  const group = useRef()
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    group.current?.children.forEach((sp, i) => {
      const p = puffs[i]
      sp.position.set(p.x + Math.sin(t * 0.15 + p.ph) * 0.8, p.h + Math.sin(t * 0.3 + p.ph) * 0.2, -(p.y + Math.cos(t * 0.12 + p.ph) * 0.8))
      sp.material.opacity = 0.1 + 0.05 * Math.sin(t * 0.4 + p.ph)
    })
  })
  const tape = useMemo(() => {
    const t = materials().tape.map
    return [[x1 - x0, 'h'], [y1 - y0, 'v']].map(([len]) => {
      const m = t.clone()
      m.repeat.set(len / 0.5, 1)
      m.needsUpdate = true
      return m
    })
  }, [x0, x1, y0, y1])
  const edges = [
    [[x0, y0], [x1, y0], 0], [[x0, y1], [x1, y1], 0], [[x0, y0], [x0, y1], 1], [[x1, y0], [x1, y1], 1],
  ]
  return (
    <group>
      {edges.map(([a, b, k], i) => {
        const len = Math.hypot(b[0] - a[0], b[1] - a[1])
        const ang = Math.atan2(b[1] - a[1], b[0] - a[0])
        return (
          <mesh key={i} position={w2t((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.007)} rotation={[-Math.PI / 2, 0, ang]} receiveShadow>
            <planeGeometry args={[len, 0.14]} />
            <meshStandardMaterial map={tape[k]} roughness={0.6} />
          </mesh>
        )
      })}
      <group ref={group}>
        {puffs.map((p, i) => (
          <sprite key={i} scale={[p.s, p.s * 0.6, 1]}>
            <spriteMaterial map={materials().puff} color="#c5d86d" transparent opacity={0.12} depthWrite={false} />
          </sprite>
        ))}
      </group>
    </group>
  )
}
