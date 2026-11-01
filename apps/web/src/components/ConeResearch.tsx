import { useEffect, useState } from 'react'
import './ConeResearch.css'

type Score = { map_50: number; map_50_95: number; precision_at_50_iou: number | null; recall_at_50_iou: number | null; conditional_frame_bootstrap_recall_95: number[] | null; mean_model_seconds_excluding_decode_first: number | null }
type Metrics = { baseline: Score; fine_tuned: Score; model_sha256: string; dataset_manifest_sha256: string; source_revision: string; device: string; gpu: string | null }
type Study = { evidence: string; frame_count: number; metrics: Metrics }
type Box = { bbox: [number, number, number, number]; score: number }
type Frame = { frame_id: number; frame_count: number; width: number; height: number; filename_prefix: string; image_sha256: string; ground_truth: { bbox: [number, number, number, number]; class_name: string }[]; predictions: { baseline: Box[]; fine_tuned: Box[] } }
const metric = (value: number | null) => value === null ? 'Unavailable' : value.toFixed(3)

export function ConeResearch() {
  const [study, setStudy] = useState<Study | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [frame, setFrame] = useState<Frame | null>(null)
  const [number, setNumber] = useState(1)
  const [arm, setArm] = useState<'baseline' | 'fine_tuned'>('fine_tuned')
  const [threshold, setThreshold] = useState(0.5)
  const [truth, setTruth] = useState(true)
  const [frameError, setFrameError] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/research/racevision/cones', { signal: controller.signal }).then(async (r) => {
      if (!r.ok) throw new Error('Unavailable')
      return r.json() as Promise<Study>
    }).then(setStudy).catch((e) => { if (e.name !== 'AbortError') setUnavailable(true) })
    return () => controller.abort()
  }, [])
  useEffect(() => {
    if (!study) return
    const controller = new AbortController()
    fetch(`/api/v1/research/racevision/cones/${number}`, { signal: controller.signal }).then(async (r) => {
      if (!r.ok) throw new Error('Unavailable')
      return r.json() as Promise<Frame>
    }).then((result) => { setFrame(result); setFrameError(false) }).catch((e) => { if (e.name !== 'AbortError') setFrameError(true) })
    return () => controller.abort()
  }, [number, study])
  const current = frame?.frame_id === number ? frame : null
  const selected = current?.predictions[arm].filter((box) => box.score >= threshold) ?? []
  return <section className="research-panel cone-research" aria-label="Cone perception research">
    <span className="cone-kicker">RACEVISION · LOCAL EXPLORATORY STUDY</span><h2>Perception under race conditions</h2>
    <p>Formula Student cone images and saved detector output. This is not Formula 1 footage or a race-car detector.</p>
    {unavailable && <p role="status">Local cone study unavailable. Follow the research protocol to build its optional artifacts.</p>}
    {!study && !unavailable && <p role="status">Loading the local study…</p>}
    {study && <>
      <p>{study.evidence}. Results use 20 held-out frames from one filename prefix; the recording sequence and circuit are not independently verified.</p>
      <div className="research-table-scroll"><table aria-label="Cone detector metrics"><thead><tr><th>Model</th><th>mAP@50</th><th>mAP@50:95</th><th>Precision @0.5</th><th>Recall @0.5</th><th>Model time</th></tr></thead><tbody>
        {(['baseline', 'fine_tuned'] as const).map((key) => <tr key={key}><th scope="row">{key === 'baseline' ? 'COCO transfer reference' : 'Fine-tuned cone detector'}</th><td>{metric(study.metrics[key].map_50)}</td><td>{metric(study.metrics[key].map_50_95)}</td><td>{metric(study.metrics[key].precision_at_50_iou)}</td><td>{metric(study.metrics[key].recall_at_50_iou)}</td><td>{study.metrics[key].mean_model_seconds_excluding_decode_first === null ? 'Unavailable' : `${(1000 * study.metrics[key].mean_model_seconds_excluding_decode_first!).toFixed(1)} ms`}</td></tr>)}
      </tbody></table></div>
      <p>Threshold metrics use confidence 0.5 and IoU 0.5. Model time excludes image decoding, transfer and the first invocation. COCO baseline categories are collapsed; its classes do not include cones. This small sample cannot establish a useful improvement.</p>
      <p>Fine-tuned recall 95% conditional frame-bootstrap interval: {study.metrics.fine_tuned.conditional_frame_bootstrap_recall_95?.map(metric).join('–') ?? 'Unavailable'}. Frames may be correlated; this interval does not measure new-circuit generalization.</p>
      <div className="cone-controls"><label>Frame <select aria-label="Cone study frame" value={number} onChange={(e) => setNumber(Number(e.target.value))}>{Array.from({ length: study.frame_count }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1} / {study.frame_count}</option>)}</select></label>
        <label>Predictions <select aria-label="Cone study model" value={arm} onChange={(e) => setArm(e.target.value as typeof arm)}><option value="fine_tuned">Fine-tuned detector</option><option value="baseline">COCO transfer reference</option></select></label>
        <label>Confidence ≥ {threshold.toFixed(2)} <input aria-label="Cone confidence threshold" type="range" min="0" max="1" step="0.05" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></label>
        <label className="cone-checkbox"><input type="checkbox" checked={truth} onChange={(e) => setTruth(e.target.checked)} /> Ground truth</label></div>
      {frameError && <p role="status">This frame is unavailable or failed an integrity check.</p>}
      {current && <><div className="cone-frame" style={{ aspectRatio: `${current.width} / ${current.height}` }}>
        <img src={`/api/v1/research/racevision/cones/${current.frame_id}/image`} alt={`Formula Student held-out frame ${current.frame_id}`} />
        <svg viewBox={`0 0 ${current.width} ${current.height}`} role="img" aria-label="Ground truth and detector bounding boxes">
          {truth && current.ground_truth.map(({ bbox }, index) => <rect key={`truth-${index}`} x={bbox[0]} y={bbox[1]} width={bbox[2]} height={bbox[3]} className="cone-truth" />)}
          {selected.map(({ bbox }, index) => <rect key={`prediction-${index}`} x={bbox[0]} y={bbox[1]} width={bbox[2]} height={bbox[3]} className="cone-prediction" />)}
        </svg></div><p role="status" aria-label="Cone frame summary">Frame {current.frame_id} · {current.ground_truth.length} labeled cones · {selected.length} displayed predictions · prefix {current.filename_prefix}. Green: labels; orange: predictions.</p>
        <details><summary>Highest-confidence displayed predictions</summary><ol>{[...selected].sort((a, b) => b.score - a.score).slice(0, 5).map((item, index) => <li key={index}>Confidence {item.score.toFixed(3)} · box {item.bbox.map((value) => value.toFixed(1)).join(', ')} px (x, y, width, height)</li>)}</ol>{selected.length === 0 && <p>No predictions at this threshold.</p>}</details>
        <details><summary>Frame and model provenance</summary><p>Image SHA-256 <code>{current.image_sha256}</code></p><p>Dataset SHA-256 <code>{study.metrics.dataset_manifest_sha256}</code></p><p>Model SHA-256 <code>{study.metrics.model_sha256}</code></p><p>Source revision <code>{study.metrics.source_revision}</code> · {study.metrics.gpu ?? study.metrics.device}</p></details></>}
    </>}
  </section>
}
