import { lazy, Suspense, useState } from 'react'
import type { Circuit3DProps } from './Circuit3D'
import './Circuit3D.css'

const Scene = lazy(() => import('./Circuit3D').then((module) => ({ default: module.Circuit3D })))

export function Circuit3DLoader(props: Circuit3DProps) {
  const [requested, setRequested] = useState(false)
  if (!requested) return <div className="circuit3d circuit3d--placeholder">
    <button className="circuit3d-launch" onClick={() => setRequested(true)}>▶ Open 3D view</button>
    <p className="circuit3d-note">Three.js · synchronized to replay clock</p>
  </div>
  return <Suspense fallback={<p role="status">Preparing the 3D circuit…</p>}><Scene {...props} initiallyVisible /></Suspense>
}
