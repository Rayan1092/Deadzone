import { forwardRef, useEffect, useLayoutEffect, useMemo } from 'react'
import { useThree } from '@react-three/fiber'
import { Line2, LineGeometry, LineMaterial } from 'three-stdlib'

// Drop-in for drei's <Line> on lines whose points arrive as a new array every tick (routes,
// radio links, robot paths). drei rebuilds the geometry whenever `points` is a new object and
// its cleanup also disposes the material, so three relinks a shader program for every line on
// every tick: about 40% of the main thread in rayan-ml's profile. Here the material lives as
// long as the line, and the geometry is rebuilt (the old one disposed) only when the numbers
// in `points` actually change. Same pixels.
const FastLine = forwardRef(function FastLine({
  points, color = '#ffffff', lineWidth = 1, dashed = false, dashSize = 1, gapSize = 1,
  opacity = 1, transparent = false, depthTest = true, depthWrite, renderOrder = 0, ...rest
}, ref) {
  const size = useThree((s) => s.size)
  const [line, mat] = useMemo(() => {
    const m = new LineMaterial()
    return [new Line2(new LineGeometry(), m), m]
  }, [])
  const flat = points.flat()
  const key = flat.join(',')

  useLayoutEffect(() => {
    const old = line.geometry
    const geom = new LineGeometry()
    geom.setPositions(flat.length >= 6 ? flat : [0, 0, 0, 0, 0, 0])
    line.geometry = geom
    line.computeLineDistances()
    old.dispose()
  }, [key, line]) // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    if (dashed) mat.defines.USE_DASH = ''
    else delete mat.defines.USE_DASH
    mat.dashed = dashed
    mat.needsUpdate = true // one recompile when dashing toggles, never per tick
  }, [dashed, mat])

  useLayoutEffect(() => {
    mat.color.set(color)
    mat.linewidth = lineWidth
    mat.dashSize = dashSize
    mat.gapSize = gapSize
    mat.transparent = transparent
    mat.opacity = opacity
    mat.depthTest = depthTest
    if (depthWrite !== undefined) mat.depthWrite = depthWrite
  }, [mat, color, lineWidth, dashSize, gapSize, transparent, opacity, depthTest, depthWrite])

  useLayoutEffect(() => { mat.resolution.set(size.width, size.height) }, [mat, size.width, size.height])

  useEffect(() => () => { line.geometry.dispose(); mat.dispose() }, [line, mat])

  return <primitive object={line} ref={ref} renderOrder={renderOrder} {...rest} />
})

export default FastLine
