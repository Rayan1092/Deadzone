import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { useSim } from '../store'
import { w2t } from './util'
import { coveragePixel } from './coverageRamp'

// W: the predicted radio coverage as Command computes it (only from relays it knows about), a
// translucent layer on the Command side: strong, weak, dead. Drawn only when the server sends it.
export default function CoverageLayer() {
  const on = useSim((s) => s.coverageOn)
  const cov = useSim((s) => s.maps.coverage)
  const tex = useMemo(() => {
    if (!cov) return null
    const t = new THREE.DataTexture(new Uint8Array(cov.w * cov.h * 4), cov.w, cov.h, THREE.RGBAFormat)
    t.magFilter = THREE.LinearFilter
    t.minFilter = THREE.LinearFilter
    const px = t.image.data
    for (let i = 0; i < cov.grid.length; i++) {
      const [r, g, b, a] = coveragePixel(cov.grid[i])
      px[i * 4] = r; px[i * 4 + 1] = g; px[i * 4 + 2] = b; px[i * 4 + 3] = a
    }
    t.needsUpdate = true
    return t
  }, [cov])
  useEffect(() => () => tex?.dispose(), [tex])
  if (!on || !tex) return null
  const W = cov.w * cov.cell
  const H = cov.h * cov.cell
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={w2t(W / 2, H / 2, 0.04)} renderOrder={1}>
      <planeGeometry args={[W, H]} />
      <meshBasicMaterial map={tex} transparent depthWrite={false} toneMapped={false} />
    </mesh>
  )
}

// the two-word legend: a strong-to-dead gradient
export function CoverageLegend({ className = '' }) {
  const on = useSim((s) => s.coverageOn)
  const has = useSim((s) => Boolean(s.maps.coverage))
  if (!on || !has) return null
  return (
    <div className={`coverage-legend ${className}`} title="Predicted radio signal from the command post and the relays it knows about">
      <span>Strong</span><i /><span>Dead</span>
    </div>
  )
}
