import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { useSim } from '../store'
import { w2t } from './util'
import { CONFIRMED, beliefPixel } from './beliefRamp'

// The survivor belief map as a heat layer on the floor (Y): where people may still be. Reality
// shows the team's belief, Command only what its delivered data supports (Rayan's belief.py;
// prior from the building plan, never truth). Drawn only when the server sends the grids.
export default function BeliefLayer({ which }) {
  const on = useSim((s) => s.beliefOn)
  const grid = useSim((s) => s.grid)
  const fp = useSim((s) => s.floorplan)
  const version = useSim((s) => s.maps.beliefVersion)
  const tex = useMemo(() => {
    if (!grid) return null
    const t = new THREE.DataTexture(new Uint8Array(grid.w * grid.h * 4), grid.w, grid.h, THREE.RGBAFormat)
    t.magFilter = THREE.LinearFilter
    t.minFilter = THREE.LinearFilter
    t.needsUpdate = true
    return t
  }, [grid])
  useEffect(() => {
    const maps = useSim.getState().maps
    const src = which === 'command' ? maps.beliefCommand : maps.belief
    if (!tex || !src || src.length !== tex.image.width * tex.image.height) return
    const px = tex.image.data
    for (let i = 0; i < src.length; i++) {
      const [r, g, b, a] = beliefPixel(src[i])
      const o = i * 4
      px[o] = r; px[o + 1] = g; px[o + 2] = b; px[o + 3] = a
    }
    tex.needsUpdate = true
  }, [version, tex, which])
  useEffect(() => () => tex?.dispose(), [tex])
  const has = useSim((s) => Boolean(which === 'command' ? s.maps.beliefCommand : s.maps.belief))
  // a confirmed survivor is one 0.25 m cell: a ring makes it findable from the overview
  const marks = useMemo(() => {
    const maps = useSim.getState().maps
    const src = which === 'command' ? maps.beliefCommand : maps.belief
    if (!src || !grid) return []
    const out = []
    for (let i = 0; i < src.length; i++) if (src[i] === CONFIRMED) out.push([((i % grid.w) + 0.5) * grid.cell, (Math.floor(i / grid.w) + 0.5) * grid.cell])
    return out.slice(0, 12)
  }, [version, which, grid])
  if (!on || !has || !tex || !fp) return null
  const [W, H] = fp.size
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, 0.05)} renderOrder={1}>
        <planeGeometry args={[W, H]} />
        <meshBasicMaterial map={tex} transparent depthWrite={false} toneMapped={false} />
      </mesh>
      {marks.map(([x, y], i) => (
        <mesh key={i} rotation={[-Math.PI / 2, 0, 0]} position={w2t(x, y, 0.07)} renderOrder={2}>
          <ringGeometry args={[0.7, 0.95, 40]} />
          <meshBasicMaterial color="#2dd4bf" transparent opacity={0.9} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  )
}
