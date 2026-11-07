import { useMemo } from 'react'
import { Html, Line } from '@react-three/drei'
import * as THREE from 'three'
import { useSim } from '../store'
import { COLORS, FOG_H, w2t } from './util'

// The shared search plan, on both panes: it is made at the command post, so
// Command knows it too. Dashed while a draft, solid once dispatch is accepted.
// Drawn just above the fog so zones over unexplored rooms stay visible.
const Y = FOG_H + 0.02

function Region({ poly, color, label, dashed, fill }) {
  const shape = useMemo(() => new THREE.Shape(poly.map(([x, y]) => new THREE.Vector2(x, y))), [poly])
  const outline = [...poly, poly[0]].map(([x, y]) => w2t(x, y, Y))
  const xs = poly.map((p) => p[0])
  const ys = poly.map((p) => p[1])
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, Y, 0]} renderOrder={3}>
        <shapeGeometry args={[shape]} />
        <meshBasicMaterial color={color} transparent opacity={fill} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <Line points={outline} color={color} lineWidth={2} dashed={dashed} dashSize={0.5} gapSize={0.3} />
      <Html position={w2t((Math.min(...xs) + Math.max(...xs)) / 2, Math.max(...ys) - 0.6, Y)} center
            zIndexRange={[1, 0]} style={{ pointerEvents: 'none' }}>
        <div className="tag zone" style={{ borderColor: color }}>{label}</div>
      </Html>
    </group>
  )
}

export default function PlanZones() {
  const plan = useSim((s) => s.plan)
  const dispatched = useSim((s) => s.dispatchedPlans)
  const robots = useSim((s) => s.robotsMeta)
  if (!plan) return null
  const colors = Object.fromEntries(robots.map((r) => [r.id, r.color]))
  const draft = !dispatched.includes(plan.plan_id)
  return (
    <group>
      {plan.no_go.map((g) => (
        <Region key={g.id} poly={g.poly} color={COLORS.red} label={`${g.id} no-go`} dashed fill={0.12} />
      ))}
      {plan.zones.map((z) => (
        <Region key={z.id} poly={z.poly} color={colors[z.robot] ?? COLORS.teal}
                label={<><b>{z.id}</b><span>{z.robot}{draft ? ' · draft' : ''}</span></>}
                dashed={draft} fill={draft ? 0.08 : 0.16} />
      ))}
    </group>
  )
}
