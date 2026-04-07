import { useState } from 'react'
import { Download, FileText, FileJson, Copy, Check, Calendar, Layers, Database } from 'lucide-react'
import { useProject } from '../../context/ProjectContext'
import { pipelineExport } from '../../api'

const FORMATS = [
  { id: 'markdown', label: 'Markdown (.md)', icon: FileText },
  { id: 'json', label: 'JSON (.json)', icon: FileJson },
]

export default function ExportStep() {
  const { state } = useProject()
  const { project, spec, placeholders, validation } = state
  const [selectedFormat, setSelectedFormat] = useState('markdown')
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const sourceCount = project?.sources?.length || 0

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

  return (
    <div className="pipeline-step">
      <div className="ps-header">
        <h3>Step 4 — Export</h3>
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
