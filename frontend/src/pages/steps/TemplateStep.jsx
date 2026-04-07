import { useState, useRef } from 'react'
import { Upload, Loader2, Trash2, Plus, Edit3 } from 'lucide-react'
import { useProject } from '../../context/ProjectContext'
import { pipelineTemplate } from '../../api'
import ValidationGate from '../../components/ValidationGate'

export default function TemplateStep() {
  const { state, dispatch } = useProject()
  const { project, placeholders, templateTitle, gates } = state
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [editIdx, setEditIdx] = useState(null)
  const fileRef = useRef()

  const handleUpload = async () => {
    if (!file || !project) return
    setLoading(true)
    setError(null)
    try {
      const res = await pipelineTemplate(project.id, file)
      dispatch({ type: 'SET_TEMPLATE_RESULT', payload: res.data })
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to parse template.')
    }
    setLoading(false)
  }

  const updatePlaceholder = (idx, field, value) => {
    const updated = [...placeholders]
    updated[idx] = { ...updated[idx], [field]: value }
    dispatch({ type: 'UPDATE_PLACEHOLDERS', payload: updated })
  }

  const removePlaceholder = (idx) => {
    const updated = placeholders.filter((_, i) => i !== idx)
    dispatch({ type: 'UPDATE_PLACEHOLDERS', payload: updated })
  }

  const addPlaceholder = () => {
    const newPh = {
      id: `custom_${Date.now()}`,
      label: 'New Placeholder',
      section: '',
      type: 'text',
      description: '',
      required: true,
      options: null,
    }
    dispatch({ type: 'UPDATE_PLACEHOLDERS', payload: [...placeholders, newPh] })
  }

  const confirmed = gates[0]

  // Summary items for the gate
  const gateItems = [
    { text: `${placeholders.length} placeholder${placeholders.length !== 1 ? 's' : ''} detected`, status: placeholders.length > 0 ? 'ok' : 'warn' },
    ...[...new Set(placeholders.map(p => p.section).filter(Boolean))].map(s => ({ text: `Section: ${s}`, status: 'ok' })),
  ]

  return (
    <div className="pipeline-step">
      <div className="ps-header">
        <h3>Step 1 — Template Agent</h3>
        <p>Upload a template file. The AI will parse it and extract all placeholders.</p>
      </div>

      {/* Upload area */}
      {placeholders.length === 0 && !loading && (
        <div className="upload-area">
          <input ref={fileRef} type="file" accept=".pdf,.md,.txt" style={{ display: 'none' }}
            onChange={e => setFile(e.target.files[0] || null)} />
          <button className="btn btn-secondary upload-btn" onClick={() => fileRef.current?.click()}>
            <Upload size={16} />
            {file ? file.name : 'Choose template (.pdf, .md, .txt)'}
          </button>
          {file && (
            <button className="btn btn-primary" onClick={handleUpload}>
              <Upload size={14} /> Parse Template
            </button>
          )}
        </div>
      )}

      {error && <div className="message error">{error}</div>}

      {loading && (
        <div className="loading">
          <div className="spinner" />
          <span>Parsing template and detecting placeholders…</span>
        </div>
      )}

      {/* Placeholder review panel */}
      {placeholders.length > 0 && (
        <div className="placeholder-panel">
          {templateTitle && <div className="pp-title">Template: {templateTitle}</div>}
          <table className="pp-table">
            <thead>
              <tr>
                <th>Placeholder</th>
                <th>Section</th>
                <th>Type</th>
                <th style={{ width: 70 }}></th>
              </tr>
            </thead>
            <tbody>
              {placeholders.map((ph, i) => (
                <tr key={ph.id} className={confirmed ? 'locked' : ''}>
                  <td>
                    {editIdx === i && !confirmed ? (
                      <input type="text" value={ph.label}
                        onChange={e => updatePlaceholder(i, 'label', e.target.value)}
                        onBlur={() => setEditIdx(null)}
                        autoFocus />
                    ) : (
                      <span className="pp-label" onClick={() => !confirmed && setEditIdx(i)}>
                        {ph.label}
                        {!confirmed && <Edit3 size={11} className="pp-edit-icon" />}
                      </span>
                    )}
                  </td>
                  <td className="pp-section">{ph.section || '—'}</td>
                  <td>
                    {!confirmed ? (
                      <select value={ph.type || 'text'}
                        onChange={e => updatePlaceholder(i, 'type', e.target.value)}>
                        <option value="text">Text</option>
                        <option value="paragraph">Paragraph</option>
                        <option value="list">List</option>
                        <option value="choice">Choice</option>
                        <option value="table">Table</option>
                      </select>
                    ) : (
                      <span className="pp-type-badge">{ph.type}</span>
                    )}
                  </td>
                  <td>
                    {!confirmed && (
                      <button className="btn-icon danger" onClick={() => removePlaceholder(i)}>
                        <Trash2 size={13} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!confirmed && (
            <button className="btn btn-secondary pp-add" onClick={addPlaceholder}>
              <Plus size={14} /> Add Placeholder
            </button>
          )}
        </div>
      )}

      {/* Validation Gate 1 */}
      {placeholders.length > 0 && (
        <ValidationGate
          title="Validation Gate 1 — Confirm Placeholders"
          summary={`${placeholders.length} placeholder${placeholders.length !== 1 ? 's' : ''} extracted from template.`}
          items={gateItems}
          confirmed={confirmed}
          buttonLabel="Confirm Placeholders"
          onConfirm={() => dispatch({ type: 'CONFIRM_GATE', payload: 0 })}
        />
      )}
    </div>
  )
}
