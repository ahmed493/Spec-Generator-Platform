import { useState, useEffect } from 'react'
import { FileText, Loader2, Copy, Check } from 'lucide-react'
import { generateSpec, getGitHubRepos } from '../api'

function SpecPage() {
  const [repos, setRepos] = useState([])
  const [owner, setOwner] = useState('')
  const [selectedRepo, setSelectedRepo] = useState('')
  const [spec, setSpec] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)

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

    try {
      const repo = repos.find(r => r.name === selectedRepo)
      const res = await generateSpec(repo?.owner || owner, selectedRepo)
      setSpec(res.data.spec)
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Error: check that GitHub is connected and Ollama is running'
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

      {error && <div className="message error">{error}</div>}

      <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '24px' }}>
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
          disabled={!selectedRepo || loading}
        >
          {loading ? (
            <>
              <Loader2 size={14} className="spinner" />
              Generating...
            </>
          ) : (
            <>
              <FileText size={14} />
              Generate Spec
            </>
          )}
        </button>
      </div>

      {loading && (
        <div className="loading">
          <div className="spinner"></div>
          <span>The LLM is analyzing the code and generating the spec... (30-60s)</span>
        </div>
      )}

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
          <div className="spec-output">{spec}</div>
        </div>
      )}
    </div>
  )
}

export default SpecPage
