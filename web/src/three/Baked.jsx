import { useLayoutEffect, useRef } from 'react'
import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

// Static set dressing is hundreds of small meshes; drawn one by one (and again for the
// shadow map) that costs more than the whole sim view. After the first render, merge every
// plain mesh below this group into one mesh per material and hide the originals.
// Shared material objects stay shared, so an animated material (the truck's light bar)
// still animates. Instanced meshes and sprites are left alone.
export default function Baked({ children, deps = [] }) {
  const ref = useRef()
  useLayoutEffect(() => {
    const root = ref.current
    if (!root) return
    root.updateWorldMatrix(true, true)
    const inv = root.matrixWorld.clone().invert()
    const byMat = new Map()
    const hidden = []
    root.traverse((o) => {
      if (!o.isMesh || o.isInstancedMesh || o.userData.baked || !o.visible || Array.isArray(o.material)) return
      const g = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone()
      for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k)
      if (!g.attributes.uv) return
      g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld))
      const key = o.material.uuid
      if (!byMat.has(key)) byMat.set(key, { material: o.material, geoms: [], cast: false, receive: false })
      const entry = byMat.get(key)
      entry.geoms.push(g)
      entry.cast ||= o.castShadow
      entry.receive ||= o.receiveShadow
      hidden.push(o)
    })
    const made = []
    for (const { material, geoms, cast, receive } of byMat.values()) {
      if (geoms.length < 2) { geoms.forEach((g) => g.dispose()); continue }
      const merged = mergeGeometries(geoms, false)
      geoms.forEach((g) => g.dispose())
      if (!merged) continue
      const mesh = new THREE.Mesh(merged, material)
      mesh.castShadow = cast
      mesh.receiveShadow = receive
      mesh.userData.baked = true
      root.add(mesh)
      made.push(mesh)
    }
    const mergedMats = new Set(made.map((m) => m.material.uuid))
    const off = hidden.filter((o) => mergedMats.has(o.material.uuid))
    off.forEach((o) => { o.visible = false })
    return () => {
      made.forEach((m) => { root.remove(m); m.geometry.dispose() })
      off.forEach((o) => { o.visible = true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return <group ref={ref}>{children}</group>
}
