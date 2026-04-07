import { useState, useEffect, useRef } from 'react'
import { FileText, Loader2, Copy, Check, Upload, AlertCircle, CheckCircle } from 'lucide-react'
import { generateSpec, generateSpecFromTemplate, getGitHubRepos } from '../api'

const MODES = { CLASSIC: 'classic', TEMPLATE: 'template' }

function SpecPage() {
  const [repos, setRepos] = useState([])
  const [owner, setOwner] = useState('')
  const [selectedRepo, setSelectedRepo] = useState('')
  const [spec, setSpec] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)
  const [mode, setMode] = useState(MODES.CLASSIC)

  // Template mode state
  const [templateFile, setTemplateFile] = useState(null)
  const [validation, setValidation] = useState(null)
  const [detectedFields, setDetectedFields] = useState(null)
  const [extractedValues, setExtractedValues] = useState(null)
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

  const handleGenerate = async () => {
    if (!selectedRepo) return
    setLoading(true)
    setError(null)
    setSpec(null)
    setValidation(null)
    setDetectedFields(null)
    setExtractedValues(null)

    try {
      const repo = repos.find(r => r.name === selectedRepo)
      const repoOwner = repo?.owner || owner

      if (mode === MODES.CLASSIC) {
        const res = await generateSpec(repoOwner, selectedRepo)
        setSpec(res.data.spec)
      } else {
        if (!templateFile) {
          setError('Please upload a template file (PDF or Markdown).')
          setLoading(false)
          return
        }
        const res = await generateSpecFromTemplate(repoOwner, selectedRepo, templateFile)
        setSpec(res.data.spec)
        setValidation(res.data.validation)
        setDetectedFields(res.data.fields)
        setExtractedValues(res.data.extracted_values)
      }
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Error: check that GitHub is connected and the LLM is running'
      )
    }
    setLoading(false)
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(spec)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div>
      <div className="page-header">
        <h2>Generate Specification</h2>
        <p>Select a repository and automatically generate technical and functional specs.</p>
      </div>

      {/* Mode Toggle */}
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

      {/* Repo Selector */}
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap' }}>
        <select
          value={selectedRepo}
          onChange={(e) => setSelectedRepo(e.target.value)}
        >
          <option value="">Select a repository</option>
          {repos.map((repo) => (
            <option key={repo.name} value={repo.name}>
              {repo.name}
            </option>
          ))}
        </select>

        <button
          className="btn btn-primary"
          onClick={handleGenerate}
          disabled={!selectedRepo || loading || (mode === MODES.TEMPLATE && !templateFile)}
        >
          {loading ? (
            <><Loader2 size={14} className="spinner" /> Generating...</>
          ) : (
            <><FileText size={14} /> Generate Spec</>
          )}
        </button>
      </div>

      {/* Template Upload (only in template mode) */}
      {mode === MODES.TEMPLATE && (
        <div className="section" style={{ marginBottom: '20px' }}>
          <h3 className="section-title"><Upload size={16} /> Upload Template</h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
            Upload any template file (PDF or Markdown). The agents will automatically detect fields,
            extract values from your repository, and compose the filled specification.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.md,.txt"
              style={{ display: 'none' }}
              onChange={(e) => setTemplateFile(e.target.files[0] || null)}
            />
            <button className="btn btn-secondary" onClick={() => fileInputRef.current.click()}>
              <Upload size={14} /> {templateFile ? templateFile.name : 'Choose file (.pdf, .md)'}
            </button>
            {templateFile && (
              <span style={{ fontSize: '12px', color: 'var(--accent)' }}>
                ✅ {templateFile.name} ({(templateFile.size / 1024).toFixed(1)} KB)
              </span>
            )}
          </div>
        </div>
      )}

      {loading && (
        <div className="loading">
          <div className="spinner"></div>
          <span>
            {mode === MODES.TEMPLATE
              ? 'Agents are extracting, mapping and validating fields from your template... (60-90s)'
              : 'The LLM is analyzing the code and generating the spec... (30-60s)'}
          </span>
        </div>
      )}

      {/* Validation Report */}
      {validation && (
        <div className="section" style={{ marginBottom: '16px' }}>
          <h3 className="section-title">
            {validation.is_valid
              ? <><CheckCircle size={16} style={{ color: '#22c55e' }} /> Validation Report</>
              : <><AlertCircle size={16} style={{ color: '#f59e0b' }} /> Validation Report</>
            }
          </h3>
          <pre style={{ fontSize: '12px', whiteSpace: 'pre-wrap', color: 'var(--text-secondary)' }}>
            {validation.report}
          </pre>
          {validation.missing?.length > 0 && (
            <p style={{ color: '#f59e0b', fontSize: '12px', marginTop: '8px' }}>
              ⚠️ Some fields could not be automatically extracted. You can edit the spec manually below.
            </p>
          )}
        </div>
      )}

      {/* Generated Spec */}
      {spec && (
        <div className="section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h3 className="section-title">
              <FileText size={16} />
              Specification — {selectedRepo}
            </h3>
            <button className="btn btn-secondary" onClick={handleCopy}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <textarea
            className="spec-output"
            value={spec}
            onChange={(e) => setSpec(e.target.value)}
            style={{ width: '100%', minHeight: '500px', resize: 'vertical', fontFamily: 'monospace', fontSize: '13px', background: 'var(--surface)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: '8px', padding: '16px' }}
          />
        </div>
      )}
    </div>
  )
}

export default SpecPage
