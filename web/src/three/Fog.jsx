import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useSim } from '../store'
import { FOG_H, w2t } from './util'

// Textures built from the occupancy grids:
//  - fog: dark over UNKNOWN cells, sits above the walls so unmapped rooms stay hidden
//  - tint: faint teal on known FREE floor, bright on OCC so the map reads as a scan
//  - haze (which = 'gap' only): amber over cells the robots have mapped but Command
//    has not received yet. It fades out as the map patches arrive: the reveal.
const HAZE_A = 95      // alpha of not-yet-reported floor
const FADE_OUT = 3     // alpha per frame when Command learns a cell (~0.5 s)

// cover={false}: skip the dark layer (the Command inset shows the public floorplan).
export default function Fog({ which, cover = true }) {
  const grid = useSim((s) => s.grid)
  const fp = useSim((s) => s.floorplan)
  const version = useSim((s) => s.maps.version)
  const haze = useRef(null)    // current alpha per cell
  const target = useRef(null)  // wanted alpha per cell
  const animating = useRef(false)

  const tex = useMemo(() => {
    if (!grid) return null
    const make = () => {
      const t = new THREE.DataTexture(new Uint8Array(grid.w * grid.h * 4), grid.w, grid.h, THREE.RGBAFormat)
      t.magFilter = THREE.LinearFilter
      t.minFilter = THREE.LinearFilter
      t.needsUpdate = true
      return t
    }
    haze.current = new Uint8Array(grid.w * grid.h)
    target.current = new Uint8Array(grid.w * grid.h)
    return { fog: make(), tint: make(), haze: make() }
  }, [grid])

  useEffect(() => {
    if (!tex) return
    const maps = useSim.getState().maps
    const map = maps[which === 'gap' ? 'reality' : which]
    if (!map) return
    const fog = tex.fog.image.data
    const tint = tex.tint.image.data
    const cmd = which === 'gap' ? maps.command : null
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
      if (cmd) {
        const want = v !== 0 && cmd[i] === 0 ? HAZE_A : 0
        if (want !== target.current[i]) {
          target.current[i] = want
          animating.current = true
        }
      }
    }
    tex.fog.needsUpdate = true
    tex.tint.needsUpdate = true
  }, [version, tex, which])

  // Haze appears at once (new ground) and fades out when Command catches up.
  useFrame(() => {
    if (which !== 'gap' || !tex || !animating.current) return
    const cur = haze.current
    const want = target.current
    const px = tex.haze.image.data
    let moving = false
    for (let i = 0; i < cur.length; i++) {
      if (cur[i] === want[i]) continue
      cur[i] = want[i] > cur[i] ? want[i] : Math.max(want[i], cur[i] - FADE_OUT)
      if (cur[i] !== want[i]) moving = true
      const o = i * 4
      px[o] = 245; px[o + 1] = 158; px[o + 2] = 11; px[o + 3] = cur[i]
    }
    tex.haze.needsUpdate = true
    animating.current = moving
  })

  if (!tex || !fp) return null
  const W = grid.w * grid.cell
  const H = grid.h * grid.cell
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, 0.03)} renderOrder={1}>
        <planeGeometry args={[W, H]} />
        <meshBasicMaterial map={tex.tint} transparent depthWrite={false} />
      </mesh>
      {which === 'gap' && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, 0.04)} renderOrder={1}>
          <planeGeometry args={[W, H]} />
          <meshBasicMaterial map={tex.haze} transparent depthWrite={false} />
        </mesh>
      )}
      {cover && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, FOG_H)} renderOrder={2}>
          <planeGeometry args={[W, H]} />
          <meshBasicMaterial map={tex.fog} transparent depthWrite={false} />
        </mesh>
      )}
    </group>
  )
}
