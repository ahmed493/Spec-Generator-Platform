import { useState, useEffect, useRef } from 'react'
import {
  FileText, Loader2, Copy, Check, Upload, AlertCircle, CheckCircle,
  Search, Layers, ChevronDown, ChevronUp, Database, GitBranch,
} from 'lucide-react'
import { generateSpec, generateSpecFromTemplate, getGitHubRepos, detectPipelines } from '../api'

const MODES = { CLASSIC: 'classic', TEMPLATE: 'template' }

/* â”€â”€ tiny helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
const TypeBadge = ({ type }) => {
  const color = {
    ETL: '#3b82f6', ELT: '#6366f1', ingestion: '#10b981',
    reporting: '#f59e0b', ml: '#ec4899', api: '#8b5cf6',
  }[type?.toLowerCase()] || '#64748b'
  return (
    <span style={{
      fontSize: '10px', fontWeight: 700, padding: '2px 8px', borderRadius: '999px',
      background: color + '22', color, border: `1px solid ${color}55`, textTransform: 'uppercase',
    }}>{type || 'pipeline'}</span>
  )
}

const TechTag = ({ label }) => (
  <span style={{
    fontSize: '10px', padding: '2px 7px', borderRadius: '4px',
    background: 'var(--surface-hover, rgba(255,255,255,.07))', color: 'var(--text-secondary)',
    border: '1px solid var(--border)',
  }}>{label}</span>
)

/* â”€â”€ main component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function SpecPage() {
  const [repos, setRepos] = useState([])
  const [owner, setOwner] = useState('')
  const [selectedRepos, setSelectedRepos] = useState([])

  // pipeline detection
  const [pipelines, setPipelines] = useState([])
  const [pipelineDetected, setPipelineDetected] = useState(false)
  const [detectingPipelines, setDetectingPipelines] = useState(false)
  const [selectedPipelineIds, setSelectedPipelineIds] = useState([])
  const [expandedPipelineId, setExpandedPipelineId] = useState(null)
  const [detectError, setDetectError] = useState(null)

  // spec generation
  const [mode, setMode] = useState(MODES.CLASSIC)
  const [templateFile, setTemplateFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState(null)   // pipeline id or 'classic'
  const [specResults, setSpecResults] = useState({}) // { [pipelineId|'classic']: {spec, validation, ...} }
  const [generatingIds, setGeneratingIds] = useState(new Set())
  const [copied, setCopied] = useState(false)
  const fileInputRef = useRef(null)

  useEffect(() => {
    const fetchRepos = async () => {
      try {
        const res = await getGitHubRepos()
        setRepos(res.data.repos || [])
        setOwner(res.data.owner || '')
      } catch {
        setRepos([])
      }
    }
    fetchRepos()
  }, [])

  const buildRepoList = () =>
    selectedRepos.map(name => {
      const repo = repos.find(r => r.name === name)
      return { owner: repo?.owner || owner, repo_name: name }
    })

  /* â”€â”€ pipeline detection â”€â”€â”€ */
  const handleDetectPipelines = async () => {
    if (selectedRepos.length === 0) return
    setDetectingPipelines(true)
    setDetectError(null)
    setPipelines([])
    setPipelineDetected(false)
    setSelectedPipelineIds([])
    setSpecResults({})
    setActiveTab(null)

    try {
      const res = await detectPipelines(buildRepoList())
      const detected = res.data.pipelines || []
      setPipelines(detected)
      setPipelineDetected(true)
      // Pre-select all detected pipelines
      setSelectedPipelineIds(detected.map(p => p.id))
      if (detected.length > 0) setExpandedPipelineId(detected[0].id)
    } catch (err) {
      setDetectError(err.response?.data?.detail || 'Detection failed â€” check backend.')
    }
    setDetectingPipelines(false)
  }

  const toggleSelectPipeline = (id) =>
    setSelectedPipelineIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )

  /* â”€â”€ spec generation â”€â”€â”€ */
  const handleClassicGenerate = async () => {
    if (selectedRepos.length === 0) return
    setLoading(true)
    setError(null)
    try {
      const repoList = buildRepoList()
      const res = await generateSpec(repoList[0].owner, repoList[0].repo_name)
      setSpecResults({ classic: { spec: res.data.spec } })
      setActiveTab('classic')
    } catch (err) {
      setError(err.response?.data?.detail || 'Generation failed.')
    }
    setLoading(false)
  }

  const handleGeneratePerPipeline = async () => {
    if (!templateFile) {
      setError('Please upload a template file (PDF or Markdown).')
      return
    }
    if (selectedPipelineIds.length === 0) {
      setError('Select at least one pipeline to generate a spec for.')
      return
    }
    setError(null)
    const repoList = buildRepoList()
    const toGenerate = pipelines.filter(p => selectedPipelineIds.includes(p.id))

    // generate sequentially (avoid hammering LLM)
    for (const pipeline of toGenerate) {
      setGeneratingIds(prev => new Set([...prev, pipeline.id]))
      try {
        const res = await generateSpecFromTemplate(repoList, templateFile, pipeline)
        setSpecResults(prev => ({
          ...prev,
          [pipeline.id]: {
            spec: res.data.spec,
            validation: res.data.validation,
            fields: res.data.fields,
            extracted_values: res.data.extracted_values,
          },
        }))
        setActiveTab(pipeline.id)
      } catch (err) {
        setSpecResults(prev => ({
          ...prev,
          [pipeline.id]: { error: err.response?.data?.detail || 'Generation failed.' },
        }))
      }
      setGeneratingIds(prev => { const s = new Set(prev); s.delete(pipeline.id); return s })
    }
  }

  const handleCopy = () => {
    const result = specResults[activeTab]
    if (!result?.spec) return
    navigator.clipboard.writeText(result.spec)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const activeResult = specResults[activeTab] || null

  return (
    <div>
      <div className="page-header">
        <h2>Generate Specification</h2>
        <p>Detect pipelines/modules from your code, then generate a tailored spec for each one.</p>
      </div>

      {/* â”€â”€ Mode Toggle â”€â”€ */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <button
          className={`btn ${mode === MODES.CLASSIC ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setMode(MODES.CLASSIC)}
        >
          <FileText size={14} /> Classic (Auto)
        </button>
        <button
          className={`btn ${mode === MODES.TEMPLATE ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setMode(MODES.TEMPLATE)}
        >
          <Upload size={14} /> From Template
        </button>
      </div>

      {error && <div className="message error">{error}</div>}

      {/* â”€â”€ Repo Selector â”€â”€ */}
      <div style={{ marginBottom: '16px' }}>
        <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '8px' }}>
          Select repositories <span style={{ fontWeight: 400, opacity: .7 }}>(hold Ctrl / âŒ˜ for multiple)</span>
        </label>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <select
            multiple
            size={Math.min(repos.length || 4, 6)}
            value={selectedRepos}
            onChange={e => setSelectedRepos(Array.from(e.target.selectedOptions, o => o.value))}
            style={{ minWidth: '220px', height: 'auto' }}
          >
            {repos.map(repo => (
              <option key={repo.name} value={repo.name}>{repo.name}</option>
            ))}
          </select>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {selectedRepos.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {selectedRepos.map(name => (
                  <span key={name} style={{
                    fontSize: '11px', padding: '3px 8px', borderRadius: '999px',
                    background: 'var(--accent)', color: '#fff', fontWeight: 600,
                  }}>
                    {name}
                    <button
                      onClick={() => setSelectedRepos(prev => prev.filter(r => r !== name))}
                      style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', marginLeft: '4px', fontWeight: 700 }}
                    >Ã—</button>
                  </span>
                ))}
              </div>
            )}

            {mode === MODES.CLASSIC ? (
              <button
                className="btn btn-primary"
                onClick={handleClassicGenerate}
                disabled={selectedRepos.length === 0 || loading}
              >
                {loading ? <><Loader2 size={14} className="spinner" /> Generating...</> : <><FileText size={14} /> Generate Spec</>}
              </button>
            ) : (
              <button
                className="btn btn-secondary"
                onClick={handleDetectPipelines}
                disabled={selectedRepos.length === 0 || detectingPipelines}
                style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}
              >
                {detectingPipelines
                  ? <><Loader2 size={14} className="spinner" /> Detecting pipelines...</>
                  : <><Search size={14} /> Detect Pipelines / Modules</>}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* â”€â”€ Template Upload â”€â”€ */}
      {mode === MODES.TEMPLATE && (
        <div className="section" style={{ marginBottom: '20px' }}>
          <h3 className="section-title"><Upload size={16} /> Upload Template</h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
            Upload any template (PDF or Markdown). Agents will auto-detect fields, extract values,
            and compose a filled spec â€” scoped to each detected pipeline.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.md,.txt"
              style={{ display: 'none' }}
              onChange={e => setTemplateFile(e.target.files[0] || null)}
            />
            <button className="btn btn-secondary" onClick={() => fileInputRef.current.click()}>
              <Upload size={14} /> {templateFile ? templateFile.name : 'Choose file (.pdf, .md)'}
            </button>
            {templateFile && (
              <span style={{ fontSize: '12px', color: 'var(--accent)' }}>
                âœ… {templateFile.name} ({(templateFile.size / 1024).toFixed(1)} KB)
              </span>
            )}
          </div>
        </div>
      )}

      {/* â”€â”€ Detection error â”€â”€ */}
      {detectError && <div className="message error" style={{ marginBottom: '16px' }}>{detectError}</div>}

      {/* â”€â”€ Pipeline Cards â”€â”€ */}
      {mode === MODES.TEMPLATE && pipelineDetected && (
        <div className="section" style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h3 className="section-title" style={{ margin: 0 }}>
              <Layers size={16} /> {pipelines.length} Pipeline{pipelines.length !== 1 ? 's' : ''} Detected
            </h3>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-secondary"
                style={{ fontSize: '11px', padding: '4px 10px' }}
                onClick={() => setSelectedPipelineIds(pipelines.map(p => p.id))}
              >Select all</button>
              <button
                className="btn btn-secondary"
                style={{ fontSize: '11px', padding: '4px 10px' }}
                onClick={() => setSelectedPipelineIds([])}
              >Deselect all</button>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '16px' }}>
            {pipelines.map(pipeline => {
              const isSelected = selectedPipelineIds.includes(pipeline.id)
              const isExpanded = expandedPipelineId === pipeline.id
              const isGenerating = generatingIds.has(pipeline.id)
              const hasResult = !!specResults[pipeline.id]
              return (
                <div
                  key={pipeline.id}
                  style={{
                    border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`,
                    borderRadius: '8px',
                    background: isSelected ? 'rgba(var(--accent-rgb, 14,165,233),.06)' : 'var(--surface)',
                    overflow: 'hidden',
                    transition: 'border-color .2s',
                  }}
                >
                  {/* card header */}
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '12px 14px', cursor: 'pointer' }}
                    onClick={() => setExpandedPipelineId(isExpanded ? null : pipeline.id)}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={e => { e.stopPropagation(); toggleSelectPipeline(pipeline.id) }}
                      style={{ accentColor: 'var(--accent)', width: '15px', height: '15px', cursor: 'pointer' }}
                    />
                    <span style={{ fontWeight: 700, fontSize: '14px', flex: 1 }}>{pipeline.name}</span>
                    <TypeBadge type={pipeline.type} />
                    {hasResult && (
                      <span style={{ fontSize: '11px', color: '#22c55e', fontWeight: 600 }}>âœ“ spec ready</span>
                    )}
                    {isGenerating && <Loader2 size={13} className="spinner" />}
                    {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>

                  {/* card body */}
                  {isExpanded && (
                    <div style={{ borderTop: '1px solid var(--border)', padding: '12px 14px', fontSize: '13px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <p style={{ color: 'var(--text-secondary)', margin: 0 }}>{pipeline.description}</p>

                      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                        {pipeline.source_files?.length > 0 && (
                          <div>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                              <GitBranch size={11} /> Source files
                            </span>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                              {pipeline.source_files.map(f => <TechTag key={f} label={f} />)}
                            </div>
                          </div>
                        )}
                        {pipeline.source_tables?.length > 0 && (
                          <div>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                              <Database size={11} /> Tables
                            </span>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                              {pipeline.source_tables.map(t => <TechTag key={t} label={t} />)}
                            </div>
                          </div>
                        )}
                        {pipeline.technologies?.length > 0 && (
                          <div>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                              Technologies
                            </span>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                              {pipeline.technologies.map(t => <TechTag key={t} label={t} />)}
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

          {/* Generate button */}
          <button
            className="btn btn-primary"
            onClick={handleGeneratePerPipeline}
            disabled={selectedPipelineIds.length === 0 || generatingIds.size > 0 || !templateFile}
            style={{ width: '100%', justifyContent: 'center', padding: '10px' }}
          >
            {generatingIds.size > 0
              ? <><Loader2 size={14} className="spinner" /> Generating {generatingIds.size} spec{generatingIds.size > 1 ? 's' : ''}...</>
              : <><FileText size={14} /> Generate Spec for {selectedPipelineIds.length} Selected Pipeline{selectedPipelineIds.length !== 1 ? 's' : ''}</>
            }
          </button>
        </div>
      )}

      {/* â”€â”€ Classic loading â”€â”€ */}
      {loading && (
        <div className="loading">
          <div className="spinner"></div>
          <span>The LLM is analyzing the code... (30-60s)</span>
        </div>
      )}

      {/* â”€â”€ Results: tabs â”€â”€ */}
      {Object.keys(specResults).length > 0 && (
        <div className="section">
          {/* Tab bar */}
          <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid var(--border)', marginBottom: '16px', flexWrap: 'wrap' }}>
            {Object.keys(specResults).map(key => {
              const label = key === 'classic'
                ? selectedRepos[0] || 'Spec'
                : pipelines.find(p => p.id === key)?.name || key
              return (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  style={{
                    padding: '7px 14px',
                    fontSize: '12px',
                    fontWeight: activeTab === key ? 700 : 400,
                    background: 'none',
                    border: 'none',
                    borderBottom: activeTab === key ? '2px solid var(--accent)' : '2px solid transparent',
                    color: activeTab === key ? 'var(--accent)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                    marginBottom: '-1px',
                  }}
                >
                  {label}
                  {specResults[key]?.error && ' âš ï¸'}
                </button>
              )
            })}
          </div>

          {/* Active result */}
          {activeResult?.error ? (
            <div className="message error">{activeResult.error}</div>
          ) : (
            <>
              {/* Validation report */}
              {activeResult?.validation && (
                <div style={{ marginBottom: '14px' }}>
                  <h3 className="section-title">
                    {activeResult.validation.is_valid
                      ? <><CheckCircle size={16} style={{ color: '#22c55e' }} /> Validation</>
                      : <><AlertCircle size={16} style={{ color: '#f59e0b' }} /> Validation</>}
                  </h3>
                  <pre style={{ fontSize: '12px', whiteSpace: 'pre-wrap', color: 'var(--text-secondary)' }}>
                    {activeResult.validation.report}
                  </pre>
                  {activeResult.validation.missing?.length > 0 && (
                    <p style={{ color: '#f59e0b', fontSize: '12px', marginTop: '6px' }}>
                      âš ï¸ Some fields could not be automatically extracted â€” edit the spec below.
                    </p>
                  )}
                </div>
              )}

              {/* Spec textarea */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h3 className="section-title" style={{ margin: 0 }}>
                  <FileText size={16} />
                  {activeTab === 'classic'
                    ? `Spec â€” ${selectedRepos[0] || ''}`
                    : `Spec â€” ${pipelines.find(p => p.id === activeTab)?.name || activeTab}`}
                </h3>
                <button className="btn btn-secondary" onClick={handleCopy}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <textarea
                value={activeResult?.spec || ''}
                onChange={e => setSpecResults(prev => ({
                  ...prev,
                  [activeTab]: { ...prev[activeTab], spec: e.target.value },
                }))}
                style={{
                  width: '100%', minHeight: '500px', resize: 'vertical',
                  fontFamily: 'monospace', fontSize: '13px',
                  background: 'var(--surface)', color: 'var(--text-primary)',
                  border: '1px solid var(--border)', borderRadius: '8px', padding: '16px',
                  boxSizing: 'border-box',
                }}
              />
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default SpecPage
