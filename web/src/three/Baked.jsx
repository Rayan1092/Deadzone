import { useLayoutEffect, useRef } from 'react'
import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

// Static set dressing is hundreds of small meshes; drawn one by one (and again for the
// shadow map) that costs more than the whole sim view. After the first render, merge every
// plain mesh below this group into one mesh per look and hide the originals. Meshes are grouped
// by what their material looks like (type, colours, maps, surface, blending), not by material
// object: props declare materials inline, so 36 identical tyres used to be 36 materials and 36
// draws. A material marked `userData.live` (animated, like the truck's light bar) keeps its own
// group. Geometry without uvs or normals (glass shards) gets them so it can merge too.
// Instanced meshes and sprites are left alone.
const hex = (c) => (c ? c.getHexString() : '-')
const id = (tex) => (tex ? tex.uuid : '-')
// Everything that changes how a material draws; equal looks render identically, so they share a mesh.
export function lookOf(m) {
  if (m.userData?.live || m.onBeforeCompile?.toString() !== THREE.Material.prototype.onBeforeCompile.toString()) return m.uuid
  return [m.type, hex(m.color), hex(m.emissive), m.emissiveIntensity, m.roughness, m.metalness, m.opacity, m.transparent,
    m.side, m.alphaTest, m.depthWrite, m.depthTest, m.toneMapped, m.fog, m.flatShading, m.vertexColors, m.wireframe,
    m.polygonOffset, m.polygonOffsetFactor, m.polygonOffsetUnits, m.blending, m.envMapIntensity,
    id(m.map), id(m.normalMap), id(m.roughnessMap), id(m.metalnessMap), id(m.alphaMap), id(m.aoMap), id(m.emissiveMap),
    id(m.envMap), id(m.bumpMap), id(m.lightMap), m.normalScale ? `${m.normalScale.x},${m.normalScale.y}` : '-'].join('|')
}

export default function Baked({ children, deps = [] }) {
  const ref = useRef()
  useLayoutEffect(() => {
    const root = ref.current
    if (!root) return
    root.updateWorldMatrix(true, true)
    const inv = root.matrixWorld.clone().invert()
    const byMat = new Map()
    const hidden = []
    // a subtree marked userData.noBake (an animated part, like a rover's spinning lidar) is skipped
    const visit = (o, fn) => { if (o !== root && o.userData.noBake) return; fn(o); o.children.forEach((c) => visit(c, fn)) }
    visit(root, (o) => {
      if (!o.isMesh || o.isInstancedMesh || o.userData.baked || !o.visible || Array.isArray(o.material)) return
      const g = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone()
      for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k)
      if (!g.attributes.position) return
      if (!g.attributes.normal) g.computeVertexNormals()
      if (!g.attributes.uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2))
      g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld))
      const key = lookOf(o.material)
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
    const mergedLooks = new Set(made.map((m) => lookOf(m.material)))
    const off = hidden.filter((o) => mergedLooks.has(lookOf(o.material)))
    off.forEach((o) => { o.visible = false })
    return () => {
      made.forEach((m) => { root.remove(m); m.geometry.dispose() })
      off.forEach((o) => { o.visible = true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return <group ref={ref}>{children}</group>
}
