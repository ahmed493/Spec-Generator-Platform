import { useState, useEffect, useRef } from 'react'
import {
  Layers, ChevronDown, ChevronUp, Database, GitBranch, ArrowUp, ArrowDown, Scissors, Combine, Save,
} from 'lucide-react'
import { useProject } from '../../context/ProjectContext'
import {
  pipelineDetectPipelines,
  pipelineMerge,
  pipelineReorder,
  pipelineResetPipelines,
  pipelineSelect,
  pipelineSplit,
  pipelineUpdatePipelines,
} from '../../api'
import ValidationGate from '../../components/ValidationGate'

const TypeBadge = ({ type }) => {
  const color = {
    ETL: '#3b82f6', ELT: '#6366f1', ingestion: '#10b981',
    reporting: '#f59e0b', ml: '#ec4899', api: '#8b5cf6',
    batch: '#3b82f6', streaming: '#10b981',
  }[type?.toLowerCase()] || '#64748b'
  return (
    <span style={{
      fontSize: '10px', fontWeight: 700, padding: '2px 8px', borderRadius: '999px',
      background: color + '22', color, border: `1px solid ${color}55`, textTransform: 'uppercase',
    }}>{type || 'pipeline'}</span>
  )
}

const Tag = ({ label }) => (
  <span style={{
    fontSize: '10px', padding: '2px 7px', borderRadius: '4px',
    background: 'rgba(255,255,255,.06)', color: 'var(--text-secondary)',
    border: '1px solid var(--border)',
  }}>{label}</span>
)

const getPipelineSource = (pipeline) => {
  if (!pipeline) return 'detected'
  if (pipeline.origin === 'manual' || pipeline.id?.startsWith('manual_pipeline_')) {
    return 'manual'
  }
  return 'detected'
}

const SourceBadge = ({ pipeline }) => {
  const source = getPipelineSource(pipeline)
  const palette = source === 'manual'
    ? {
      label: 'Manual',
      color: '#f59e0b',
      background: 'rgba(245, 158, 11, 0.14)',
      border: 'rgba(245, 158, 11, 0.28)',
    }
    : {
      label: 'Detected',
      color: '#34d399',
      background: 'rgba(52, 211, 153, 0.12)',
      border: 'rgba(52, 211, 153, 0.24)',
    }

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      fontSize: '10px',
      fontWeight: 700,
      padding: '2px 8px',
      borderRadius: '999px',
      background: palette.background,
      color: palette.color,
      border: `1px solid ${palette.border}`,
      textTransform: 'uppercase',
      letterSpacing: '.04em',
    }}>{palette.label}</span>
  )
}

const createManualPipeline = () => ({
  id: `manual_pipeline_${Date.now()}`,
  origin: 'manual',
  name: 'Manual Pipeline',
  description: 'Pipeline added manually by the user.',
  type: 'other',
  execution_mode: 'batch',
  launcher: 'manual',
  confidence: 1,
  triggers: [],
  listen_mode: [],
  queues: [],
  jobs: [],
  sub_pipelines: [],
  parent_pipeline: null,
  explainability: {
    keywords: ['manual'],
    orchestration_clues: ['user_defined'],
    evidence_files: [],
    evidence_tables: [],
  },
  source_files: [],
  source_tables: [],
  technologies: [],
})

export default function PipelineDetectionStep() {
  const { state, dispatch } = useProject()
  const { project, detectedPipelines, selectedPipeline, gates } = state
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [selectedId, setSelectedId] = useState(selectedPipeline?.id || null)
  const [pipelines, setPipelines] = useState(detectedPipelines || [])
  const [mergeSelection, setMergeSelection] = useState([])

  const confirmed = gates[0]
  const detectionCalledRef = useRef(false)

  useEffect(() => {
    if (detectedPipelines.length === 0 && !loading && !detectionCalledRef.current) {
      detectionCalledRef.current = true
      runDetection()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setPipelines(detectedPipelines || [])
  }, [detectedPipelines])

  const runDetection = async () => {
    if (!project) return
    if (loading) return  // prevent double-fire
    detectionCalledRef.current = true
    setLoading(true)
    setError(null)
    setPipelines([])
    dispatch({ type: 'SET_DETECTED_PIPELINES', payload: [] })
    try {
      let res
      try {
        res = await pipelineDetectPipelines(project.id)
      } catch (firstErr) {
        const code = firstErr?.code || ''
        const status = firstErr?.response?.status
        const transient = code === 'ECONNABORTED' || code === 'ERR_NETWORK' || status === 502 || status === 503 || status === 504
        if (!transient) throw firstErr
        // Retry once for transient gateway/timeout/network errors.
        res = await pipelineDetectPipelines(project.id)
      }
      const items = res.data.pipelines || []
      setPipelines(items)
      setError(null)
      dispatch({ type: 'SET_DETECTED_PIPELINES', payload: items })
      if (items.length === 1) setSelectedId(items[0].id)
      if (items.length > 0) setExpandedId(items[0].id)
      if (items.length === 0) {
        setError('No pipelines detected. The AI could not identify pipeline patterns in your source. Try adding more sources or use "Add Pipeline Manually".')
      }
    } catch (err) {
      const details = err.response?.data?.detail || err.message || 'Pipeline detection failed.'
      setError(`Pipeline detection failed: ${details}`)
    }
    setLoading(false)
  }

  const persistPipelines = async (nextPipelines, nextSelectedId = selectedId) => {
    if (!project) return
    setSaving(true)
    setError(null)
    try {
      const res = await pipelineUpdatePipelines(project.id, nextPipelines)
      const saved = res.data.pipelines || []
      setPipelines(saved)
      dispatch({ type: 'SET_DETECTED_PIPELINES', payload: saved })
      const chosenId = nextSelectedId || saved[0]?.id || null
      if (chosenId) {
        setSelectedId(chosenId)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save pipeline edits.')
    }
    setSaving(false)
  }

  const movePipeline = async (pipelineId, direction) => {
    const idx = pipelines.findIndex(p => p.id === pipelineId)
    const target = direction === 'up' ? idx - 1 : idx + 1
    if (idx < 0 || target < 0 || target >= pipelines.length) return
    const ordered = [...pipelines]
    const [item] = ordered.splice(idx, 1)
    ordered.splice(target, 0, item)
    const ids = ordered.map(p => p.id)
    setPipelines(ordered)
    try {
      const res = await pipelineReorder(project.id, ids)
      const saved = res.data.pipelines || ordered
      setPipelines(saved)
      dispatch({ type: 'SET_DETECTED_PIPELINES', payload: saved })
    } catch {
      persistPipelines(ordered)
    }
  }

  const renamePipeline = (pipelineId, name) => {
    const next = pipelines.map(p => (p.id === pipelineId ? { ...p, name } : p))
    setPipelines(next)
  }

  const splitPipelineItem = async (pipeline) => {
    const first = window.prompt('Name for split pipeline A:', `${pipeline.name} A`)
    if (!first) return
    const second = window.prompt('Name for split pipeline B:', `${pipeline.name} B`)
    if (!second) return
    setSaving(true)
    setError(null)
    try {
      const res = await pipelineSplit(project.id, pipeline.id, first, second)
      const saved = res.data.pipelines || []
      setPipelines(saved)
      dispatch({ type: 'SET_DETECTED_PIPELINES', payload: saved })
      const sid = res.data.selected_pipeline?.id || saved[0]?.id || null
      if (sid) setSelectedId(sid)
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to split pipeline.')
    }
    setSaving(false)
  }

  const mergePipelines = async () => {
    if (mergeSelection.length < 2) return
    const mergedName = window.prompt('Merged pipeline name:', 'Merged Pipeline')
    if (!mergedName) return
    setSaving(true)
    setError(null)
    try {
      const res = await pipelineMerge(project.id, mergeSelection, mergedName)
      const saved = res.data.pipelines || []
      setPipelines(saved)
      dispatch({ type: 'SET_DETECTED_PIPELINES', payload: saved })
      setMergeSelection([])
      const sid = res.data.selected_pipeline?.id || saved[0]?.id || null
      if (sid) setSelectedId(sid)
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to merge pipelines.')
    }
    setSaving(false)
  }

  const addManualPipeline = async () => {
    const next = [...pipelines, createManualPipeline()]
    setPipelines(next)
    setExpandedId(next[next.length - 1].id)
    setSelectedId(next[next.length - 1].id)
    await persistPipelines(next, next[next.length - 1].id)
  }

  const restoreOriginalDetection = async () => {
    if (!project) return
    setSaving(true)
    setError(null)
    try {
      const res = await pipelineResetPipelines(project.id)
      const saved = res.data.pipelines || []
      const selected = res.data.selected_pipeline || saved[0] || null
      setPipelines(saved)
      dispatch({ type: 'SET_DETECTED_PIPELINES', payload: saved })
      if (selected?.id) {
        setSelectedId(selected.id)
      }
      setExpandedId(saved[0]?.id || null)
      setMergeSelection([])
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to restore original detection.')
    }
    setSaving(false)
  }

  const handleConfirm = async () => {
    const chosen = pipelines.find(p => p.id === selectedId) || null
    if (!chosen || !project) return
    await persistPipelines(pipelines, selectedId)
    try {
      await pipelineSelect(project.id, selectedId)
      dispatch({ type: 'SET_SELECTED_PIPELINE', payload: chosen })
      if (!confirmed) {
        dispatch({ type: 'CONFIRM_GATE', payload: 0 })
      } else {
        dispatch({ type: 'SET_PIPELINE_STEP', payload: 1 })
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save selected pipeline.')
    }
  }

  const gateItems = [
    {
      text: `${pipelines.length} pipeline${pipelines.length !== 1 ? 's' : ''} detected`,
      status: pipelines.length > 0 ? 'ok' : 'warn',
    },
    ...(selectedId
      ? [{ text: `Selected: ${pipelines.find(p => p.id === selectedId)?.name || selectedId}`, status: 'ok' }]
      : [{ text: 'No pipeline selected', status: 'error' }]),
  ]

  return (
    <div className="pipeline-step">
      <div className="ps-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <h3>Step 1 — Pipeline Detection</h3>
            <p>The AI analyzes your connected sources to detect distinct data pipelines, modules or flux.</p>
          </div>
          <button className="btn btn-secondary" onClick={runDetection} disabled={loading} style={{ whiteSpace: 'nowrap', marginTop: '4px' }}>
            🔄 Re-detect
          </button>
        </div>
      </div>

      {error && <div className="message error">{error}</div>}

      {loading && (
        <div className="loading">
          <div className="spinner" />
          <span>Detecting pipelines from your sources…</span>
        </div>
      )}

      {saving && <div className="message">Saving pipeline edits…</div>}

      {!loading && pipelines.length > 0 && (
        <>
          <div style={{ marginBottom: '10px', fontSize: '13px', color: 'var(--text-secondary)' }}>
            <Layers size={14} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
            <strong>{pipelines.length}</strong> pipeline{pipelines.length !== 1 ? 's' : ''} detected.
            Review, edit, then select one pipeline to generate the spec.
          </div>

          <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', flexWrap: 'wrap' }}>
            <button className="btn btn-secondary" onClick={runDetection} disabled={loading || saving}>
              🔄 Re-detect
            </button>
            <button className="btn btn-secondary" onClick={addManualPipeline} disabled={saving}>
              <Layers size={14} /> Add Pipeline
            </button>
            <button className="btn btn-secondary" onClick={mergePipelines} disabled={mergeSelection.length < 2 || saving}>
              <Combine size={14} /> Merge Selected
            </button>
            <button className="btn btn-secondary" onClick={() => persistPipelines(pipelines)} disabled={saving}>
              <Save size={14} /> Save Edits
            </button>
            <button className="btn btn-secondary" onClick={restoreOriginalDetection} disabled={saving}>
              Restore Original Detection
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
            {pipelines.map((pipeline, idx) => {
              const isSelected = selectedId === pipeline.id
              const isExpanded = expandedId === pipeline.id
              const confidencePct = Math.round((pipeline.confidence || 0) * 100)
              const explain = pipeline.explainability || {}
              return (
                <div
                  key={pipeline.id}
                  style={{
                    border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`,
                    borderRadius: '8px',
                    background: isSelected ? 'rgba(14,165,233,.08)' : 'var(--surface)',
                    overflow: 'hidden',
                    transition: 'border-color .2s',
                  }}
                >
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 14px', cursor: 'pointer' }}
                    onClick={() => setExpandedId(isExpanded ? null : pipeline.id)}
                  >
                    <input
                      type="checkbox"
                      checked={mergeSelection.includes(pipeline.id)}
                      onChange={(e) => {
                        e.stopPropagation()
                        setMergeSelection((prev) => (
                          e.target.checked
                            ? [...prev, pipeline.id]
                            : prev.filter(id => id !== pipeline.id)
                        ))
                      }}
                      style={{ width: '14px', height: '14px', cursor: 'pointer' }}
                    />
                    <input
                      type="radio"
                      name="pipeline"
                      checked={isSelected}
                      onChange={() => setSelectedId(pipeline.id)}
                      onClick={e => e.stopPropagation()}
                      style={{ accentColor: 'var(--accent)', width: '15px', height: '15px', cursor: 'pointer' }}
                    />
                    <input
                      type="text"
                      value={pipeline.name}
                      onChange={(e) => renamePipeline(pipeline.id, e.target.value)}
                      onClick={e => e.stopPropagation()}
                      onBlur={() => persistPipelines(pipelines)}
                      style={{
                        fontWeight: 700,
                        fontSize: '14px',
                        flex: 1,
                        border: '1px solid var(--border)',
                        background: 'rgba(255,255,255,.03)',
                        color: 'var(--text-primary)',
                        borderRadius: '6px',
                        padding: '4px 8px',
                      }}
                    />
                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{confidencePct}%</span>
                    <SourceBadge pipeline={pipeline} />
                    <TypeBadge type={pipeline.type} />
                    <button className="btn-icon" onClick={(e) => { e.stopPropagation(); movePipeline(pipeline.id, 'up') }} disabled={idx === 0}>
                      <ArrowUp size={12} />
                    </button>
                    <button className="btn-icon" onClick={(e) => { e.stopPropagation(); movePipeline(pipeline.id, 'down') }} disabled={idx === pipelines.length - 1}>
                      <ArrowDown size={12} />
                    </button>
                    <button className="btn-icon" onClick={(e) => { e.stopPropagation(); splitPipelineItem(pipeline) }}>
                      <Scissors size={12} />
                    </button>
                    {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>

                  {isExpanded && (
                    <div style={{
                      borderTop: '1px solid var(--border)', padding: '12px 14px', fontSize: '13px',
                      display: 'flex', flexDirection: 'column', gap: '12px',
                    }}>
                      <p style={{ color: 'var(--text-secondary)', margin: 0 }}>{pipeline.description}</p>

                      {/* Origin + Confidence + Execution Mode + Launcher */}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '14px', fontSize: '12px' }}>
                        <div><strong>Origin:</strong> {getPipelineSource(pipeline) === 'manual' ? 'Manually added' : 'AI detected'}</div>
                        <div><strong>Confidence:</strong> {confidencePct}%</div>
                        {pipeline.execution_mode && <div><strong>Execution:</strong> <span style={{ background: 'rgba(99,102,241,.15)', color: '#818cf8', borderRadius: '4px', padding: '1px 7px', fontSize: '11px' }}>{pipeline.execution_mode}</span></div>}
                        {pipeline.launcher && pipeline.launcher !== 'unknown' && <div><strong>Launcher:</strong> <span style={{ background: 'rgba(245,158,11,.12)', color: '#fbbf24', borderRadius: '4px', padding: '1px 7px', fontSize: '11px' }}>{pipeline.launcher}</span></div>}
                        {pipeline.parent_pipeline && <div><strong>Parent:</strong> <span style={{ color: 'var(--text-secondary)' }}>{pipeline.parent_pipeline}</span></div>}
                      </div>

                      {/* Triggers */}
                      {pipeline.triggers?.length > 0 && (
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '5px' }}>⚡ Triggers</span>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                            {pipeline.triggers.map((t, i) => (
                              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                                <span style={{ background: 'rgba(16,185,129,.15)', color: '#34d399', borderRadius: '4px', padding: '1px 7px', fontSize: '11px', whiteSpace: 'nowrap' }}>{t.type || 'trigger'}</span>
                                {t.detail && <span style={{ color: 'var(--text-secondary)' }}>{t.detail}</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Listen Mode */}
                      {pipeline.listen_mode?.length > 0 && (
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '5px' }}>👂 Listen Mode</span>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                            {pipeline.listen_mode.map((lm, i) => (
                              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                                <span style={{ background: 'rgba(139,92,246,.15)', color: '#a78bfa', borderRadius: '4px', padding: '1px 7px', fontSize: '11px', whiteSpace: 'nowrap' }}>{lm.type || 'listener'}</span>
                                {lm.detail && <span style={{ color: 'var(--text-secondary)' }}>{lm.detail}</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Queues / Topics */}
                      {pipeline.queues?.length > 0 && (
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '5px' }}>📨 Queues / Topics</span>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                            {pipeline.queues.map((q, i) => (
                              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '4px', background: 'rgba(255,255,255,.04)', border: '1px solid var(--border)', borderRadius: '6px', padding: '3px 8px', fontSize: '11px' }}>
                                <span style={{ fontWeight: 600 }}>{q.name}</span>
                                {q.technology && <span style={{ color: 'var(--text-secondary)' }}>{q.technology}</span>}
                                {q.role && <span style={{ background: q.role === 'input' ? 'rgba(16,185,129,.15)' : q.role === 'output' ? 'rgba(239,68,68,.15)' : 'rgba(99,102,241,.15)', color: q.role === 'input' ? '#34d399' : q.role === 'output' ? '#f87171' : '#818cf8', borderRadius: '3px', padding: '0 5px' }}>{q.role}</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Jobs */}
                      {pipeline.jobs?.length > 0 && (
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '5px' }}>⚙️ Jobs / Tasks ({pipeline.jobs.length})</span>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            {pipeline.jobs.map((job, i) => (
                              <div key={job.id || i} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', background: 'rgba(255,255,255,.03)', border: '1px solid var(--border)', borderRadius: '6px', padding: '5px 9px', fontSize: '12px' }}>
                                <span style={{ color: 'var(--text-secondary)', minWidth: '18px', fontVariantNumeric: 'tabular-nums' }}>{job.order ?? i + 1}.</span>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', flex: 1 }}>
                                  <span style={{ fontWeight: 600 }}>{job.name || job.id}</span>
                                  {job.file && <span style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>{job.file}</span>}
                                  {job.description && <span style={{ color: 'var(--text-secondary)' }}>{job.description}</span>}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Sub-pipelines */}
                      {pipeline.sub_pipelines?.length > 0 && (
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '5px' }}>🔗 Sub-pipelines</span>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                            {pipeline.sub_pipelines.map(sp => <Tag key={sp} label={sp} />)}
                          </div>
                        </div>
                      )}

                      {/* Keywords + Orchestration clues */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px' }}>
                        {explain.keywords?.length > 0 && <div><strong>Keywords:</strong> {explain.keywords.join(', ')}</div>}
                        {explain.orchestration_clues?.length > 0 && <div><strong>Orchestration clues:</strong> {explain.orchestration_clues.join(', ')}</div>}
                      </div>

                      {/* Source files / tables / technologies */}
                      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                        {(pipeline.source_files?.length > 0 || explain.evidence_files?.length > 0) && (
                          <div>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                              <GitBranch size={11} /> Source files / evidence
                            </span>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                              {[...(pipeline.source_files || []), ...(explain.evidence_files || [])].slice(0, 12).map(f => <Tag key={f} label={f} />)}
                            </div>
                          </div>
                        )}
                        {(pipeline.source_tables?.length > 0 || explain.evidence_tables?.length > 0) && (
                          <div>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                              <Database size={11} /> Tables / evidence
                            </span>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                              {[...(pipeline.source_tables || []), ...(explain.evidence_tables || [])].slice(0, 12).map(t => <Tag key={t} label={t} />)}
                            </div>
                          </div>
                        )}
                        {pipeline.technologies?.length > 0 && (
                          <div>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                              Technologies
                            </span>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                              {pipeline.technologies.map(t => <Tag key={t} label={t} />)}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}

      {!loading && pipelines.length === 0 && !error && (
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-secondary)' }}>
          <div style={{ marginBottom: '8px', fontSize: '14px' }}>No pipelines detected yet.</div>
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', flexWrap: 'wrap', marginTop: '12px' }}>
            <button className="btn btn-primary" onClick={runDetection} disabled={loading}>
              🔄 Run Detection
            </button>
            <button className="btn btn-secondary" onClick={addManualPipeline} disabled={saving}>
              <Layers size={14} /> Add Manually
            </button>
          </div>
        </div>
      )}

      {pipelines.length > 0 && (
        <ValidationGate
          title="Validation Gate — Confirm Pipeline Selection"
          summary={`${pipelines.length} pipeline${pipelines.length !== 1 ? 's' : ''} detected. Select the target pipeline.`}
          items={gateItems}
          confirmed={confirmed}
          buttonLabel="Confirm Pipeline"
          onConfirm={handleConfirm}
          disabled={!selectedId}
        />
      )}

      {confirmed && (
        <button className="btn btn-primary" onClick={handleConfirm} disabled={!selectedId || saving}>
          Continue with selected pipeline
        </button>
      )}
    </div>
  )
}
