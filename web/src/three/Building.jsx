import { useMemo } from 'react'
import * as THREE from 'three'
import { useSim } from '../store'
import { WALL_H, w2t } from './util'
import { materials, tiledSet } from './textures'
import Baked from './Baked'
import Debris from './Debris'
import { CommandPost, GasLeak, Interior, Lot } from './Props'
import { CollapseLive, CollapseStatic, WallDetails, holedWallGeometry, wallDamage } from './Collapse'
import { DisasterLive, DisasterStatic } from './Disaster'
import FracturedWalls from './Fracture'

// Thermal palette for the robot's-eye view: everything cold reads as deep blue.
const COLD = { floor: '#070b1f', wall: '#1d3a8a', wallGlow: '#0b1d5c' }
// Blueprint palette for the Command inset: the public floorplan only, no truth rubble.
const PRINT = { floor: '#0a1830', wall: '#7fb2ff', wallGlow: '#1e40af' }

const THICK = { concrete: 0.3, brick: 0.2, drywall: 0.12, metal: 0.06 }
const LINTEL = 2.02 // m, top of a door opening
const CAP = '#b8b0a3' // wall tops: the cut section, light so the plan reads from far away

// Surface per wall material, tiled by real size (1 tile = 2 m of concrete, 1.6 m of brick).
function wallSurface(material, len, h) {
  const m = materials()
  if (material === 'brick') return { ...tiledSet(m.brick, len / 1.6, h / 1.6), roughness: 0.92, color: '#d9d2cc' }
  if (material === 'drywall') return { ...tiledSet(m.plaster, len / 2, 1), roughness: 0.9, color: '#ffffff' }
  return { ...tiledSet(m.concrete, len / 2, h / 2), roughness: 0.88, color: '#c9c6c0' }
}

// Same surfaces for an extruded wall, whose UVs are in meters (repeat = 1 / tile size).
function holedSurface(material) {
  const m = materials()
  if (material === 'brick') return { ...tiledSet(m.brick, 1 / 1.6, 1 / 1.6), roughness: 0.92, color: '#d9d2cc' }
  if (material === 'drywall') return { ...tiledSet(m.plaster, 0.5, 1 / WALL_H), roughness: 0.9, color: '#ffffff' }
  return { ...tiledSet(m.concrete, 0.5, 0.5), roughness: 0.88, color: '#c9c6c0' }
}

function SolidWall({ len, thick, material, mode, damage }) {
  const holed = mode === 'plain' && damage && (damage.windows.length || damage.breaches.length)
  const surf = useMemo(() => (mode !== 'plain' ? null : holed ? holedSurface(material) : wallSurface(material, len + thick, WALL_H)),
    [mode, material, len, thick, holed])
  const geom = useMemo(() => (holed ? holedWallGeometry(len + thick, thick, damage) : null), [holed, len, thick, damage])
  if (mode !== 'plain') {
    const p = mode === 'blueprint' ? PRINT : COLD
    return (
      <mesh position={[0, WALL_H / 2, 0]}>
        <boxGeometry args={[len + thick, WALL_H, thick]} />
        <meshStandardMaterial color={p.wall} emissive={p.wallGlow} roughness={0.9} />
      </mesh>
    )
  }
  return (
    <>
      {geom ? (
        <mesh geometry={geom} castShadow receiveShadow>
          <meshStandardMaterial {...surf} normalScale={[0.8, 0.8]} />
        </mesh>
      ) : (
        <mesh position={[0, WALL_H / 2, 0]} castShadow receiveShadow>
          <boxGeometry args={[len + thick, WALL_H, thick]} />
          <meshStandardMaterial {...surf} normalScale={[0.8, 0.8]} />
        </mesh>
      )}
      <mesh position={[0, WALL_H + 0.012, 0]} receiveShadow>
        <boxGeometry args={[len + thick + 0.01, 0.024, thick + 0.02]} />
        <meshStandardMaterial color={CAP} roughness={0.8} />
      </mesh>
    </>
  )
}

// Steel storage cage: chain-link panels between square posts, with a top rail.
// Radio-wise it is still a metal wall; to the eye you can see through it.
function FenceWall({ len, mode }) {
  const fence = useMemo(() => tiledSet(materials().fence, len / 0.5, WALL_H / 0.5), [len])
  if (mode !== 'plain') return <SolidWall len={len} thick={0.06} material="metal" mode={mode} />
  const posts = Math.max(2, Math.round(len / 2) + 1)
  const steel = { color: '#8c939b', metalness: 0.8, roughness: 0.38 }
  return (
    <>
      <mesh position={[0, WALL_H / 2, 0]} castShadow>
        <planeGeometry args={[len, WALL_H]} />
        <meshStandardMaterial {...steel} alphaMap={fence.alphaMap} alphaTest={0.5} side={THREE.DoubleSide} />
      </mesh>
      {Array.from({ length: posts }, (_, i) => (
        <mesh key={i} position={[-len / 2 + (i * len) / (posts - 1), WALL_H / 2, 0]} castShadow>
          <boxGeometry args={[0.07, WALL_H, 0.07]} />
          <meshStandardMaterial {...steel} color="#6b7280" />
        </mesh>
      ))}
      <mesh position={[0, WALL_H, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.03, 0.03, len, 8]} />
        <meshStandardMaterial {...steel} />
      </mesh>
      <mesh position={[0, 0.04, 0]}>
        <boxGeometry args={[len, 0.08, 0.05]} />
        <meshStandardMaterial {...steel} color="#4b5563" />
      </mesh>
    </>
  )
}

function Gate({ width }) {
  const fence = useMemo(() => tiledSet(materials().fence, width / 0.5, WALL_H / 0.5), [width])
  const steel = { color: '#8c939b', metalness: 0.8, roughness: 0.38 }
  return (
    <group position={[-width / 2, 0, 0]}>
      <mesh position={[0, WALL_H / 2, 0]} castShadow>
        <planeGeometry args={[width, WALL_H - 0.1]} />
        <meshStandardMaterial {...steel} alphaMap={fence.alphaMap} alphaTest={0.5} side={THREE.DoubleSide} />
      </mesh>
      {[-width / 2, width / 2].map((x) => (
        <mesh key={x} position={[x, WALL_H / 2, 0]}><boxGeometry args={[0.04, WALL_H - 0.1, 0.04]} />
          <meshStandardMaterial {...steel} /></mesh>
      ))}
    </group>
  )
}

// Wall-local frame for a wall segment: centered, x along the wall.
function wallFrame(w) {
  const [ax, ay] = w.a
  const [bx, by] = w.b
  return { pos: w2t((ax + bx) / 2, (ay + by) / 2, 0), ang: Math.atan2(by - ay, bx - ax), len: Math.hypot(bx - ax, by - ay) }
}

// Window frames, glass, breach rubble and cracks for every damaged wall (static: baked).
function WallDamageLayer({ walls, damage }) {
  return walls.map((w, i) => {
    if (!damage[i]) return null
    const f = wallFrame(w)
    return (
      <group key={i} position={f.pos} rotation={[0, f.ang, 0]}>
        <WallDetails damage={damage[i]} thick={THICK[w.material] ?? 0.2} />
      </group>
    )
  })
}

function Walls({ walls, mode, damage, size }) {
  // Reality: every masonry wall is drawn fractured (one merged mesh per material); the
  // cage stays a fence. Command, thermal and blueprint keep the intact slabs.
  const fractured = mode === 'plain' && damage
  return (
    <>
      {fractured && <FracturedWalls walls={walls} damage={damage} size={size} />}
      {walls.map((w, i) => {
        if (fractured && w.material !== 'metal') return null
        return <WallSegment key={i} w={w} mode={mode} damage={damage?.[i]} />
      })}
    </>
  )
}

function WallSegment({ w, mode, damage }) {
  const [ax, ay] = w.a
  const [bx, by] = w.b
  const len = Math.hypot(bx - ax, by - ay)
  const ang = Math.atan2(by - ay, bx - ax)
  const thick = THICK[w.material] ?? 0.2
  return (
    <group position={w2t((ax + bx) / 2, (ay + by) / 2, 0)} rotation={[0, ang, 0]}>
      {w.material === 'metal'
        ? <FenceWall len={len} mode={mode} />
        : <SolidWall len={len} thick={thick} material={w.material} mode={mode} damage={damage} />}
    </group>
  )
}

// --------------------------------------------------------------- doors
// The wall that ends at this door edge decides how thick the frame is.
function wallAt(walls, x, y) {
  return walls.find((w) => [w.a, w.b].some(([px, py]) => Math.hypot(px - x, py - y) < 0.3))
}

function Door({ door, walls }) {
  const [x, y] = door.at
  const along = door.axis === 'x' ? 0 : -Math.PI / 2 // gap runs along sim x or sim y
  const half = door.width / 2
  const w = wallAt(walls, door.axis === 'x' ? x - half : x, door.axis === 'x' ? y : y - half)
  const thick = (THICK[w?.material] ?? 0.2) + 0.04
  if (w?.material === 'metal') {
    // cage gate: a chain-link leaf standing open against the fence
    return (
      <group position={w2t(x, y, 0)} rotation={[0, along, 0]}>
        <group position={[-half, 0, 0.08]} rotation={[0, Math.PI * 0.92, 0]}>
          <Gate width={door.width} />
        </group>
      </group>
    )
  }
  const entrance = door.width >= 1.8
  const broken = door.state === 'broken'
  const wood = { color: '#7a5636', roughness: 0.7 }
  const frame = { color: '#3d434a', roughness: 0.5, metalness: 0.5 }
  return (
    <group position={w2t(x, y, 0)} rotation={[0, along, 0]}>
      {/* jambs and lintel */}
      {[-half, half].map((s) => (
        <mesh key={s} position={[s, LINTEL / 2, 0]} castShadow>
          <boxGeometry args={[0.07, LINTEL, thick]} />
          <meshStandardMaterial {...frame} />
        </mesh>
      ))}
      <mesh position={[0, (LINTEL + WALL_H) / 2, 0]} rotation={[0, 0, broken ? 0.06 : 0]} castShadow receiveShadow>
        <boxGeometry args={[door.width + 0.14, WALL_H - LINTEL, thick - 0.02]} />
        <meshStandardMaterial {...frame} color="#2f3439" />
      </mesh>
      {entrance ? (
        // roll-up shutter wound into its housing above the opening
        <mesh position={[0, WALL_H - 0.14, 0.24]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.16, 0.16, door.width + 0.1, 16]} />
          <meshStandardMaterial color="#9aa1a8" metalness={0.7} roughness={0.35} />
        </mesh>
      ) : broken ? (
        // door torn off its hinges, lying flat in the doorway: robots drive over it
        <mesh position={[0.15, 0.035, thick / 2 + 0.75]} rotation={[-Math.PI / 2, 0, 0.5]} castShadow receiveShadow>
          <boxGeometry args={[door.width - 0.15, 2.0, 0.045]} />
          <meshStandardMaterial {...wood} color="#5e4630" />
        </mesh>
      ) : (
        // swung right open, flat against the wall
        <mesh position={[-half - (door.width - 0.1) / 2, (LINTEL - 0.02) / 2, thick / 2 + 0.04]} castShadow>
          <boxGeometry args={[door.width - 0.1, LINTEL - 0.02, 0.045]} />
          <meshStandardMaterial {...wood} />
        </mesh>
      )}
    </group>
  )
}

// --------------------------------------------------------------- floors
const FLOOR_BY_ROOM = [
  [/office [ab]/i, 'carpet', 2, '#a7b0c4'],
  [/break|corridor/i, 'vinyl', 1.2, '#e8e2d6'],
]

function RoomFloor({ room }) {
  const xs = room.poly.map((p) => p[0])
  const ys = room.poly.map((p) => p[1])
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const kind = FLOOR_BY_ROOM.find(([re]) => re.test(room.name))
  const surf = useMemo(() => (kind ? tiledSet(materials()[kind[1]], (x1 - x0) / kind[2], (y1 - y0) / kind[2]) : null),
    [kind, x0, x1, y0, y1])
  if (!kind) return null
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t((x0 + x1) / 2, (y0 + y1) / 2, 0.004)} receiveShadow>
      <planeGeometry args={[x1 - x0, y1 - y0]} />
      <meshStandardMaterial {...surf} color={kind[3]} roughness={kind[1] === 'carpet' ? 1 : 0.55} normalScale={[0.6, 0.6]} />
    </mesh>
  )
}

// Polished concrete slab under everything, 4 m saw-cut panels.
function Slab({ W, H }) {
  const surf = useMemo(() => tiledSet(materials().floor, W / 2.5, H / 2.5), [W, H])
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, 0)} receiveShadow>
      <planeGeometry args={[W, H]} />
      <meshStandardMaterial {...surf} color="#e2e2e0" roughness={0.9} metalness={0} normalScale={[0.9, 0.9]} />
    </mesh>
  )
}

const NO_RUBBLE = []
const staticCache = new WeakMap()
function staticRubble(fp) {
  if (!staticCache.has(fp)) staticCache.set(fp, (fp.rubble ?? NO_RUBBLE).filter((r) => !r.dynamic))
  return staticCache.get(fp)
}

// `props`: furniture and decoy objects (Reality only; the command post's floorplan has none).
// `lite`: the robot camera's copy (indoors only: no outside ruins, smoke or airborne dust).
export default function Building({ thermal = false, blueprint = false, props = true, lite = false }) {
  const fp = useSim((s) => s.floorplan)
  const perf = useSim((s) => s.perf)
  const mode = blueprint ? 'blueprint' : thermal ? 'thermal' : 'plain'
  // collapse damage is truth: Reality panes only (the Command pane keeps the intact plan)
  const damage = useMemo(() => (fp && props && mode === 'plain' ? wallDamage(fp) : null), [fp, props, mode])
  if (!fp) return null
  const [W, H] = fp.size
  const [cx, cy] = fp.command_post.pos
  return (
    <group>
      {mode === 'plain' ? <Lot W={W} H={H} /> : (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, -0.01)}>
          <planeGeometry args={[W + 30, H + 30]} />
          <meshStandardMaterial color={blueprint ? PRINT.floor : COLD.floor} roughness={1} />
        </mesh>
      )}
      {mode === 'plain' && <Slab W={W} H={H} />}
      {mode === 'plain' && fp.rooms.map((r) => <RoomFloor key={r.id} room={r} />)}
      <Walls walls={fp.walls} mode={mode} damage={damage} size={fp.size} />
      {/* aftershock walls are truth geometry: Reality panes only, never Command or the inset */}
      {props && fp.dynamic_walls?.length > 0 && <Walls walls={fp.dynamic_walls} mode={mode} />}
      <Baked deps={[fp, mode, props]}>
        {mode === 'plain' && (fp.doors ?? []).map((d, i) => <Door key={i} door={d} walls={fp.walls} />)}
        {/* rubble that fell during the run (R key, aftershock) is truth: Reality panes only */}
        {!blueprint && <Debris rubble={props ? fp.rubble ?? NO_RUBBLE : staticRubble(fp)} cold={thermal} />}
        {props && !blueprint && <Interior fp={fp} cold={thermal} />}
        {!blueprint && <CommandPost pos={[cx, cy]} entry={fp.entry} cold={thermal} />}
        {damage && <WallDamageLayer walls={fp.walls} damage={damage} />}
        {damage && <CollapseStatic fp={fp} />}
        {damage && <DisasterStatic fp={fp} outside={!lite} />}
      </Baked>
      {damage && <CollapseLive fp={fp} dust={!perf && !lite} />}
      {damage && !perf && !lite && <DisasterLive fp={fp} />}
      {mode === 'plain' && (fp.hazards ?? []).map((hz) => <GasLeak key={hz.id} hazard={hz} />)}
      {blueprint && (
        <mesh position={w2t(cx, cy, 0.5)}>
          <sphereGeometry args={[0.35, 16, 16]} />
          <meshBasicMaterial color="#f59e0b" />
        </mesh>
      )}
    </group>
  )
}
