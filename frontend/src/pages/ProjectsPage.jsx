import { useState, useEffect, useRef } from 'react'
import {
  Plus, FolderOpen, Trash2, ArrowLeft, Zap, Loader2, X,
  CheckCircle, AlertCircle, Link2, FileText, Globe, AlignLeft,
  Github, Database, Cloud, BarChart3, HardDrive, BookOpen, FileSpreadsheet,
  Search, Unplug, ScrollText, Download, Copy, Check,
} from 'lucide-react'
import {
  getProjects, createProject, deleteProject,
  getProject, addProjectSource, removeProjectSource,
  getProjectApprovedSpecs,
  getConnections,
  getGitHubRepos, getBigQueryDatasets, getPostgreSQLSchemas,
  getPowerBIWorkspaces, getGCSBuckets,
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
  { id: 'pdf',        name: 'PDF File',      icon: FileText,     bg: 'rgba(220,38,38,.14)',
    fields: [{ id:'name', label:'File name or path', ph:'template.pdf' }] },
  { id: 'notion',     name: 'Notion Page',   icon: BookOpen,     bg: 'rgba(55,65,81,.45)',
    fields: [{ id:'url', label:'Notion page URL', ph:'https://notion.so/…' }] },
  { id: 'googledoc',  name: 'Google Doc',    icon: FileSpreadsheet, bg: 'rgba(29,78,216,.14)',
    fields: [{ id:'url', label:'Google Doc URL', ph:'https://docs.google.com/…' }] },
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
              background:'rgba(255,255,255,0.03)', border:'1px solid var(--border)',
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

  const canSubmit = isMcp ? !!selectedResource : selected && t?.fields

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
                      background:'rgba(255,255,255,0.03)', border:'1px solid var(--border)',
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
   PROJECT WORKSPACE (inside a project — source manager)
============================================================ */
function ProjectWorkspace({ project, onBack, onRefresh, onStartPipeline }) {
  const [removing, setRemoving] = useState(null)
  const [showAddSource, setShowAddSource] = useState(false)
  const [message, setMessage] = useState(null)
  const [approvedSpecs, setApprovedSpecs] = useState([])
  const [specsLoading, setSpecsLoading] = useState(true)
  const [viewingSpec, setViewingSpec] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await getProjectApprovedSpecs(project.id)
        setApprovedSpecs(res.data.approved_specs || [])
      } catch {
        setApprovedSpecs([])
      }
      setSpecsLoading(false)
    }
    load()
  }, [project.id])

  const handleDownloadSpec = (entry) => {
    const blob = new Blob([entry.spec], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${project.name.replace(/\s+/g, '_')}_v${entry.version_number}_approved.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleCopySpec = (spec) => {
    navigator.clipboard.writeText(spec).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
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

  return (
    <div>
      {/* Back + header */}
      <button className="btn btn-secondary" onClick={onBack} style={{ marginBottom: 20, gap: 6 }}>
        <ArrowLeft size={14} /> Back to Projects
      </button>

      <div className="page-header" style={{ marginBottom: 24 }}>
        <h2>{project.name}</h2>
        {project.description && <p>{project.description}</p>}
      </div>

      {/* Stats */}
      <div className="stats-bar" style={{ marginBottom: 24 }}>
        <div className="stat-card">
          <div className="stat-label">Total Sources</div>
          <div className="stat-value">{sources.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Connected</div>
          <div className="stat-value" style={{ color: 'var(--success)' }}>{connectedCount}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Created</div>
          <div className="stat-value" style={{ fontSize: 14 }}>
            {new Date(project.created_at).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })}
          </div>
        </div>
      </div>

      {message && <div className={`message ${message.type}`}>{message.text}</div>}

      {/* Sources header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom: 18 }}>
        <div style={{ display:'flex', alignItems:'center', gap: 10 }}>
          <h3 className="section-title" style={{ margin: 0 }}>
            <Link2 size={16} /> Sources
          </h3>
          <span className="source-count-badge">{sources.length}</span>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAddSource(true)}>
          <Plus size={14} /> Add Source
        </button>
      </div>

      {/* Sources grid or empty state */}
      {sources.length === 0 ? (
        <div className="sources-empty-state">
          <div className="se-icon-wrap">
            <FileText size={22} />
          </div>
          <div className="se-title">No sources yet</div>
          <p className="se-desc">
            Connect your first source to start building a specification.
            You can combine as many sources as you need.
          </p>
          <button className="btn btn-primary" onClick={() => setShowAddSource(true)}>
            <Plus size={14} /> Connect your first source
          </button>
        </div>
      ) : (
        <div className="project-sources-grid">
          {sources.map(s => {
            const t = getTypeInfo(s.type)
            const Icon = t.icon
            return (
              <div key={s.id} className="psource-card">
                <div className="psource-top">
                  <div className="psource-icon" style={{ background: t.bg }}>
                    <Icon size={18} />
                  </div>
                  <div className="psource-info">
                    <div className="psource-label">{s.label}</div>
                    <div className="psource-type">{s.type_name}</div>
                  </div>
                </div>
                <div className="psource-foot">
                  <div className={`card-status ${s.status === 'connected' ? 'connected' : s.status === 'error' ? 'error' : 'disconnected'}`}>
                    <span className="dot" />
                    {s.status.charAt(0).toUpperCase() + s.status.slice(1)}
                  </div>
                  <button
                    className="btn btn-danger-outline"
                    style={{ padding:'5px 10px', fontSize:12 }}
                    onClick={() => handleRemove(s.id)}
                    disabled={removing === s.id}
                  >
                    {removing === s.id ? <Loader2 size={12} className="spinner" /> : <Trash2 size={12} />}
                  </button>
                </div>
              </div>
            )
          })}

          {/* "Add another" card */}
          <div className="psource-add-card" onClick={() => setShowAddSource(true)}>
            <div className="psa-icon"><Plus size={18} /></div>
            <span className="psa-label">Add Another Source</span>
          </div>
        </div>
      )}

      {/* Generate button (below sources) */}
      {sources.length > 0 && (
        <div style={{ marginTop: 28, display:'flex', alignItems:'center', gap:14 }}>
          <button className="btn btn-primary" style={{ padding:'11px 24px', fontWeight:600 }}
            onClick={() => onStartPipeline(project)}>
            <Zap size={14} /> Generate Spec from {sources.length} source{sources.length !== 1 ? 's' : ''} →
          </button>
        </div>
      )}

      {/* ── Generated Specs ───────────────────────────────────── */}
      <div style={{ marginTop: 36 }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:18 }}>
          <h3 className="section-title" style={{ margin:0 }}>
            <ScrollText size={16} /> Generated Specs
          </h3>
          {approvedSpecs.length > 0 && (
            <span className="source-count-badge">{approvedSpecs.length}</span>
          )}
        </div>

        {specsLoading && (
          <div className="loading"><div className="spinner" /><span>Loading specs…</span></div>
        )}

        {!specsLoading && approvedSpecs.length === 0 && (
          <div className="sources-empty-state">
            <div className="se-icon-wrap"><ScrollText size={22} /></div>
            <div className="se-title">No approved specs yet</div>
            <p className="se-desc">
              Run the pipeline wizard and promote a spec version to Approved — it will appear here.
            </p>
          </div>
        )}

        {!specsLoading && approvedSpecs.length > 0 && (
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {[...approvedSpecs].reverse().map((entry) => (
              <div key={entry.version_id} style={{
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 10,
                padding: '14px 18px',
                display: 'flex',
                alignItems: 'center',
                gap: 16,
                flexWrap: 'wrap',
              }}>
                <div style={{ display:'flex', alignItems:'center', gap:10, flex:1, minWidth:200 }}>
                  <div style={{
                    background: 'rgba(52,211,153,.12)',
                    color: 'var(--success)',
                    borderRadius: 999,
                    padding: '3px 10px',
                    fontSize: 11,
                    fontWeight: 700,
                    border: '1px solid rgba(52,211,153,.22)',
                    whiteSpace: 'nowrap',
                  }}>v{entry.version_number} approved</div>
                  <div>
                    <div style={{ fontWeight:600, fontSize:14, color:'var(--text-primary)' }}>
                      {entry.pipeline_name}
                    </div>
                    <div style={{ fontSize:12, color:'var(--text-secondary)', marginTop:2 }}>
                      {new Date(entry.approved_at).toLocaleString('en-US', {
                        month:'short', day:'numeric', year:'numeric',
                        hour:'2-digit', minute:'2-digit',
                      })}
                    </div>
                  </div>
                </div>
                <div style={{ display:'flex', gap:8 }}>
                  <button className="btn btn-secondary" style={{ padding:'6px 14px', fontSize:12 }}
                    onClick={() => setViewingSpec(entry)}>
                    <FileText size={13} /> View
                  </button>
                  <button className="btn btn-secondary" style={{ padding:'6px 14px', fontSize:12 }}
                    onClick={() => handleDownloadSpec(entry)}>
                    <Download size={13} /> Download
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Spec viewer modal */}
      {viewingSpec && (
        <div className="modal-overlay" onClick={() => setViewingSpec(null)}>
          <div className="modal" style={{ maxWidth:820, width:'95vw', maxHeight:'85vh', display:'flex', flexDirection:'column' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16, flexShrink:0 }}>
              <div>
                <span style={{ fontWeight:700, fontSize:15 }}>
                  {viewingSpec.pipeline_name} — v{viewingSpec.version_number}
                </span>
                <span style={{
                  marginLeft:10, fontSize:11, fontWeight:700,
                  background:'rgba(52,211,153,.12)', color:'var(--success)',
                  border:'1px solid rgba(52,211,153,.22)', borderRadius:999, padding:'2px 9px',
                }}>Approved</span>
              </div>
              <div style={{ display:'flex', gap:8 }}>
                <button className="btn btn-secondary" style={{ padding:'5px 12px', fontSize:12 }}
                  onClick={() => handleCopySpec(viewingSpec.spec)}>
                  {copied ? <Check size={13} /> : <Copy size={13} />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
                <button className="btn btn-secondary" style={{ padding:'5px 12px', fontSize:12 }}
                  onClick={() => handleDownloadSpec(viewingSpec)}>
                  <Download size={13} /> Download
                </button>
                <button className="btn-icon" onClick={() => setViewingSpec(null)}><X size={16} /></button>
              </div>
            </div>
            <pre style={{
              flex:1, overflow:'auto', background:'var(--bg-deep)',
              border:'1px solid var(--border)', borderRadius:8,
              padding:16, fontSize:12.5, lineHeight:1.6,
              color:'var(--text-primary)', whiteSpace:'pre-wrap', wordBreak:'break-word',
            }}>{viewingSpec.spec}</pre>
          </div>
        </div>
      )}

      {/* Add Source Modal */}
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
   MAIN PAGE — PROJECTS DASHBOARD
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
      setOpenProjectId(null)
      setOpenProject(null)
    }
  }

  useEffect(() => { fetchProjects() }, [])
  useEffect(() => {
    if (openProjectId) fetchOpenProject(openProjectId)
    else setOpenProject(null)
  }, [openProjectId])

  const handleDelete = async (e, pid) => {
    e.stopPropagation()
    setDeleting(pid)
    try {
      await deleteProject(pid)
      setMessage({ type:'success', text:'Project deleted' })
      fetchProjects()
    } catch (err) {
      setMessage({ type:'error', text: err.response?.data?.detail || 'Failed to delete' })
    }
    setDeleting(null)
    setTimeout(() => setMessage(null), 3000)
  }

  /* Inside a project */
  if (openProject) {
    return (
      <ProjectWorkspace
        project={openProject}
        onBack={() => { setOpenProjectId(null); fetchProjects() }}
        onRefresh={() => fetchOpenProject(openProject.id)}
        onStartPipeline={(proj) => dispatch({ type: 'OPEN_PROJECT', payload: proj })}
      />
    )
  }

  /* Dashboard */
  return (
    <div>
      <div className="page-header">
        <h2>Projects</h2>
        <p>Each project aggregates multiple sources and generates a unified specification using AI.</p>
      </div>

      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:20 }}>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          <Plus size={14} /> New Project
        </button>
      </div>

      {message && <div className={`message ${message.type}`}>{message.text}</div>}

      {loading && (
        <div className="loading"><div className="spinner" /><span>Loading projects…</span></div>
      )}

      {!loading && projects.length === 0 && (
        <div className="sources-empty-state">
          <div className="se-icon-wrap"><FolderOpen size={22} /></div>
          <div className="se-title">No projects yet</div>
          <p className="se-desc">
            Create your first project to start connecting sources and generating specifications.
          </p>
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            <Plus size={14} /> Create your first project
          </button>
        </div>
      )}

      {!loading && projects.length > 0 && (
        <div className="projects-grid">
          {/* New project placeholder */}
          <div className="project-add-card" onClick={() => setShowModal(true)}>
            <div className="psa-icon"><Plus size={20} /></div>
            <span className="psa-label">New Project</span>
          </div>

          {projects.map(p => {
            const initials = p.name.trim().split(/\s+/).map(w => w[0]).join('').slice(0,2).toUpperCase()
            const total = (p.sources || []).length
            const conn = (p.sources || []).filter(s => s.status === 'connected').length
            const badge = total === 0
              ? 'No sources yet'
              : `${total} source${total !== 1 ? 's' : ''}${conn > 0 ? ` · ${conn} connected` : ''}`
            return (
              <div key={p.id} className="project-card" onClick={() => setOpenProjectId(p.id)}>
                <div className="pc-head">
                  <div className="pc-avatar">{initials}</div>
                  <div className="pc-meta">
                    <div className="pc-name">{p.name}</div>
                    <div className="pc-desc">{p.description || 'No description'}</div>
                  </div>
                </div>
                <div className="pc-foot">
                  <span className="pc-badge"><span className="dot" />{badge}</span>
                  <div style={{ display:'flex', gap:6 }}>
                    <button className="btn btn-primary" style={{ padding:'4px 12px', fontSize:11.5 }}
                      onClick={e => { e.stopPropagation(); setOpenProjectId(p.id) }}>
                      Open →
                    </button>
                    <button className="btn btn-danger-outline" style={{ padding:'4px 8px' }}
                      onClick={e => handleDelete(e, p.id)} disabled={deleting === p.id}>
                      {deleting === p.id ? <Loader2 size={12} className="spinner" /> : <Trash2 size={12} />}
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
          onCreated={(proj) => { setShowModal(false); setOpenProjectId(proj.id); fetchProjects() }}
        />
      )}
    </div>
  )
}

export default ProjectsPage
