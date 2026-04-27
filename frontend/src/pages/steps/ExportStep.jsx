import { useState } from 'react'
import { Download, FileText, FileJson, Copy, Check, Calendar, Layers, Database } from 'lucide-react'
import { useProject } from '../../context/ProjectContext'
import { pipelineDiffSpecVersions, pipelineExport, pipelineGetSpecVersions, pipelinePromoteSpecVersion } from '../../api'
import { useEffect } from 'react'

const FORMATS = [
  { id: 'markdown', label: 'Markdown (.md)', icon: FileText },
  { id: 'json', label: 'JSON (.json)', icon: FileJson },
]

export default function ExportStep() {
  const { state, dispatch } = useProject()
  const { project, spec, placeholders, validation, specVersions, approvedVersionId } = state
  const [selectedFormat, setSelectedFormat] = useState('markdown')
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [fromVersionId, setFromVersionId] = useState('')
  const [toVersionId, setToVersionId] = useState('')
  const [diffData, setDiffData] = useState(null)

  const sourceCount = project?.sources?.length || 0

  useEffect(() => {
    const loadVersions = async () => {
      if (!project) return
      try {
        const res = await pipelineGetSpecVersions(project.id)
        const versions = res.data.versions || []
        dispatch({ type: 'SET_SPEC_VERSIONS', payload: versions })
        dispatch({ type: 'SET_APPROVED_VERSION', payload: res.data.approved_version_id || null })
        if (versions.length > 0) {
          const last = versions[versions.length - 1]
          const prev = versions.length > 1 ? versions[versions.length - 2] : last
          setFromVersionId(prev.id)
          setToVersionId(last.id)
        }
      } catch {
        // ignore
      }
    }
    loadVersions()
  }, [project, dispatch])

  useEffect(() => {
    const loadDiff = async () => {
      if (!project || !fromVersionId || !toVersionId) return
      try {
        const res = await pipelineDiffSpecVersions(project.id, fromVersionId, toVersionId)
        setDiffData(res.data)
      } catch {
        setDiffData(null)
      }
    }
    loadDiff()
  }, [project, fromVersionId, toVersionId])

  const handleDownload = async () => {
    if (!project) return
    setLoading(true)
    try {
      const res = await pipelineExport(project.id, selectedFormat)
      const data = res.data.data
      let blob, filename
      if (selectedFormat === 'json') {
        blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        filename = `${project.name.replace(/\s+/g, '_')}_spec.json`
      } else {
        blob = new Blob([data], { type: 'text/markdown' })
        filename = `${project.name.replace(/\s+/g, '_')}_spec.md`
      }
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* ignore */ }
    setLoading(false)
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(spec)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handlePromote = async () => {
    if (!project || !toVersionId) return
    try {
      const res = await pipelinePromoteSpecVersion(project.id, toVersionId)
      dispatch({ type: 'SET_APPROVED_VERSION', payload: res.data.approved_version_id })
      const refresh = await pipelineGetSpecVersions(project.id)
      dispatch({ type: 'SET_SPEC_VERSIONS', payload: refresh.data.versions || [] })
    } catch {
      // ignore
    }
  }

  return (
    <div className="pipeline-step">
      <div className="ps-header">
        <h3>Step 5 — Export</h3>
        <p>Your specification is ready. Choose a format and download.</p>
      </div>

      {/* Summary card */}
      <div className="export-summary">
        <div className="es-row">
          <div className="es-item">
            <Layers size={16} />
            <div>
              <div className="es-label">Project</div>
              <div className="es-value">{project?.name}</div>
            </div>
          </div>
          <div className="es-item">
            <Database size={16} />
            <div>
              <div className="es-label">Sources</div>
              <div className="es-value">{sourceCount}</div>
            </div>
          </div>
          <div className="es-item">
            <FileText size={16} />
            <div>
              <div className="es-label">Placeholders</div>
              <div className="es-value">{placeholders.length}</div>
            </div>
          </div>
          <div className="es-item">
            <Calendar size={16} />
            <div>
              <div className="es-label">Date</div>
              <div className="es-value">{new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</div>
            </div>
          </div>
        </div>
        {validation && (
          <div className={`es-validation ${validation.is_valid ? 'valid' : 'invalid'}`}>
            {validation.is_valid ? 'All fields validated' : 'Some fields incomplete'}
          </div>
        )}
      </div>

      {/* Format selector */}
      <div className="export-formats">
        {FORMATS.map(f => {
          const Icon = f.icon
          return (
            <button key={f.id}
              className={`ef-btn ${selectedFormat === f.id ? 'selected' : ''}`}
              onClick={() => setSelectedFormat(f.id)}>
              <Icon size={18} />
              {f.label}
            </button>
          )
        })}
      </div>

      {/* Actions */}
      <div className="export-actions">
        <button className="btn btn-primary export-download" onClick={handleDownload} disabled={loading}>
          <Download size={16} />
          {loading ? 'Preparing…' : `Download ${selectedFormat.toUpperCase()}`}
        </button>
        <button className="btn btn-secondary" onClick={handleCopy}>
          {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy Markdown</>}
        </button>
      </div>

      <div className="export-summary">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h4 style={{ margin: 0, fontSize: '13px' }}>Spec Versions</h4>
          <button className="btn btn-primary" onClick={handlePromote} disabled={!toVersionId || approvedVersionId === toVersionId}>
            {approvedVersionId === toVersionId ? 'Approved' : 'Promote to Approved'}
          </button>
        </div>
        <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
          <select value={fromVersionId} onChange={(e) => setFromVersionId(e.target.value)}>
            {specVersions.map(v => (
              <option key={v.id} value={v.id}>From v{v.version_number} ({v.status})</option>
            ))}
          </select>
          <select value={toVersionId} onChange={(e) => setToVersionId(e.target.value)}>
            {specVersions.map(v => (
              <option key={v.id} value={v.id}>To v{v.version_number} ({v.status})</option>
            ))}
          </select>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          Current approved version: {approvedVersionId || 'None'}
        </div>
      </div>

      {diffData && (
        <div className="spec-diff-grid">
          <div className="export-preview">
            <h4>From Version</h4>
            <pre className="ep-content">{diffData.from_spec}</pre>
          </div>
          <div className="export-preview">
            <h4>To Version</h4>
            <pre className="ep-content">{diffData.to_spec}</pre>
          </div>
          <div className="export-preview" style={{ gridColumn: '1 / -1' }}>
            <h4>Diff</h4>
            <pre className="ep-content">{diffData.diff || 'No differences'}</pre>
          </div>
        </div>
      )}

      {/* Spec preview */}
      {spec && (
        <div className="export-preview">
          <h4>Preview</h4>
          <pre className="ep-content">{spec}</pre>
        </div>
      )}
    </div>
  )
}
