import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { useSim } from '../store'
import { FOG_H, w2t } from './util'

// Two textures built from the same occupancy grid:
//  - fog: dark over UNKNOWN cells, sits above the walls so unmapped rooms stay hidden
//  - tint: faint teal on known FREE floor, bright on OCC so the map reads as a scan
export default function Fog({ which }) {
  const grid = useSim((s) => s.grid)
  const fp = useSim((s) => s.floorplan)
  const version = useSim((s) => s.maps.version)

  const tex = useMemo(() => {
    if (!grid) return null
    const make = () => {
      const t = new THREE.DataTexture(new Uint8Array(grid.w * grid.h * 4), grid.w, grid.h, THREE.RGBAFormat)
      t.magFilter = THREE.LinearFilter
      t.minFilter = THREE.LinearFilter
      t.needsUpdate = true
      return t
    }
    return { fog: make(), tint: make() }
  }, [grid])

  useEffect(() => {
    if (!tex) return
    const map = useSim.getState().maps[which]
    if (!map) return
    const fog = tex.fog.image.data
    const tint = tex.tint.image.data
    for (let i = 0; i < map.length; i++) {
      const v = map[i]
      const o = i * 4
      // fog: unknown = near black
      fog[o] = 12; fog[o + 1] = 14; fog[o + 2] = 17
      fog[o + 3] = v === 0 ? 232 : 0
      // tint
      if (v === 1) { tint[o] = 45; tint[o + 1] = 212; tint[o + 2] = 191; tint[o + 3] = 34 }
      else if (v === 2) { tint[o] = 180; tint[o + 1] = 255; tint[o + 2] = 245; tint[o + 3] = 200 }
      else { tint[o + 3] = 0 }
    }
    tex.fog.needsUpdate = true
    tex.tint.needsUpdate = true
  }, [version, tex, which])

  if (!tex || !fp) return null
  const W = grid.w * grid.cell
  const H = grid.h * grid.cell
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, 0.03)} renderOrder={1}>
        <planeGeometry args={[W, H]} />
        <meshBasicMaterial map={tex.tint} transparent depthWrite={false} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, FOG_H)} renderOrder={2}>
        <planeGeometry args={[W, H]} />
        <meshBasicMaterial map={tex.fog} transparent depthWrite={false} />
      </mesh>
    </group>
  )
}
