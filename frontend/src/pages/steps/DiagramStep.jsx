import { useState, useEffect, useRef } from 'react'
import { GitBranch, RefreshCw, Download, Copy, Check, AlertTriangle } from 'lucide-react'
import { useProject } from '../../context/ProjectContext'
import { pipelineDiagram } from '../../api'
import ValidationGate from '../../components/ValidationGate'

export default function DiagramStep() {
  const { state, dispatch } = useProject()
  const { project, selectedPipeline, confirmedValues, placeholders, gates, diagramCode } = state
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [code, setCode] = useState(diagramCode || '')
  const [editMode, setEditMode] = useState(false)
  const [copied, setCopied] = useState(false)
  const diagramRef = useRef(null)
  const mermaidRef = useRef(null)

  const confirmed = gates[3]

  // Load mermaid from CDN once
  useEffect(() => {
    if (window.mermaid) { mermaidRef.current = window.mermaid; return }
    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js'
    script.onload = () => {
      window.mermaid.initialize({
        startOnLoad: false,
        theme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'default',
        flowchart: { curve: 'basis' },
      })
      mermaidRef.current = window.mermaid
      if (code) renderDiagram(code)
    }
    document.head.appendChild(script)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fetch diagram on mount
  useEffect(() => {
    if (!code && !loading) {
      fetchDiagram()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Re-render when code changes
  useEffect(() => {
    if (code && mermaidRef.current) {
      renderDiagram(code)
    }
  }, [code]) // eslint-disable-line react-hooks/exhaustive-deps

  const renderDiagram = async (mermaidCode) => {
    if (!diagramRef.current || !mermaidRef.current) return
    try {
      diagramRef.current.innerHTML = ''
      const id = `mermaid-${Date.now()}`
      const { svg } = await mermaidRef.current.render(id, mermaidCode)
      diagramRef.current.innerHTML = svg
    } catch (e) {
      diagramRef.current.innerHTML = `<pre style="color:var(--danger);font-size:12px;white-space:pre-wrap">${e.message}</pre>`
    }
  }

  const fetchDiagram = async () => {
    if (!project) return
    setLoading(true)
    setError(null)
    try {
      const res = await pipelineDiagram(project.id)
      const mermaidCode = res.data.mermaid || ''
      setCode(mermaidCode)
      dispatch({ type: 'SET_DIAGRAM', payload: mermaidCode })
    } catch (err) {
      setError(err.response?.data?.detail || 'Diagram generation failed.')
    }
    setLoading(false)
  }

  const handleConfirm = () => {
    dispatch({ type: 'CONFIRM_GATE', payload: 3 })
  }

  const handleSkip = () => {
    // Mark gate 3 as confirmed and advance without generating a diagram
    dispatch({ type: 'CONFIRM_GATE', payload: 3 })
  }

  const handleCopyCode = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handleDownloadSvg = () => {
    if (!diagramRef.current) return
    const svg = diagramRef.current.innerHTML
    const blob = new Blob([svg], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${project?.name?.replace(/\s+/g, '_') || 'pipeline'}_diagram.svg`
    a.click()
    URL.revokeObjectURL(url)
  }

  const gateItems = [
    { text: `${placeholders.length} placeholders mapped`, status: 'ok' },
    { text: code ? 'Diagram generated' : 'Diagram not generated', status: code ? 'ok' : 'warn' },
    selectedPipeline ? { text: `Pipeline: ${selectedPipeline.name}`, status: 'ok' } : null,
  ].filter(Boolean)

  return (
    <div className="pipeline-step">
      <div className="ps-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem' }}>
          <div>
            <h3>Step 4 — Diagram Agent</h3>
            <p>Visual representation of your pipeline's data flow.</p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
            {code && !editMode && (
              <>
                <button className="btn btn-secondary" onClick={handleCopyCode} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? 'Copied' : 'Copy code'}
                </button>
                <button className="btn btn-secondary" onClick={handleDownloadSvg} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Download size={14} /> SVG
                </button>
                <button className="btn btn-secondary" onClick={() => setEditMode(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  Edit
                </button>
              </>
            )}
            <button
              className="btn btn-secondary"
              onClick={fetchDiagram}
              disabled={loading}
              style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}
            >
              <RefreshCw size={14} /> Regenerate
            </button>
          </div>
        </div>
      </div>

      {error && <div className="message error"><AlertTriangle size={14} style={{ marginRight: 6 }} />{error}</div>}

      {loading && (
        <div className="loading">
          <div className="spinner" />
          <span>Generating pipeline diagram…</span>
        </div>
      )}

      {!loading && !code && !error && (
        <div className="pd-empty" style={{ marginTop: 24 }}>
          <div className="pd-empty-icon"><GitBranch size={22} /></div>
          <div className="pd-empty-title">No diagram yet</div>
          <p className="pd-empty-sub">Click "Regenerate" to build the flow diagram from your extraction results.</p>
        </div>
      )}

      {!loading && code && (
        <div className="diagram-container" style={{ marginTop: 16 }}>
          {editMode ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <textarea
                className="ex-value-input"
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12, minHeight: 240, resize: 'vertical' }}
                value={code}
                onChange={e => setCode(e.target.value)}
                rows={14}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" onClick={() => { renderDiagram(code); setEditMode(false) }}>
                  Apply Changes
                </button>
                <button className="btn btn-secondary" onClick={() => setEditMode(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div
              ref={diagramRef}
              className="diagram-render"
              style={{
                background: 'var(--bg-surface)',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
                padding: '24px',
                overflow: 'auto',
                minHeight: 200,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            />
          )}
        </div>
      )}

      {!loading && (
        <ValidationGate
          title="Validation Gate 4 — Confirm Diagram"
          summary={code ? 'Diagram generated from pipeline data. Review and proceed to export.' : 'Diagram not yet generated.'}
          items={gateItems}
          confirmed={confirmed}
          buttonLabel="Confirm Diagram & Continue"
          onConfirm={handleConfirm}
        />
      )}

      {!loading && !confirmed && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
          <button
            className="btn btn-secondary"
            onClick={handleSkip}
            style={{ fontSize: 12.5, color: 'var(--text-tertiary)' }}
          >
            Skip diagram →
          </button>
        </div>
      )}
    </div>
  )
}
