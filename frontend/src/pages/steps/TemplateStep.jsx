import { useState, useRef, useEffect } from 'react'
import { Upload, Trash2, Plus, Edit3, FileText, PenLine, ArrowLeft, BookMarked, Save, X } from 'lucide-react'
import { useProject } from '../../context/ProjectContext'
import { pipelineTemplate, getPlaceholderPresets, savePlaceholderPreset, deletePlaceholderPreset } from '../../api'
import ValidationGate from '../../components/ValidationGate'

export default function TemplateStep() {
  const { state, dispatch } = useProject()
  const { project, placeholders, templateTitle, gates } = state

  // 'upload' | 'manual' | 'preset' | null (null = show mode selector)
  const [mode, setMode] = useState(placeholders.length > 0 ? 'upload' : null)
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [editIdx, setEditIdx] = useState(null)
  const [editField, setEditField] = useState(null) // 'label' | 'section'
  const fileRef = useRef()

  // Preset state
  const [presets, setPresets] = useState([])
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [presetSaving, setPresetSaving] = useState(false)
  const [presetError, setPresetError] = useState(null)

  useEffect(() => {
    getPlaceholderPresets().then(r => setPresets(r.data.presets || [])).catch(() => {})
  }, [])

  const handleSavePreset = async () => {
    if (!presetName.trim()) return
    setPresetSaving(true)
    setPresetError(null)
    try {
      const res = await savePlaceholderPreset(presetName.trim(), placeholders)
      setPresets(prev => [res.data, ...prev])
      setShowSaveModal(false)
      setPresetName('')
    } catch (err) {
      setPresetError(err.response?.data?.detail || 'Failed to save preset.')
    }
    setPresetSaving(false)
  }

  const handleLoadPreset = (preset) => {
    dispatch({ type: 'SET_TEMPLATE_RESULT', payload: { template_title: preset.name, placeholders: preset.placeholders } })
    setMode('upload') // reuse upload mode to show placeholder panel
  }

  const handleDeletePreset = async (e, presetId) => {
    e.stopPropagation()
    try {
      await deletePlaceholderPreset(presetId)
      setPresets(prev => prev.filter(p => p.id !== presetId))
    } catch {}
  }

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
    // Auto-open inline edit on the new row
    setEditIdx(placeholders.length)
    setEditField('label')
  }

  const handleBack = () => {
    setMode(null)
    setFile(null)
    setError(null)
  }

  const confirmed = gates[1]

  const gateItems = [
    { text: `${placeholders.length} placeholder${placeholders.length !== 1 ? 's' : ''} defined`, status: placeholders.length > 0 ? 'ok' : 'warn' },
    ...[...new Set(placeholders.map(p => p.section).filter(Boolean))].map(s => ({ text: `Section: ${s}`, status: 'ok' })),
  ]

  const showPanel = placeholders.length > 0 || mode === 'manual'

  return (
    <div className="pipeline-step">
      <div className="ps-header">
        <h3>Step 2 — Template Agent</h3>
        <p>
          {mode === 'upload' ? 'Upload a template file — the AI will extract all placeholders automatically.'
            : mode === 'manual' ? 'Define your placeholders manually. Add, rename, and type each field.'
            : 'Choose how to define the spec placeholders for this pipeline.'}
        </p>
      </div>

      {/* ── Mode selector ── */}
      {!mode && !confirmed && (
        <div className="template-mode-selector">
          <button className="mode-card" onClick={() => setMode('upload')}>
            <div className="mode-card-icon"><FileText size={28} /></div>
            <div className="mode-card-body">
              <span className="mode-card-title">Upload a Template</span>
              <span className="mode-card-desc">Provide a .pdf, .md or .txt spec template and let the AI detect all placeholders automatically.</span>
            </div>
          </button>
          <button className="mode-card" onClick={() => setMode('manual')}>
            <div className="mode-card-icon"><PenLine size={28} /></div>
            <div className="mode-card-body">
              <span className="mode-card-title">Enter Manually</span>
              <span className="mode-card-desc">Type in the placeholder names, sections and types yourself — no template file needed.</span>
            </div>
          </button>
          <button className="mode-card" onClick={() => setMode('preset')} disabled={presets.length === 0}>
            <div className="mode-card-icon"><BookMarked size={28} /></div>
            <div className="mode-card-body">
              <span className="mode-card-title">Load a Preset</span>
              <span className="mode-card-desc">
                {presets.length === 0 ? 'No saved presets yet — save one after defining placeholders.' : `${presets.length} saved preset${presets.length !== 1 ? 's' : ''} available.`}
              </span>
            </div>
          </button>
        </div>
      )}

      {/* ── Preset picker ── */}
      {mode === 'preset' && !confirmed && (
        <div className="placeholder-panel">
          <div className="pp-title">Select a preset to load</div>
          {presets.length === 0 ? (
            <p className="pp-empty-hint">No saved presets yet.</p>
          ) : (
            <div className="preset-list">
              {presets.map(p => (
                <div key={p.id} className="preset-item" onClick={() => handleLoadPreset(p)}>
                  <div className="preset-item-info">
                    <span className="preset-item-name">{p.name}</span>
                    <span className="preset-item-count">{p.placeholders.length} placeholders</span>
                  </div>
                  <button className="btn-icon danger" onClick={e => handleDeletePreset(e, p.id)}><Trash2 size={13} /></button>
                </div>
              ))}
            </div>
          )}
          <button className="btn-text pp-back" onClick={() => setMode(null)}><ArrowLeft size={13} /> Back</button>
        </div>
      )}

      {/* ── Back link (shown when a mode is chosen but not yet confirmed) ── */}
      {mode && !confirmed && placeholders.length === 0 && (
        <button className="btn-text pp-back" onClick={handleBack}>
          <ArrowLeft size={13} /> Change method
        </button>
      )}

      {/* ── Upload UI ── */}
      {mode === 'upload' && placeholders.length === 0 && !loading && (
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

      {/* ── Placeholder panel (upload review OR manual entry) ── */}
      {showPanel && (
        <div className="placeholder-panel">
          {templateTitle && <div className="pp-title">Template: {templateTitle}</div>}
          {mode === 'manual' && placeholders.length === 0 && (
            <p className="pp-empty-hint">No placeholders yet — click <strong>Add Placeholder</strong> below to start.</p>
          )}
          {placeholders.length > 0 && (
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
                      {editIdx === i && editField === 'label' && !confirmed ? (
                        <input type="text" value={ph.label}
                          onChange={e => updatePlaceholder(i, 'label', e.target.value)}
                          onBlur={() => { setEditIdx(null); setEditField(null) }}
                          autoFocus />
                      ) : (
                        <span className="pp-label" onClick={() => { if (!confirmed) { setEditIdx(i); setEditField('label') } }}>
                          {ph.label}
                          {!confirmed && <Edit3 size={11} className="pp-edit-icon" />}
                        </span>
                      )}
                    </td>
                    <td className="pp-section">
                      {editIdx === i && editField === 'section' && !confirmed ? (
                        <input type="text" value={ph.section || ''}
                          placeholder="Section name"
                          onChange={e => updatePlaceholder(i, 'section', e.target.value)}
                          onBlur={() => { setEditIdx(null); setEditField(null) }}
                          autoFocus />
                      ) : (
                        <span className="pp-label" onClick={() => { if (!confirmed) { setEditIdx(i); setEditField('section') } }}>
                          {ph.section || <span style={{ opacity: 0.4 }}>—</span>}
                          {!confirmed && <Edit3 size={11} className="pp-edit-icon" />}
                        </span>
                      )}
                    </td>
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
          )}
          {!confirmed && (
            <div className="pp-actions-row">
              <button className="btn btn-secondary pp-add" onClick={addPlaceholder}>
                <Plus size={14} /> Add Placeholder
              </button>
              <button className="btn btn-secondary" onClick={() => { setPresetName(''); setShowSaveModal(true) }}>
                <Save size={14} /> Save as Preset
              </button>
            </div>
          )}
          {confirmed && (
            <div className="pp-actions-row">
              <button className="btn btn-secondary" onClick={() => { setPresetName(''); setShowSaveModal(true) }}>
                <Save size={14} /> Save as Preset
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Validation Gate 2 ── */}
      {placeholders.length > 0 && (
        <ValidationGate
          title="Validation Gate 2 — Confirm Placeholders"
          summary={`${placeholders.length} placeholder${placeholders.length !== 1 ? 's' : ''} ${mode === 'manual' ? 'defined manually' : 'extracted from template'}.`}
          items={gateItems}
          confirmed={confirmed}
          buttonLabel="Confirm Placeholders"
          onConfirm={() => dispatch({ type: 'CONFIRM_GATE', payload: 1 })}
        />
      )}
      {/* ── Save preset modal ── */}
      {showSaveModal && (
        <div className="preset-modal-overlay" onClick={() => setShowSaveModal(false)}>
          <div className="preset-modal" onClick={e => e.stopPropagation()}>
            <div className="preset-modal-header">
              <span>Save as Preset</span>
              <button className="btn-icon" onClick={() => setShowSaveModal(false)}><X size={15} /></button>
            </div>
            <p className="preset-modal-hint">{placeholders.length} placeholder{placeholders.length !== 1 ? 's' : ''} will be saved.</p>
            <input
              className="preset-name-input"
              type="text"
              placeholder="Preset name (e.g. JEMS DataFlow Template)"
              value={presetName}
              onChange={e => setPresetName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSavePreset()}
              autoFocus
            />
            {presetError && <div className="message error">{presetError}</div>}
            <div className="preset-modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowSaveModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSavePreset} disabled={presetSaving || !presetName.trim()}>
                {presetSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
