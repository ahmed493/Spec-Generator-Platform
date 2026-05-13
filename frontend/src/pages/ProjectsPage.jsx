import { useState, useEffect, useRef } from 'react'
import {
  Plus, FolderOpen, Trash2, ArrowLeft, Zap, Loader2, X,
  CheckCircle, AlertCircle, Link2, FileText, Globe, AlignLeft,
  Github, Database, Cloud, BarChart3, HardDrive, BookOpen, FileSpreadsheet,
  Search, Unplug, ScrollText, Download, Copy, Check, BookMarked, Clock,
  ChevronDown, ChevronRight, UploadCloud, FileUp, Pencil, Save,
} from 'lucide-react'
import {
  getProjects, createProject, deleteProject,
  getProject, addProjectSource, removeProjectSource,
  getProjectApprovedSpecs,
  getConnections,
  getGitHubRepos, getBigQueryDatasets, getPostgreSQLSchemas,
  getPowerBIWorkspaces, getGCSBuckets,
  pipelineGetCatalog,
  uploadProjectFile,
  pipelineTemplate,
  getPlaceholderPresets, savePlaceholderPreset, deletePlaceholderPreset,
} from '../api'
import { useProject } from '../context/ProjectContext'

/* ============================================================
   SOURCE TYPE DEFINITIONS
   mcpKey  → links to an MCP server connection (checked via /connections)
   fetchFn → function to load available resources when connected
   parseRes → extracts the items array from the API response
   itemLabel → how to display each resource item
   itemValue → the config key + value to store when selecting
============================================================ */
const SOURCE_TYPES = [
  // ── MCP-backed sources ──
  { id: 'github',     name: 'GitHub Repo',   icon: Github,       bg: 'rgba(31,41,55,.55)',
    mcpKey: 'github',     fetchFn: getGitHubRepos,      parseRes: r => r.data.repos || [],
    itemLabel: i => i.name + (i.description ? ` — ${i.description}` : ''),
    itemValue: i => ({ label: i.name, config: { owner: i.owner, repo: i.name } }) },
  { id: 'bigquery',   name: 'BigQuery',      icon: Database,     bg: 'rgba(66,133,244,.14)',
    mcpKey: 'bigquery',   fetchFn: getBigQueryDatasets,  parseRes: r => r.data || [],
    itemLabel: i => i.dataset_id,
    itemValue: i => ({ label: i.dataset_id, config: { dataset: i.dataset_id, project: i.project } }) },
  { id: 'postgresql', name: 'PostgreSQL',    icon: HardDrive,    bg: 'rgba(51,103,145,.18)',
    mcpKey: 'postgresql', fetchFn: getPostgreSQLSchemas, parseRes: r => r.data || [],
    itemLabel: i => i.schema_name,
    itemValue: i => ({ label: i.schema_name, config: { schema: i.schema_name } }) },
  { id: 'powerbi',    name: 'Power BI',      icon: BarChart3,    bg: 'rgba(245,189,68,.12)',
    mcpKey: 'powerbi',    fetchFn: getPowerBIWorkspaces, parseRes: r => r.data || [],
    itemLabel: i => i.name,
    itemValue: i => ({ label: i.name, config: { workspace_id: i.id, workspace_name: i.name } }) },
  { id: 'gcs',        name: 'Cloud Storage', icon: Cloud,        bg: 'rgba(52,168,83,.12)',
    mcpKey: 'gcs',        fetchFn: getGCSBuckets,        parseRes: r => r.data || [],
    itemLabel: i => i.name + (i.location ? ` (${i.location})` : ''),
    itemValue: i => ({ label: i.name, config: { bucket: i.name } }) },
  // ── Manual sources ──
  // ── File upload sources ──
  { id: 'pdf',        name: 'PDF / Document', icon: FileUp,          bg: 'rgba(220,38,38,.14)',
    fileUpload: true, accept: '.pdf,.txt,.md,.csv,.docx',
    acceptLabel: 'PDF, TXT, Markdown, CSV, DOCX' },
  { id: 'notion',     name: 'Notion Page',   icon: BookOpen,     bg: 'rgba(55,65,81,.45)',
    fields: [{ id:'url', label:'Notion page URL', ph:'https://notion.so/…' }] },
  { id: 'googledoc',  name: 'Google Doc',    icon: FileSpreadsheet, bg: 'rgba(29,78,216,.14)',
    fields: [{ id:'url', label:'Google Doc share URL', ph:'https://docs.google.com/…' }] },
  { id: 'text',       name: 'Plain Text',    icon: AlignLeft,    bg: 'rgba(74,85,104,.28)',
    fields: [{ id:'content', label:'Paste your text', ph:'Enter or paste text…', multi: true }] },
  { id: 'api',        name: 'REST API',      icon: Zap,          bg: 'rgba(124,58,237,.14)',
    fields: [{ id:'url', label:'Endpoint URL', ph:'https://api.example.com/spec' }] },
  { id: 'url',        name: 'Web URL',       icon: Globe,        bg: 'rgba(8,145,178,.13)',
    fields: [{ id:'url', label:'Page URL', ph:'https://docs.example.com/overview' }] },
  { id: 'database',   name: 'DB Schema',     icon: Database,     bg: 'rgba(6,95,70,.22)',
    fields: [{ id:'conn', label:'Connection string', ph:'postgresql://localhost/mydb' }] },
]

function getTypeInfo(id) {
  return SOURCE_TYPES.find(t => t.id === id) || SOURCE_TYPES[0]
}

/* ============================================================
   NEW PROJECT MODAL
============================================================ */
function NewProjectModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef()

  useEffect(() => { inputRef.current?.focus() }, [])

  const handleCreate = async (e) => {
    e?.preventDefault()
    if (!name.trim()) return setError('Project name is required')
    setLoading(true)
    setError(null)
    try {
      const res = await createProject(name.trim(), desc.trim())
      onCreated(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create project')
    }
    setLoading(false)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 440 }}>
        <div className="modal-header">
          <div className="modal-title-row">
            <FolderOpen size={18} />
            <h3>New Project</h3>
          </div>
          <button className="modal-close" onClick={onClose}><X size={16} /></button>
        </div>
        <form onSubmit={handleCreate}>
          {error && <div className="message error">{error}</div>}
          <label>Project name <span style={{ color: 'var(--danger)' }}>*</span></label>
          <input
            ref={inputRef} type="text" placeholder="e.g. Payments API v2"
            value={name} onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCreate()}
          />
          <label>Description <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>(optional)</span></label>
          <textarea
            style={{ width:'100%', minHeight:72, resize:'vertical', padding:'9px 14px',
              background:'var(--bg-surface)', border:'1px solid var(--border)',
              borderRadius:'var(--radius-sm)', color:'var(--text-primary)',
              fontSize:13, fontFamily:'var(--font-body)' }}
            placeholder="What is this project about?"
            value={desc} onChange={e => setDesc(e.target.value)}
          />
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? <><Loader2 size={14} className="spinner" /> Creating…</> : 'Create Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/* ============================================================
   ADD SOURCE MODAL — with MCP connection check + resource browsing
============================================================ */
function AddSourceModal({ project, onClose, onAdded }) {
  const [selected, setSelected] = useState(null)
  const [fieldValues, setFieldValues] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)

  // MCP connection status + resource browsing
  const [connStatus, setConnStatus] = useState({})    // { github: true, bigquery: false, … }
  const [resources, setResources] = useState([])       // fetched resources for MCP type
  const [loadingRes, setLoadingRes] = useState(false)
  const [selectedResource, setSelectedResource] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Fetch connection statuses on mount
  useEffect(() => {
    getConnections()
      .then(res => setConnStatus(res.data || {}))
      .catch(() => setConnStatus({}))
  }, [])

  const handleSelect = async (typeId) => {
    setSelected(typeId)
    setFieldValues({})
    setError(null)
    setResources([])
    setSelectedResource(null)
    setSearchQuery('')
    setSelectedFile(null)

    const t = getTypeInfo(typeId)
    // If MCP-backed and connected, fetch resources
    if (t.mcpKey && connStatus[t.mcpKey]) {
      setLoadingRes(true)
      try {
        const res = await t.fetchFn()
        setResources(t.parseRes(res))
      } catch (err) {
        setError('Failed to fetch resources. Check your connection.')
      }
      setLoadingRes(false)
    }
  }

  const handleConnect = async () => {
    if (!selected) return
    const t = getTypeInfo(selected)
    setLoading(true)
    setError(null)
    try {
      // File upload path
      if (t.fileUpload) {
        if (!selectedFile) { setError('Please select a file.'); setLoading(false); return }
        const formData = new FormData()
        formData.append('file', selectedFile)
        const res = await uploadProjectFile(project.id, formData)
        onAdded(res.data)
        return
      }
      let label, config
      if (t.mcpKey && selectedResource) {
        const v = t.itemValue(selectedResource)
        label = v.label
        config = v.config
      } else if (t.fields) {
        const firstField = t.fields[0]
        label = fieldValues[firstField.id]?.trim() || ''
        config = {}
        t.fields.forEach(f => { config[f.id] = fieldValues[f.id] || '' })
      } else {
        return
      }
      const res = await addProjectSource(project.id, selected, label, config)
      onAdded(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add source')
      setLoading(false)
    }
  }

  const t = selected ? getTypeInfo(selected) : null
  const isMcp = t?.mcpKey
  const isConnected = isMcp && connStatus[t.mcpKey]
  const filteredResources = resources.filter(r =>
    t?.itemLabel(r).toLowerCase().includes(searchQuery.toLowerCase())
  )

  const canSubmit = t?.fileUpload
    ? !!selectedFile
    : isMcp
      ? !!selectedResource
      : selected && t?.fields

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 620 }}>
        <div className="modal-header">
          <div className="modal-title-row">
            <Link2 size={18} />
            <h3>Add a Source</h3>
          </div>
          <button className="modal-close" onClick={onClose}><X size={16} /></button>
        </div>
        <p className="modal-desc">Pick a source type to connect to this project:</p>

        {error && <div className="message error">{error}</div>}

        {/* Source type grid — icons, no emojis */}
        <div className="source-type-grid">
          {SOURCE_TYPES.map(st => {
            const Icon = st.icon
            const connected = st.mcpKey ? connStatus[st.mcpKey] : null
            return (
              <div
                key={st.id}
                className={`st-card${selected === st.id ? ' selected' : ''}`}
                onClick={() => handleSelect(st.id)}
              >
                <div className="st-icon" style={{ background: st.bg }}>
                  <Icon size={18} />
                </div>
                <div className="st-name">{st.name}</div>
                {st.mcpKey && (
                  <span className={`st-conn-dot ${connected ? 'on' : 'off'}`} />
                )}
              </div>
            )
          })}
        </div>

        {/* ── MCP-backed type: resource browser ── */}
        {isMcp && !isConnected && (
          <div className="src-config-section">
            <div className="src-not-connected">
              <Unplug size={18} />
              <div>
                <strong>{t.name} is not connected.</strong>
                <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--text-tertiary)' }}>
                  Go to the <strong>Connections</strong> page to set up this source first.
                </p>
              </div>
            </div>
          </div>
        )}

        {isMcp && isConnected && (
          <div className="src-config-section">
            <div className="src-config-head">
              {(() => { const I = t.icon; return <I size={16} /> })()}
              Browse {t.name}
            </div>

            {loadingRes && (
              <div className="loading" style={{ padding: '20px 0' }}>
                <div className="spinner" /><span>Loading resources…</span>
              </div>
            )}

            {!loadingRes && resources.length === 0 && (
              <p style={{ color: 'var(--text-tertiary)', fontSize: 13, textAlign: 'center', padding: '18px 0' }}>
                No resources found for this connection.
              </p>
            )}

            {!loadingRes && resources.length > 0 && (
              <>
                {resources.length > 5 && (
                  <div className="resource-search-wrap">
                    <Search size={14} />
                    <input
                      type="text" placeholder="Search…"
                      value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                    />
                  </div>
                )}
                <div className="resource-list">
                  {filteredResources.map((item, idx) => (
                    <div
                      key={idx}
                      className={`resource-item${selectedResource === item ? ' selected' : ''}`}
                      onClick={() => setSelectedResource(item)}
                    >
                      <div className="resource-item-icon" style={{ background: t.bg }}>
                        {(() => { const I = t.icon; return <I size={14} /> })()}
                      </div>
                      <span className="resource-item-label">{t.itemLabel(item)}</span>
                      {selectedResource === item && <CheckCircle size={14} className="resource-check" />}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* ── File upload type ── */}
        {!isMcp && t?.fileUpload && (
          <div className="src-config-section">
            <div className="src-config-head">
              {(() => { const I = t.icon; return <I size={16} /> })()}
              Upload {t.name}
            </div>
            <p style={{ fontSize: 12.5, color: 'var(--text-tertiary)', margin: '0 0 10px' }}>
              Accepted formats: {t.acceptLabel}
            </p>
            <label
              htmlFor="file-upload-input"
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
                padding: '24px 16px', border: '2px dashed var(--border)', borderRadius: 'var(--radius)',
                cursor: 'pointer', background: 'var(--bg-surface)',
                transition: 'border-color .15s',
              }}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) setSelectedFile(f) }}
            >
              <UploadCloud size={28} style={{ color: 'var(--text-tertiary)' }} />
              {selectedFile
                ? <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{selectedFile.name}</span>
                : <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>Click to browse or drag & drop</span>
              }
              <input
                id="file-upload-input"
                type="file"
                accept={t.accept}
                style={{ display: 'none' }}
                onChange={e => setSelectedFile(e.target.files[0] || null)}
              />
            </label>
          </div>
        )}

        {/* ── Manual source: input fields ── */}
        {!isMcp && t?.fields && (
          <div className="src-config-section">
            <div className="src-config-head">
              {(() => { const I = t.icon; return <I size={16} /> })()}
              Configure {t.name}
            </div>
            {t.fields.map(f => (
              <div key={f.id} style={{ marginBottom: 12 }}>
                <label>{f.label}</label>
                {f.multi ? (
                  <textarea
                    style={{ width:'100%', minHeight:78, resize:'vertical', padding:'9px 14px',
                      background:'var(--bg-surface)', border:'1px solid var(--border)',
                      borderRadius:'var(--radius-sm)', color:'var(--text-primary)',
                      fontSize:13, fontFamily:'var(--font-body)' }}
                    placeholder={f.ph}
                    value={fieldValues[f.id] || ''}
                    onChange={e => setFieldValues(v => ({ ...v, [f.id]: e.target.value }))}
                  />
                ) : (
                  <input
                    type="text" placeholder={f.ph}
                    value={fieldValues[f.id] || ''}
                    onChange={e => setFieldValues(v => ({ ...v, [f.id]: e.target.value }))}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          {canSubmit && (
            <button className="btn btn-primary" onClick={handleConnect} disabled={loading}>
              {loading ? <><Loader2 size={14} className="spinner" /> Adding…</> : 'Add Source'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/* ============================================================
   PROJECT TEMPLATE PANEL
   Lets users configure the spec template at the project level
   (upload, manual, or preset) before launching the pipeline.
============================================================ */
function ProjectTemplatePanel({ project, onConfigured }) {
  const { dispatch } = useProject()
  const [mode, setMode] = useState('upload')   // 'upload' | 'manual' | 'preset'
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [placeholders, setPlaceholders] = useState([])
  const [templateTitle, setTemplateTitle] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [editIdx, setEditIdx] = useState(null)
  const [editField, setEditField] = useState(null) // 'label' | 'section'
  // Presets
  const [presets, setPresets] = useState([])
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [presetSaving, setPresetSaving] = useState(false)
  const [presetError, setPresetError] = useState(null)
  const fileRef = useRef(null)

  useEffect(() => {
    getPlaceholderPresets().then(r => setPresets(r.data.presets || [])).catch(() => {})
  }, [])

  const handleUpload = async () => {
    if (!file) return
    setLoading(true); setError(null)
    try {
      const res = await pipelineTemplate(project.id, file)
      setTemplateTitle(res.data.template_title || file.name)
      setPlaceholders(res.data.placeholders || [])
      setConfirmed(false)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to parse template.')
    }
    setLoading(false)
  }

  const handleLoadPreset = (preset) => {
    setPlaceholders(preset.placeholders || [])
    setTemplateTitle(preset.name)
    setConfirmed(false)
    setMode('upload')
  }

  const handleConfirm = () => {
    dispatch({
      type: 'SET_PROJECT_TEMPLATE',
      payload: { template_title: templateTitle, placeholders },
    })
    setConfirmed(true)
    onConfigured?.()
  }

  const handleSavePreset = async () => {
    if (!presetName.trim() || placeholders.length === 0) return
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

  const handleDeletePreset = async (e, presetId) => {
    e.stopPropagation()
    try {
      await deletePlaceholderPreset(presetId)
      setPresets(prev => prev.filter(p => p.id !== presetId))
    } catch {}
  }

  const updatePlaceholder = (idx, field, value) => {
    const updated = [...placeholders]
    updated[idx] = { ...updated[idx], [field]: value }
    setPlaceholders(updated)
  }

  const removePlaceholder = (idx) => {
    setPlaceholders(placeholders.filter((_, i) => i !== idx))
  }

  const addPlaceholder = () => {
    const newPh = { id: `custom_${Date.now()}`, label: 'New Placeholder', section: '', type: 'text' }
    setPlaceholders(prev => [...prev, newPh])
    setEditIdx(placeholders.length)
    setEditField('label')
  }

  // Show the full editor when: manual mode (always), or after placeholders are loaded
  const showPanel = placeholders.length > 0 || mode === 'manual'

  return (
    <div className="project-template-panel" style={{ marginTop: 16, padding: '0 4px' }}>
      {/* Mode tabs */}
      <div className="pp-actions-row" style={{ marginBottom: 12 }}>
        {[
          { id: 'upload', label: 'Upload file' },
          { id: 'manual', label: 'Manual input' },
          { id: 'preset', label: 'Saved presets' },
        ].map(m => (
          <button
            key={m.id}
            className={`btn${mode === m.id ? ' btn-primary' : ' btn-secondary'}`}
            onClick={() => setMode(m.id)}
            style={{ fontSize: 12 }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {error && <div className="message error" style={{ marginBottom: 10 }}>{error}</div>}

      {/* Upload mode — show file picker only when no placeholders loaded yet */}
      {mode === 'upload' && !showPanel && (
        <div>
          <label
            htmlFor="tpl-file-input"
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
              padding: '20px 16px', border: '2px dashed var(--border)', borderRadius: 'var(--radius)',
              cursor: 'pointer', background: 'var(--bg-surface)', marginBottom: 10,
            }}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) setFile(f) }}
          >
            <UploadCloud size={24} style={{ color: 'var(--text-tertiary)' }} />
            {file
              ? <span style={{ fontSize: 13, fontWeight: 600 }}>{file.name}</span>
              : <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>Click to browse or drag & drop (.md, .txt, .docx, .pdf)</span>
            }
            <input id="tpl-file-input" ref={fileRef} type="file" accept=".md,.txt,.docx,.pdf"
              style={{ display: 'none' }} onChange={e => setFile(e.target.files[0] || null)} />
          </label>
          {file && (
            <button className="btn btn-primary" onClick={handleUpload} disabled={loading} style={{ fontSize: 12 }}>
              {loading ? <><Loader2 size={12} className="spinner" /> Parsing…</> : 'Parse Template'}
            </button>
          )}
        </div>
      )}

      {loading && (
        <div className="loading">
          <div className="spinner" />
          <span>Parsing template and detecting placeholders…</span>
        </div>
      )}

      {/* Preset mode */}
      {mode === 'preset' && (
        <div>
          {presets.length === 0
            ? <p style={{ fontSize: 13, color: 'var(--text-tertiary)', padding: '12px 0' }}>No saved presets yet.</p>
            : (
              <div className="preset-list">
                {presets.map(p => (
                  <div key={p.id} className="preset-item" onClick={() => handleLoadPreset(p)}>
                    <div className="preset-item-info">
                      <span className="preset-item-name">{p.name}</span>
                      <span className="preset-item-count">{p.placeholders?.length || 0} placeholders</span>
                    </div>
                    <button className="btn-text" style={{ color: 'var(--danger)', fontSize: 11 }}
                      onClick={e => handleDeletePreset(e, p.id)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )
          }
        </div>
      )}

      {/* Full placeholder editor — shown for upload result, manual entry, and preset load */}
      {showPanel && !loading && (
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
                          {!confirmed && <Pencil size={11} className="pp-edit-icon" />}
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
                          {!confirmed && <Pencil size={11} className="pp-edit-icon" />}
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
          <div className="pp-actions-row">
            {!confirmed && (
              <button className="btn btn-secondary pp-add" onClick={addPlaceholder}>
                <Plus size={14} /> Add Placeholder
              </button>
            )}
            <button className="btn btn-secondary" onClick={() => { setPresetName(''); setPresetError(null); setShowSaveModal(true) }}>
              <Save size={14} /> Save as Preset
            </button>
          </div>
        </div>
      )}

      {/* Confirm / re-upload buttons */}
      {placeholders.length > 0 && !loading && (
        <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
          {!confirmed && (
            <button className="btn btn-primary" onClick={handleConfirm} style={{ fontSize: 13 }}>
              <Check size={14} /> Use this template
            </button>
          )}
          {!confirmed && mode === 'upload' && (
            <button className="btn btn-secondary" style={{ fontSize: 12 }}
              onClick={() => { setPlaceholders([]); setFile(null); setTemplateTitle('') }}>
              ← Re-upload
            </button>
          )}
        </div>
      )}

      {/* Save preset modal */}
      {showSaveModal && (
        <div className="preset-modal-overlay" onClick={() => setShowSaveModal(false)}>
          <div className="preset-modal" onClick={e => e.stopPropagation()}>
            <div className="preset-modal-header">
              <span>Save as Preset</span>
              <button className="btn-text" onClick={() => setShowSaveModal(false)}><X size={14} /></button>
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
              <button className="btn btn-primary" disabled={!presetName.trim() || presetSaving} onClick={handleSavePreset}>
                {presetSaving ? <Loader2 size={12} className="spinner" /> : <Save size={12} />} Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ============================================================
   PROJECT DETAIL PAGE
============================================================ */
function ProjectWorkspace({ project, onBack, onRefresh, onStartPipeline, onLoadFromCatalog }) {
  const { state, dispatch } = useProject()
  const { templateReady, templateTitle, placeholders } = state
  const [removing, setRemoving] = useState(null)
  const [showAddSource, setShowAddSource] = useState(false)
  const [message, setMessage] = useState(null)
  const [approvedSpecs, setApprovedSpecs] = useState([])
  const [specsLoading, setSpecsLoading] = useState(true)
  const [viewingSpec, setViewingSpec] = useState(null)
  const [copied, setCopied] = useState(false)
  const [catalogSnapshots, setCatalogSnapshots] = useState([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogSearch, setCatalogSearch] = useState('')
  const [expandedSnapshot, setExpandedSnapshot] = useState(null)
  const [mergeSelections, setMergeSelections] = useState({})
  const [visible, setVisible] = useState(false)
  // Template panel state
  const [showTemplatePanel, setShowTemplatePanel] = useState(false)

  useEffect(() => { requestAnimationFrame(() => setVisible(true)) }, [])

  const toggleMerge = (snapshotId, pipelineId) => {
    setMergeSelections(prev => {
      const cur = new Set(prev[snapshotId] || [])
      cur.has(pipelineId) ? cur.delete(pipelineId) : cur.add(pipelineId)
      return { ...prev, [snapshotId]: cur }
    })
  }

  const mergePipelinesFromCatalog = (selected) => {
    if (selected.length === 1) return selected[0]
    return {
      id: `catalog_merged_${Date.now()}`,
      name: selected.map(p => p.name).join(' + '),
      description: selected.map(p => p.description).filter(Boolean).join(' | '),
      type: selected[0].type,
      execution_mode: selected[0].execution_mode,
      confidence: Math.max(...selected.map(p => p.confidence || 0)),
      origin: 'catalog_merge',
      source_files: [...new Set(selected.flatMap(p => p.source_files || []))],
      source_tables: [...new Set(selected.flatMap(p => p.source_tables || []))],
      technologies: [...new Set(selected.flatMap(p => p.technologies || []))],
      jobs: selected.flatMap(p => p.jobs || []),
      triggers: selected.flatMap(p => p.triggers || []),
      listen_mode: selected.flatMap(p => p.listen_mode || []),
      queues: selected.flatMap(p => p.queues || []),
      sub_pipelines: [...new Set(selected.flatMap(p => p.sub_pipelines || []))],
      explainability: {
        keywords: [...new Set(selected.flatMap(p => p.explainability?.keywords || []))],
        orchestration_clues: [...new Set(selected.flatMap(p => p.explainability?.orchestration_clues || []))],
        evidence_files: [...new Set(selected.flatMap(p => p.explainability?.evidence_files || []))],
        evidence_tables: [...new Set(selected.flatMap(p => p.explainability?.evidence_tables || []))],
      },
    }
  }

  useEffect(() => {
    getProjectApprovedSpecs(project.id)
      .then(res => setApprovedSpecs(res.data.approved_specs || []))
      .catch(() => setApprovedSpecs([]))
      .finally(() => setSpecsLoading(false))
  }, [project.id])

  useEffect(() => {
    pipelineGetCatalog(project.id)
      .then(res => setCatalogSnapshots(res.data.catalog || []))
      .catch(() => setCatalogSnapshots([]))
      .finally(() => setCatalogLoading(false))
  }, [project.id])

  const handleDownloadSpec = (entry) => {
    const blob = new Blob([entry.spec], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url
    a.download = `${project.name.replace(/\s+/g, '_')}_v${entry.version_number}_approved.md`
    a.click(); URL.revokeObjectURL(url)
  }

  const handleCopySpec = (spec) => {
    navigator.clipboard.writeText(spec).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 2000)
    })
  }

  const sources = project.sources || []
  const connectedCount = sources.filter(s => s.status === 'connected').length

  const handleRemove = async (srcId) => {
    setRemoving(srcId)
    try {
      await removeProjectSource(project.id, srcId)
      onRefresh()
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to remove source' })
    }
    setRemoving(null)
  }

  const totalPipelines = catalogSnapshots.reduce((s, sn) => s + sn.count, 0)
  const hasSpecs = !specsLoading && approvedSpecs.length > 0
  const needsPulse = !specsLoading && approvedSpecs.length === 0 && sources.length > 0

  return (
    <div className={`pd-page${visible ? ' pd-page--visible' : ''}`}>
      {/* ── Back button ── */}
      <button className="pd-back" onClick={onBack}>
        <ArrowLeft size={14} />
        Back to Projects
      </button>

      {/* ── Hero header ── */}
      <div className="pd-hero pd-anim" style={{ '--delay': '0ms' }}>
        <div className="pd-hero-text">
          <h1 className="pd-title">{project.name}</h1>
          <div className="pd-title-bar" />
          {project.description && <p className="pd-desc">{project.description}</p>}
        </div>
      </div>

      {/* ── Stat cards ── */}
      <div className="pd-stats pd-anim" style={{ '--delay': '60ms' }}>
        <div className="pd-stat-card">
          <div className="pd-stat-label">Total Sources</div>
          <div className="pd-stat-value">{sources.length}</div>
        </div>
        <div className="pd-stat-card">
          <div className="pd-stat-label">Connected</div>
          <div className="pd-stat-value pd-stat-value--green">{connectedCount}</div>
        </div>
        <div className="pd-stat-card">
          <div className="pd-stat-label">Created</div>
          <div className="pd-stat-value pd-stat-value--date">
            {new Date(project.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
          </div>
        </div>
      </div>

      {message && <div className={`message ${message.type}`}>{message.text}</div>}

      {/* ── Sources section ── */}
      <div className="pd-section pd-anim" style={{ '--delay': '120ms' }}>
        <div className="pd-section-header">
          <div className="pd-section-left">
            <Link2 size={16} className="pd-section-icon" />
            <span className="pd-section-title">Sources</span>
            <span className="pd-count-badge">{sources.length}</span>
          </div>
          <button className="pd-btn-primary" onClick={() => setShowAddSource(true)}>
            <Plus size={14} />
            Add Source
          </button>
        </div>

        {sources.length === 0 ? (
          <div className="pd-empty">
            <div className="pd-empty-icon"><FileText size={22} /></div>
            <div className="pd-empty-title">No sources yet</div>
            <p className="pd-empty-sub">
              Connect your first source to start building a specification.
            </p>
            <button className="pd-btn-primary" onClick={() => setShowAddSource(true)}>
              <Plus size={14} /> Connect your first source
            </button>
          </div>
        ) : (
          <div className="pd-sources-grid">
            {sources.map((s, i) => {
              const t = getTypeInfo(s.type)
              const Icon = t.icon
              return (
                <div key={s.id} className="pd-source-card" style={{ '--i': i }}>
                  <div className="pd-source-top">
                    <div className="pd-source-icon" style={{ background: t.bg }}>
                      <Icon size={18} />
                    </div>
                    <div className="pd-source-info">
                      <div className="pd-source-name">{s.label}</div>
                      <div className="pd-source-type">{s.type_name}</div>
                    </div>
                  </div>
                  <div className="pd-source-foot">
                    <span className={`pd-status-badge pd-status-badge--${s.status === 'connected' ? 'green' : s.status === 'error' ? 'pink' : 'muted'}`}>
                      <span className="pd-status-dot" />
                      {s.status === 'connected' ? 'Connected' : s.status === 'error' ? 'Error' : 'Pending'}
                    </span>
                    <button
                      className="pd-delete-icon"
                      onClick={() => handleRemove(s.id)}
                      disabled={removing === s.id}
                      title="Remove source"
                    >
                      {removing === s.id ? <Loader2 size={14} className="spinner" /> : <Trash2 size={14} />}
                    </button>
                  </div>
                </div>
              )
            })}
            <div className="pd-source-add" onClick={() => setShowAddSource(true)}>
              <div className="pd-source-add-icon"><Plus size={14} /></div>
              <span>Add Another Source</span>
            </div>
          </div>
        )}
      </div>

      {/* ── Template Section ── */}
      <div className="pd-section pd-anim" style={{ '--delay': '150ms' }}>
        <div className="pd-section-header">
          <div className="pd-section-left">
            <FileText size={16} className="pd-section-icon" />
            <span className="pd-section-title">Template</span>
            {templateReady && <span className="pd-count-badge">✓</span>}
          </div>
          <button className="pd-btn-primary" onClick={() => setShowTemplatePanel(v => !v)}>
            {templateReady ? <><Pencil size={14} /> Change</> : <><Plus size={14} /> Configure</>}
          </button>
        </div>

        {!templateReady && !showTemplatePanel && (
          <div className="pd-empty" style={{ padding: '20px 0' }}>
            <div className="pd-empty-icon"><FileText size={22} /></div>
            <div className="pd-empty-title">No template configured</div>
            <p className="pd-empty-sub">Choose your spec template before launching the pipeline.</p>
          </div>
        )}

        {templateReady && !showTemplatePanel && (
          <div className="pd-template-summary">
            <div className="pd-template-name">{templateTitle || 'Custom template'}</div>
            <div className="pd-template-meta">{placeholders.length} placeholder{placeholders.length !== 1 ? 's' : ''}</div>
          </div>
        )}

        {showTemplatePanel && (
          <ProjectTemplatePanel
            project={project}
            onConfigured={() => setShowTemplatePanel(false)}
          />
        )}
      </div>

      {/* ── Generate Spec CTA ── */}
      {sources.length > 0 && (
        <div className="pd-cta-row pd-anim" style={{ '--delay': '160ms' }}>
          {!templateReady && (
            <p style={{ fontSize: 12.5, color: 'var(--text-tertiary)', textAlign: 'center', marginBottom: 8 }}>
              Configure a template above to enable pipeline launch.
            </p>
          )}
          <button
            className={`pd-cta-btn${needsPulse && templateReady ? ' pd-cta-btn--pulse' : ''}`}
            onClick={() => onStartPipeline(project)}
            disabled={!templateReady}
            style={!templateReady ? { opacity: 0.45, cursor: 'not-allowed' } : {}}
          >
            <Zap size={16} />
            Generate Spec from {sources.length} source{sources.length !== 1 ? 's' : ''} →
          </button>
        </div>
      )}

      {/* ── Generated Specs ── */}
      <div className="pd-section pd-anim" style={{ '--delay': '200ms' }}>
        <div className="pd-section-header">
          <div className="pd-section-left">
            <ScrollText size={16} className="pd-section-icon" />
            <span className="pd-section-title">Generated Specs</span>
            {hasSpecs && <span className="pd-count-badge">{approvedSpecs.length}</span>}
          </div>
        </div>

        {specsLoading && (
          <div className="loading"><div className="spinner" /><span>Loading specs…</span></div>
        )}

        {!specsLoading && approvedSpecs.length === 0 && (
          <div className="pd-empty">
            <div className="pd-empty-icon"><ScrollText size={22} /></div>
            <div className="pd-empty-title">No approved specs yet</div>
            <p className="pd-empty-sub">
              Run the pipeline wizard and promote a spec version to Approved — it will appear here.
            </p>
          </div>
        )}

        {!specsLoading && approvedSpecs.length > 0 && (
          <div className="pd-specs-list">
            {[...approvedSpecs].reverse().map(entry => (
              <div key={entry.version_id} className="pd-spec-row">
                <span className="pd-badge pd-badge--green">v{entry.version_number} approved</span>
                <div className="pd-spec-meta">
                  <span className="pd-spec-name">{entry.pipeline_name}</span>
                  <span className="pd-spec-date">
                    {new Date(entry.approved_at).toLocaleString('en-US', {
                      month: 'short', day: 'numeric', year: 'numeric',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </span>
                </div>
                <div className="pd-spec-actions">
                  <button className="pd-btn-ghost" onClick={() => setViewingSpec(entry)}>
                    <FileText size={13} /> View
                  </button>
                  <button className="pd-btn-ghost" onClick={() => handleDownloadSpec(entry)}>
                    <Download size={13} /> Download
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Detected Pipelines Catalog ── */}
      <div className="pd-section pd-anim" style={{ '--delay': '240ms' }}>
        <div className="pd-section-header">
          <div className="pd-section-left">
            <BookMarked size={16} className="pd-section-icon" />
            <span className="pd-section-title">Detected Pipelines Catalog</span>
            {catalogSnapshots.length > 0 && (
              <>
                <span className="pd-badge pd-badge--pink">{totalPipelines} pipeline{totalPipelines !== 1 ? 's' : ''}</span>
                <span className="pd-badge pd-badge--orange">{catalogSnapshots.length} snapshot{catalogSnapshots.length !== 1 ? 's' : ''}</span>
              </>
            )}
          </div>
        </div>

        {catalogLoading && <div className="loading"><div className="spinner" /><span>Loading catalog…</span></div>}

        {!catalogLoading && catalogSnapshots.length === 0 && (
          <div className="pd-empty">
            <div className="pd-empty-icon"><BookMarked size={22} /></div>
            <div className="pd-empty-title">No pipeline snapshots saved</div>
            <p className="pd-empty-sub">
              Run pipeline detection and click <strong>Save to Catalog</strong> to preserve a snapshot here.
            </p>
          </div>
        )}

        {!catalogLoading && catalogSnapshots.length > 0 && (
          <>
            <div className="pd-catalog-search-wrap">
              <Search size={14} className="pd-catalog-search-icon" />
              <input
                className="pd-catalog-search"
                type="text"
                placeholder="Search catalog pipelines…"
                value={catalogSearch}
                onChange={e => setCatalogSearch(e.target.value)}
              />
            </div>

            <div className="pd-catalog-list">
              {[...catalogSnapshots].reverse().map(snapshot => {
                const isExpanded = expandedSnapshot === snapshot.id
                const q = catalogSearch.toLowerCase()
                const matchedPipelines = q
                  ? snapshot.pipelines.filter(p =>
                      p.name?.toLowerCase().includes(q) ||
                      p.category?.toLowerCase().includes(q) ||
                      p.description?.toLowerCase().includes(q))
                  : snapshot.pipelines
                if (q && matchedPipelines.length === 0) return null

                const sel = mergeSelections[snapshot.id]
                const selCount = sel ? sel.size : 0
                const allIds = matchedPipelines.map(p => p.id)
                const allSelected = allIds.length > 0 && allIds.every(id => sel?.has(id))

                return (
                  <div key={snapshot.id} className="pd-snapshot">
                    <div className="pd-snapshot-header" onClick={() => setExpandedSnapshot(isExpanded ? null : snapshot.id)}>
                      <BookMarked size={14} className="pd-section-icon" />
                      <div className="pd-snapshot-meta">
                        <span className="pd-snapshot-count">{snapshot.count} pipeline{snapshot.count !== 1 ? 's' : ''}</span>
                        <span className="pd-snapshot-time">
                          <Clock size={11} />
                          {new Date(snapshot.saved_at).toLocaleString('en-US', {
                            month: 'short', day: 'numeric', year: 'numeric',
                            hour: '2-digit', minute: '2-digit',
                          })}
                        </span>
                        {q && <span className="pd-badge pd-badge--pink">{matchedPipelines.length} match{matchedPipelines.length !== 1 ? 'es' : ''}</span>}
                      </div>
                      {isExpanded ? <ChevronDown size={14} className="pd-snapshot-chevron" /> : <ChevronRight size={14} className="pd-snapshot-chevron" />}
                    </div>

                    {isExpanded && (
                      <div className="pd-snapshot-body">
                        <div className="pd-merge-bar">
                          <label className="pd-merge-all">
                            <input type="checkbox" checked={allSelected}
                              onChange={() => setMergeSelections(prev => ({
                                ...prev, [snapshot.id]: allSelected ? new Set() : new Set(allIds)
                              }))}
                              style={{ accentColor: '#FF2D78' }}
                            />
                            Select all
                          </label>
                          {selCount >= 2 && (
                            <button className="pd-btn-primary pd-btn-primary--sm"
                              onClick={() => {
                                const s = matchedPipelines.filter(p => sel.has(p.id))
                                onLoadFromCatalog?.(project, [mergePipelinesFromCatalog(s)], mergePipelinesFromCatalog(s))
                              }}>
                              Merge {selCount} & Use for Spec →
                            </button>
                          )}
                          {selCount === 1 && (
                            <button className="pd-btn-primary pd-btn-primary--sm"
                              onClick={() => {
                                const s = matchedPipelines.find(p => sel.has(p.id))
                                onLoadFromCatalog?.(project, [s], s)
                              }}>
                              Use selected for Spec →
                            </button>
                          )}
                          {selCount > 0 && <span className="pd-merge-count">{selCount} selected</span>}
                        </div>

                        {matchedPipelines.map(p => {
                          const isChecked = mergeSelections[snapshot.id]?.has(p.id) || false
                          return (
                            <div key={p.id} className={`pd-pipeline-row${isChecked ? ' pd-pipeline-row--checked' : ''}`}>
                              <input type="checkbox" checked={isChecked}
                                onChange={() => toggleMerge(snapshot.id, p.id)}
                                style={{ accentColor: '#FF2D78', width: 14, height: 14, cursor: 'pointer', flexShrink: 0, marginTop: 2 }}
                              />
                              <div className="pd-pipeline-info">
                                <div className="pd-pipeline-badges">
                                  <span className="pd-pipeline-name">{p.name}</span>
                                  {p.category && <span className="pd-badge pd-badge--pink">{p.category}</span>}
                                  {p.execution_mode && <span className="pd-badge pd-badge--purple">{p.execution_mode}</span>}
                                  {p.confidence != null && (
                                    <span className="pd-pipeline-conf">{Math.round(p.confidence * 100)}% confidence</span>
                                  )}
                                </div>
                                {p.description && <div className="pd-pipeline-desc">{p.description}</div>}
                                {p.source_files?.length > 0 && (
                                  <div className="pd-pipeline-files">
                                    {p.source_files.slice(0, 3).join(', ')}{p.source_files.length > 3 ? ` +${p.source_files.length - 3} more` : ''}
                                  </div>
                                )}
                              </div>
                              <button className="pd-btn-ghost pd-btn-ghost--sm"
                                onClick={() => onLoadFromCatalog?.(project, [p], p)}>
                                Use for Spec →
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* Spec viewer modal */}
      {viewingSpec && (
        <div className="modal-overlay" onClick={() => setViewingSpec(null)}>
          <div className="modal" style={{ maxWidth: 820, width: '95vw', maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexShrink: 0 }}>
              <div>
                <span style={{ fontWeight: 700, fontSize: 15 }}>
                  {viewingSpec.pipeline_name} — v{viewingSpec.version_number}
                </span>
                <span className="pd-badge pd-badge--green" style={{ marginLeft: 10 }}>Approved</span>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-secondary" style={{ padding: '5px 12px', fontSize: 12 }}
                  onClick={() => handleCopySpec(viewingSpec.spec)}>
                  {copied ? <Check size={13} /> : <Copy size={13} />}{copied ? 'Copied' : 'Copy'}
                </button>
                <button className="btn btn-secondary" style={{ padding: '5px 12px', fontSize: 12 }}
                  onClick={() => handleDownloadSpec(viewingSpec)}>
                  <Download size={13} /> Download
                </button>
                <button className="btn-icon" onClick={() => setViewingSpec(null)}><X size={16} /></button>
              </div>
            </div>
            <pre style={{
              flex: 1, overflow: 'auto', background: 'var(--bg-deep)',
              border: '1px solid var(--border)', borderRadius: 8,
              padding: 16, fontSize: 12.5, lineHeight: 1.6,
              color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>{viewingSpec.spec}</pre>
          </div>
        </div>
      )}

      {showAddSource && (
        <AddSourceModal
          project={project}
          onClose={() => setShowAddSource(false)}
          onAdded={() => { setShowAddSource(false); onRefresh() }}
        />
      )}
    </div>
  )
}

/* ============================================================
   MAIN PAGE — PROJECTS LIST
============================================================ */
function ProjectsPage() {
  const { dispatch } = useProject()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [openProjectId, setOpenProjectId] = useState(null)
  const [openProject, setOpenProject] = useState(null)
  const [message, setMessage] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [listVisible, setListVisible] = useState(false)

  const fetchProjects = async () => {
    try {
      const res = await getProjects()
      setProjects(res.data.projects || [])
    } catch {
      setProjects([])
    }
    setLoading(false)
  }

  const fetchOpenProject = async (id) => {
    try {
      const res = await getProject(id)
      setOpenProject(res.data)
    } catch {
      setOpenProjectId(null); setOpenProject(null)
    }
  }

  useEffect(() => { fetchProjects() }, [])
  useEffect(() => {
    if (!loading) requestAnimationFrame(() => setListVisible(true))
  }, [loading])
  useEffect(() => {
    if (openProjectId) fetchOpenProject(openProjectId)
    else setOpenProject(null)
  }, [openProjectId])

  const handleDelete = async (e, pid) => {
    e.stopPropagation()
    setDeleting(pid)
    try {
      await deleteProject(pid)
      setMessage({ type: 'success', text: 'Project deleted' })
      fetchProjects()
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to delete' })
    }
    setDeleting(null)
    setTimeout(() => setMessage(null), 3000)
  }

  /* ── Project Detail view ── */
  if (openProject) {
    return (
      <ProjectWorkspace
        project={openProject}
        onBack={() => { setOpenProjectId(null); fetchProjects() }}
        onRefresh={() => fetchOpenProject(openProject.id)}
        onStartPipeline={proj => dispatch({ type: 'OPEN_PROJECT', payload: proj })}
        onLoadFromCatalog={(proj, pipelines, selected) =>
          dispatch({ type: 'LOAD_FROM_CATALOG', payload: { project: proj, pipelines, selectedPipeline: selected } })
        }
      />
    )
  }

  /* ── Projects List view ── */
  return (
    <div className={`pl-page${listVisible ? ' pl-page--visible' : ''}`}>
      {/* Page header */}
      <div className="pl-header pl-anim" style={{ '--delay': '0ms' }}>
        <div className="pl-header-text">
          <h1 className="pl-title">Projects</h1>
          <p className="pl-subtitle">
            Each project aggregates multiple sources and generates a unified specification using AI.
          </p>
        </div>
        <button className="pd-btn-primary" onClick={() => setShowModal(true)}>
          <Plus size={14} />
          New Project
        </button>
      </div>

      {message && <div className={`message ${message.type}`}>{message.text}</div>}

      {loading && (
        <div className="loading"><div className="spinner" /><span>Loading projects…</span></div>
      )}

      {!loading && projects.length === 0 && (
        <div className="pd-empty pl-anim" style={{ '--delay': '60ms' }}>
          <div className="pd-empty-icon"><FolderOpen size={22} /></div>
          <div className="pd-empty-title">No projects yet</div>
          <p className="pd-empty-sub">
            Create your first project to start connecting sources and generating specifications.
          </p>
          <button className="pd-btn-primary" onClick={() => setShowModal(true)}>
            <Plus size={14} /> Create your first project
          </button>
        </div>
      )}

      {!loading && projects.length > 0 && (
        <div className="pl-grid">
          {/* "New Project" card — always first */}
          <div className="pl-add-card pl-anim" style={{ '--delay': '40ms' }} onClick={() => setShowModal(true)}>
            <div className="pl-add-icon">
              <Plus size={18} />
            </div>
            <span className="pl-add-label">New Project</span>
          </div>

          {projects.map((p, i) => {
            const initials = p.name.trim().split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()
            const total = (p.sources || []).length
            const conn = (p.sources || []).filter(s => s.status === 'connected').length
            const badge = total === 0
              ? 'No sources yet'
              : `${total} source${total !== 1 ? 's' : ''}${conn > 0 ? ` · ${conn} connected` : ''}`
            return (
              <div
                key={p.id}
                className="pl-card pl-anim"
                style={{ '--delay': `${(i + 1) * 60}ms` }}
                onClick={() => { dispatch({ type: 'CLEAR_PROJECT_TEMPLATE' }); setOpenProjectId(p.id) }}
              >
                {/* Gradient left accent */}
                <div className="pl-card-accent" />

                {/* Header */}
                <div className="pl-card-head">
                  <div className="pl-avatar">{initials}</div>
                  <div className="pl-card-meta">
                    <div className="pl-card-name">{p.name}</div>
                    <div className={`pl-card-desc${!p.description ? ' pl-card-desc--empty' : ''}`}>
                      {p.description || 'No description'}
                    </div>
                  </div>
                </div>

                {/* Footer */}
                <div className="pl-card-foot">
                  <span className="pl-status">
                    <span className="pl-status-dot" />
                    {badge}
                  </span>
                  <div className="pl-card-actions">
                    <button
                      className="pd-btn-ghost pd-btn-ghost--sm"
                      onClick={e => { e.stopPropagation(); setOpenProjectId(p.id) }}
                    >
                      Open →
                    </button>
                    <button
                      className="pl-delete-btn"
                      onClick={e => handleDelete(e, p.id)}
                      disabled={deleting === p.id}
                      title="Delete project"
                    >
                      {deleting === p.id ? <Loader2 size={14} className="spinner" /> : <Trash2 size={14} />}
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {showModal && (
        <NewProjectModal
          onClose={() => setShowModal(false)}
          onCreated={proj => { setShowModal(false); setOpenProjectId(proj.id); fetchProjects() }}
        />
      )}
    </div>
  )
}

export default ProjectsPage
