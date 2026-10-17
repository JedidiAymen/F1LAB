/**
 * Circuit3D — Three.js/React Three Fiber 3D circuit viewer.
 *
 * Uses the centerline_xy points from the circuit geometry (same data as the 2D
 * TrackMap) to build a Catmull-Rom spline, extrude a track ribbon and render
 * car positions synchronized to the shared RaceState clock.
 *
 * Design notes:
 * - Same RaceState and CircuitGeometry contracts as the 2D panel; no 3D-specific
 *   data fork or clock.
 * - Geometry is normalized to [-1, 1] and then lifted into 3D (y=0 plane).
 * - Track ribbon is extruded from the spline using a TubeGeometry.
 * - Car dots are spheres placed on the spline at their interpolated position.
 * - Cameras: top-down (default), orbit (mouse drag), follow (selected driver).
 * - The Three.js scene is suspended out of the React tree via Canvas; all
 *   RaceState props flow in through fiber context / React props.
 * - No official F1 car models are used; cars are generic spheres/cylinders.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import './Circuit3D.css'

// ---------------------------------------------------------------------------
// Types (must align with App.tsx / circuit-geometry.ts)
// ---------------------------------------------------------------------------

interface CircuitGeometry {
  centerline_xy?: number[][]
  normalized_centerline_xy?: number[][]
  bounds?: { min_x: number; max_x: number; min_y: number; max_y: number }
  heading_radians?: number[]
}

interface DriverState {
  track_x: number | null
  track_y: number | null
  position: number | null
  [key: string]: unknown
}

interface Driver {
  driver_id: string
  acronym: string
  team_color: string
  number: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalizePts(pts: number[][]): THREE.Vector3[] {
  // pts are in provider units; normalize to [-5, 5] in X/Z, Y=0
  if (!pts.length) return []
  const xs = pts.map(p => p[0])
  const ys = pts.map(p => p[1])
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1
  const scale = 10 / Math.max(spanX, spanY)
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  return pts.map(p => new THREE.Vector3(
    (p[0] - cx) * scale,
    0,
    (p[1] - cy) * scale,
  ))
}

function buildSpline(pts: THREE.Vector3[]): THREE.CatmullRomCurve3 {
  return new THREE.CatmullRomCurve3(pts, true, 'catmullrom', 0.5)
}

function projectOnSpline(
  spline: THREE.CatmullRomCurve3,
  tx: number, ty: number,
  bounds: { min_x: number; max_x: number; min_y: number; max_y: number } | undefined,
): THREE.Vector3 {
  if (bounds == null) return new THREE.Vector3(0, 0.3, 0)
  const spanX = bounds.max_x - bounds.min_x || 1
  const spanY = bounds.max_y - bounds.min_y || 1
  const scale = 10 / Math.max(spanX, spanY)
  const cx = (bounds.min_x + bounds.max_x) / 2
  const cy = (bounds.min_y + bounds.max_y) / 2
  const x = (tx - cx) * scale
  const z = (ty - cy) * scale
  // Find nearest point on spline
  let best = 0
  let bestDist = Infinity
  const N = 200
  for (let i = 0; i < N; i++) {
    const t = i / N
    const pt = spline.getPoint(t)
    const d = (pt.x - x) ** 2 + (pt.z - z) ** 2
    if (d < bestDist) { bestDist = d; best = t }
  }
  const pos = spline.getPoint(best)
  return new THREE.Vector3(pos.x, 0.3, pos.z)
}

// ---------------------------------------------------------------------------
// Track ribbon
// ---------------------------------------------------------------------------

function TrackRibbon({ spline }: { spline: THREE.CatmullRomCurve3 }) {
  const tube = useMemo(() => {
    return new THREE.TubeGeometry(spline, 200, 0.18, 8, true)
  }, [spline])
  return (
    <mesh geometry={tube}>
      <meshStandardMaterial color="#2a2a2a" roughness={0.9} metalness={0.1} />
    </mesh>
  )
}

// ---------------------------------------------------------------------------
// Car dot
// ---------------------------------------------------------------------------

function CarDot({ position, color, selected }: {
  position: THREE.Vector3
  color: string
  selected: boolean
}) {
  const meshRef = useRef<THREE.Mesh>(null)
  const threeColor = useMemo(() => {
    try { return new THREE.Color(color.startsWith('#') ? color : `#${color}`) }
    catch { return new THREE.Color('#ffffff') }
  }, [color])

  useFrame(() => {
    if (meshRef.current) {
      meshRef.current.position.lerp(position, 0.12)
    }
  })

  return (
    <group>
      <mesh ref={meshRef} position={position}>
        <sphereGeometry args={[0.28, 12, 12]} />
        <meshStandardMaterial
          color={threeColor}
          emissive={threeColor}
          emissiveIntensity={selected ? 0.8 : 0.3}
          roughness={0.3}
          metalness={0.5}
        />
      </mesh>
    </group>
  )
}

// ---------------------------------------------------------------------------
// Scene (inside Canvas)
// ---------------------------------------------------------------------------

function Scene({
  spline,
  bounds,
  drivers,
  driverStates,
  selectedId,
  cameraMode,
}: {
  spline: THREE.CatmullRomCurve3 | null
  bounds: { min_x: number; max_x: number; min_y: number; max_y: number } | undefined
  drivers: Driver[]
  driverStates: Record<string, DriverState>
  selectedId: string | null
  cameraMode: 'top' | 'orbit'
}) {
  const { camera } = useThree()

  useEffect(() => {
    if (cameraMode === 'top') {
      camera.position.set(0, 18, 0)
      camera.lookAt(0, 0, 0)
    }
  }, [cameraMode, camera])

  const driverMap = useMemo(() =>
    Object.fromEntries(drivers.map(d => [d.driver_id, d])), [drivers])

  const carPositions = useMemo(() => {
    if (!spline || !bounds) return {}
    const result: Record<string, THREE.Vector3> = {}
    for (const [id, ds] of Object.entries(driverStates)) {
      if (ds.track_x != null && ds.track_y != null) {
        result[id] = projectOnSpline(spline, ds.track_x, ds.track_y, bounds)
      }
    }
    return result
  }, [spline, bounds, driverStates])

  if (!spline) {
    return null
  }

  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 10, 5]} intensity={0.8} castShadow />
      <TrackRibbon spline={spline} />
      {/* Start/finish line indicator */}
      <mesh position={[spline.getPoint(0).x, 0.05, spline.getPoint(0).z]}>
        <boxGeometry args={[0.8, 0.1, 0.05]} />
        <meshStandardMaterial color="#ffffff" />
      </mesh>
      {/* Cars */}
      {Object.entries(carPositions).map(([id, pos]) => {
        const d = driverMap[id]
        return (
          <CarDot
            key={id}
            position={pos}
            color={d?.team_color ?? '#ffffff'}
            selected={id === selectedId}
          />
        )
      })}
      {cameraMode === 'orbit' && <OrbitControls enablePan={false} maxPolarAngle={Math.PI / 2.2} />}
    </>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Circuit3DProps {
  geometry: CircuitGeometry
  drivers: Driver[]
  driverStates: Record<string, DriverState>
  selectedId?: string | null
}

export function Circuit3D({ geometry, drivers, driverStates, selectedId = null }: Circuit3DProps) {
  const [cameraMode, setCameraMode] = useState<'top' | 'orbit'>('top')
  const [visible, setVisible] = useState(false)

  const spline = useMemo(() => {
    const pts = geometry.centerline_xy
    if (!pts || pts.length < 3) return null
    return buildSpline(normalizePts(pts))
  }, [geometry.centerline_xy])

  // Lazy mount the Canvas to avoid R3F initialization cost before the user opens the panel
  if (!visible) {
    return (
      <div className="circuit3d circuit3d--placeholder">
        <button className="circuit3d-launch" onClick={() => setVisible(true)}>
          ▶ Open 3D view
        </button>
        <p className="circuit3d-note">
          Three.js · synchronized to replay clock
        </p>
      </div>
    )
  }

  return (
    <div className="circuit3d">
      <div className="circuit3d-toolbar">
        <button
          className={`circuit3d-btn${cameraMode === 'top' ? ' circuit3d-btn--active' : ''}`}
          onClick={() => setCameraMode('top')}
        >
          Top
        </button>
        <button
          className={`circuit3d-btn${cameraMode === 'orbit' ? ' circuit3d-btn--active' : ''}`}
          onClick={() => setCameraMode('orbit')}
        >
          Orbit
        </button>
        <span className="circuit3d-label">3D · {geometry.centerline_xy?.length ?? 0} pts</span>
        <button className="circuit3d-btn circuit3d-btn--close" onClick={() => setVisible(false)}>✕</button>
      </div>
      <Canvas
        className="circuit3d-canvas"
        camera={{ position: [0, 18, 0], fov: 50 }}
        shadows
        gl={{ antialias: true }}
      >
        <Scene
          spline={spline}
          bounds={geometry.bounds}
          drivers={drivers}
          driverStates={driverStates}
          selectedId={selectedId}
          cameraMode={cameraMode}
        />
      </Canvas>
      {!spline && (
        <div className="circuit3d-no-geometry">
          No centerline geometry available for this session
        </div>
      )}
    </div>
  )
}
